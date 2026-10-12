"""AI price research: Claude searches the web for sold comps and live listings of one card.

Design rules
- Suggestions only. Nothing is written to sale_comp until the owner clicks "Save".
- Every price must be backed by a page the model actually retrieved this run. Items whose
  URL never appeared in a web_search / web_fetch result are dropped (anti-hallucination).
- The model reports through a client tool with a JSON schema, so output is structured.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import AiPriceResearch

logger = logging.getLogger(__name__)

MAX_ROUNDS = 6

SYSTEM_PROMPT = """You are a sports-card pricing researcher. Given a card description, you:

1. Pin down the EXACT card: product (e.g. "2024-25 Panini Prizm Black" is a different product
   from "2024-25 Panini Prizm"), card number, player, parallel name, print run (/60), and
   whether it is an auto / patch / rookie. Check a checklist source when the parallel name is
   ambiguous (e.g. "Orange" vs "Orange Wave" are different parallels with different print runs).
2. Find SOLD prices first (eBay sold/completed, 130point, Card Ladder, SportsCardsPro,
   PriceCharting, Fanatics Collect, Goldin, Alt, etc.), then current active listings.
3. Report through the `report_prices` tool exactly once, when you are done.

Hard rules:
- Never invent or estimate a data point. Every sold or active entry must come from a page you
  retrieved in this conversation, and its `url` must be that page's URL.
- Mark `exact_match: false` whenever the product, card number, parallel, serial run or grade
  differs from the target, and say what differs in `note`. Near-matches are still useful context.
- Prices in USD as numbers. Include shipping in `price` only if the source shows a total.
- `grade` is "Raw" or "<grader> <grade>" such as "PSA 10" or "BGS 9.5".
- `date` is the sale date (YYYY-MM-DD) for sold items; omit if the page doesn't show one.
- Only give an `estimate` when it is grounded in exact or very close sold comps; otherwise
  leave it out and explain in `summary`.
- Low-population parallels often have few or no recorded sales. Saying "no sales found" is a
  correct, useful answer.
"""

PRICE_ITEM = {
    "type": "object",
    "properties": {
        "price": {"type": "number"},
        "date": {"type": "string", "description": "YYYY-MM-DD"},
        "grade": {"type": "string"},
        "title": {"type": "string", "description": "Listing or record title as shown"},
        "url": {"type": "string"},
        "source": {"type": "string", "description": "e.g. eBay, 130point, SportsCardsPro"},
        "exact_match": {"type": "boolean"},
        "note": {"type": "string"},
    },
    "required": ["price", "title", "url", "source", "exact_match"],
}

REPORT_TOOL = {
    "name": "report_prices",
    "description": "Submit the final, sourced price research for the card. Call exactly once at the end.",
    "input_schema": {
        "type": "object",
        "properties": {
            "identified_card": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Full canonical name of the card"},
                    "year": {"type": "string"},
                    "product": {"type": "string"},
                    "card_number": {"type": "string"},
                    "player": {"type": "string"},
                    "parallel": {"type": "string"},
                    "print_run": {"type": "string"},
                    "attributes": {"type": "array", "items": {"type": "string"}},
                    "lookalikes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Similar cards that are easy to confuse with this one",
                    },
                },
                "required": ["description"],
            },
            "identification_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "sold": {"type": "array", "items": PRICE_ITEM},
            "active": {"type": "array", "items": PRICE_ITEM},
            "estimate": {
                "type": "object",
                "properties": {
                    "low": {"type": "number"},
                    "mid": {"type": "number"},
                    "high": {"type": "number"},
                    "grade": {"type": "string"},
                    "basis": {"type": "string"},
                },
            },
            "summary": {"type": "string"},
            "caveats": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["identified_card", "identification_confidence", "sold", "active", "summary"],
    },
}


class AiNotConfigured(RuntimeError):
    pass


def ai_enabled() -> bool:
    return bool(settings.anthropic_api_key)


def _client():
    if not ai_enabled():
        raise AiNotConfigured("ANTHROPIC_API_KEY is not set")
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=180.0, max_retries=2)


def _url_key(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    # ebay.de / ebay.co.uk item pages are the same listing as ebay.com
    if host.startswith("ebay."):
        host = "ebay"
    return f"{host}{parts.path.rstrip('/')}"


def _get(obj: Any, key: str, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _collect_urls(blocks: list[Any], seen: set[str]) -> None:
    for b in blocks:
        btype = _get(b, "type")
        if btype == "web_search_tool_result":
            content = _get(b, "content")
            if isinstance(content, list):
                for r in content:
                    url = _get(r, "url")
                    if url:
                        seen.add(_url_key(url))
        elif btype == "web_fetch_tool_result":
            content = _get(b, "content")
            url = _get(content, "url") if content is not None else None
            if url:
                seen.add(_url_key(url))
        # citations inside text blocks also point at retrieved pages
        for c in _get(b, "citations") or []:
            url = _get(c, "url")
            if url:
                seen.add(_url_key(url))


def build_prompt(query: str, grade: str | None, card: dict | None) -> str:
    lines = [f"Card to price: {query.strip()}"]
    if card:
        lines.append(
            "Catalog record: "
            + ", ".join(f"{k}={v}" for k, v in card.items() if v not in (None, "", False))
        )
    lines.append(f"Target grade: {grade or 'any (report each grade separately)'}")
    lines.append("Research it now and finish by calling report_prices.")
    return "\n".join(lines)


def verify_items(items: list[dict], seen: set[str]) -> tuple[list[dict], list[dict]]:
    kept, dropped = [], []
    for it in items or []:
        url = (it.get("url") or "").strip()
        price = it.get("price")
        if not url.startswith("http") or not isinstance(price, (int, float)) or price <= 0:
            dropped.append({**it, "dropped_reason": "missing url or price"})
        elif _url_key(url) not in seen:
            dropped.append({**it, "dropped_reason": "source page was not retrieved this run"})
        else:
            kept.append(it)
    return kept, dropped


def run_research(query: str, grade: str | None = None, card: dict | None = None, client=None) -> dict:
    """Synchronous research call. Returns {"result": ..., "usage": ...}."""
    client = client or _client()
    tools = [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": settings.ai_max_searches},
        {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": settings.ai_max_fetches, "max_content_tokens": 30000},
        REPORT_TOOL,
    ]
    messages: list[dict] = [{"role": "user", "content": build_prompt(query, grade, card)}]
    seen: set[str] = set()
    usage = {"input_tokens": 0, "output_tokens": 0, "searches": 0}
    report = None

    for _ in range(MAX_ROUNDS):
        resp = client.messages.create(
            model=settings.ai_model,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )
        u = _get(resp, "usage")
        usage["input_tokens"] += int(_get(u, "input_tokens", 0) or 0)
        usage["output_tokens"] += int(_get(u, "output_tokens", 0) or 0)
        stu = _get(u, "server_tool_use")
        usage["searches"] += int(_get(stu, "web_search_requests", 0) or 0) if stu else 0

        content = list(_get(resp, "content") or [])
        _collect_urls(content, seen)
        report = next((b for b in content if _get(b, "type") == "tool_use" and _get(b, "name") == "report_prices"), None)
        if report is not None:
            break

        messages.append({"role": "assistant", "content": content})
        stop = _get(resp, "stop_reason")
        if stop == "pause_turn":
            continue  # long server-tool turn; send it back unchanged to continue
        messages.append({"role": "user", "content": "Please finish now by calling report_prices with what you found."})

    if report is None:
        raise RuntimeError("The model did not return a report")

    data = dict(_get(report, "input") or {})
    sold, sold_dropped = verify_items(data.get("sold", []), seen)
    active, active_dropped = verify_items(data.get("active", []), seen)
    data["sold"] = sorted(sold, key=lambda x: x.get("date") or "", reverse=True)
    data["active"] = active
    data["unverified"] = sold_dropped + active_dropped
    return {"result": data, "usage": usage}


def execute_job(job_id: int, session_factory) -> None:
    """Background task body: runs the research and stores the outcome on the job row."""
    db: Session = session_factory()
    try:
        job = db.get(AiPriceResearch, job_id)
        if job is None:
            return
        meta = job.result_json or {}
        card_ctx = meta.get("_card_context")
        auto_save = bool(meta.get("_auto_save"))
        try:
            out = run_research(job.query, job.grade, card_ctx)
            result = out["result"]
            if auto_save and job.card_id:
                result["auto_saved"] = _auto_save_sold(db, job, result)
            job.result_json = result  # assign after mutations so the JSON column is persisted
            job.status = "completed"
            job.searches_used = out["usage"]["searches"]
            job.input_tokens = out["usage"]["input_tokens"]
            job.output_tokens = out["usage"]["output_tokens"]
        except Exception as exc:  # surfaced to the UI
            logger.exception("AI price research %s failed", job_id)
            job.status = "failed"
            job.error_message = str(exc)[:1000]
        job.completed_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def _auto_save_sold(db: Session, job: AiPriceResearch, result: dict) -> int:
    """Save exact, dated, source-verified sold records as comps (used by background sync)."""
    from app.services.comps import CompError, create_confirmed_comp

    saved = 0
    for i, item in enumerate(result.get("sold") or []):
        if not (item.get("exact_match") and item.get("date") and item.get("url")):
            continue
        try:
            comp, created = create_confirmed_comp(
                db,
                card_id=job.card_id,
                listing_id=f"ai-{job.id}-{i}",
                title=item.get("title", ""),
                url=item["url"],
                price=float(item["price"]),
                date=item["date"],
                grade=item.get("grade"),
                source=item.get("source", ""),
                match_method="ai_research_auto",
                payload={"ai_research_id": job.id, "item": item},
            )
        except (CompError, ValueError, TypeError):
            continue
        item["saved_comp_id"] = comp.id
        saved += int(created)
    return saved
