"""CompsAPI (compsapi.com): eBay sold listings as JSON.

eBay's own sold-history API is partner-only and its sold search page is behind a
captcha + login, so a paid aggregator is the reliable way to get recent sales.

Docs: https://compsapi.com/docs  ·  Each /v1/sold call costs one request of the monthly
quota (free plan: 100/month, 10/min, 1 year of history). /v1/usage is free.
"""

from __future__ import annotations

import time

import httpx

from app.core.config import settings
from app.services.ebay import match_listing
from app.services.ingestion.parsing import parse_title

USER_AGENT = "sports-card-portfolio/0.6 (+compsapi)"  # the API rejects requests without one


class CompsApiError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class QuotaReached(CompsApiError):
    pass


def enabled() -> bool:
    return bool(settings.compsapi_key.strip())


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.compsapi_base.rstrip("/"),
        timeout=60.0,
        headers={"Authorization": f"Bearer {settings.compsapi_key.strip()}", "User-Agent": USER_AGENT},
    )


def _get(path: str, params: dict) -> dict:
    with _client() as c:
        for attempt in range(2):
            r = c.get(path, params={k: v for k, v in params.items() if v is not None})
            if r.status_code == 429:
                body = _json(r)
                msg = str(body.get("error") or "")
                if "quota" in msg.lower():
                    raise QuotaReached("CompsAPI monthly quota is used up (resets on the 1st, UTC).", 429)
                if attempt == 0:  # per-minute limit: wait as told, once
                    time.sleep(min(float(r.headers.get("Retry-After") or 6), 15))
                    continue
            if r.status_code == 503 and attempt == 0:
                time.sleep(2)
                continue
            if r.status_code >= 400:
                body = _json(r)
                hint = {401: "API key is missing or wrong", 403: "API key expired or request blocked"}.get(r.status_code, "")
                raise CompsApiError(f"CompsAPI {r.status_code}: {body.get('error') or hint or r.text[:200]}", r.status_code)
            return _json(r)
    raise CompsApiError("CompsAPI is rate-limiting requests; try again in a minute.", 429)


def _json(r: httpx.Response) -> dict:
    try:
        data = r.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def grade_params(grade: str | None) -> dict:
    """'Raw' -> raw cards only; 'PSA 10' -> PSA 10 slabs only; None -> anything."""
    if not grade:
        return {}
    g = grade.strip()
    if g.lower() == "raw":
        return {"graded": "false"}
    parts = g.split()
    if len(parts) == 2:
        return {"graded": "true", "grader": parts[0].upper(), "grade": parts[1]}
    return {"graded": "true", "grade": parts[-1]}


def _grade_of(title: str, requested: str | None) -> str:
    p = parse_title(title)
    if p.is_raw:
        return "Raw"
    if p.grader and p.grade_value:
        return f"{p.grader} {p.grade_value}"
    return requested or "Raw"


def fetch_sold(query: str, target: dict, grade: str | None, days: int | None = None, size: int = 120) -> dict:
    """Sold listings for a card. Every row is checked against the card (player, year, set,
    #, parallel, grade); only `exact_match` rows should become comps."""
    data = _get(
        "/v1/sold",
        {
            "q": query[:300],
            "days": max(1, min(days or settings.compsapi_days, 1095)),
            "size": size,
            "site": "US",
            "best_offer": "1",  # real accepted price on Best Offer sales
            **grade_params(grade),
        },
    )
    rows = []
    for it in data.get("items") or []:
        title = str(it.get("title") or "")
        try:
            price = float(it.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0 or not it.get("item_id"):
            continue
        ship = it.get("shipping_cost")
        try:
            ship = float(ship) if ship is not None else 0.0
        except (TypeError, ValueError):
            ship = 0.0
        exact, misses = match_listing(title, target, strict_base=True)
        rows.append(
            {
                "item_id": str(it["item_id"]),
                "title": title,
                "price": round(price, 2),
                "shipping": round(ship, 2),
                "total": round(price + ship, 2),
                "date": str(it.get("last_sold") or "")[:10] or None,
                "sold_at": str(it.get("last_sold") or "") or None,  # keeps the time of day
                "url": it.get("url") or f"https://www.ebay.com/itm/{it['item_id']}",
                "image": it.get("image"),
                "best_offer": bool(it.get("best_offer")),
                "format": it.get("format"),
                "grade": _grade_of(title, grade),
                "exact_match": exact,
                "mismatches": misses,
            }
        )
    return {"query": query, "count": int(data.get("count") or len(rows)), "items": rows}


def usage() -> dict:
    """Plan and monthly usage; free to call. Never includes the key."""
    if not enabled():
        return {"configured": False}
    try:
        u = _get("/v1/usage", {})
    except CompsApiError as exc:
        return {"configured": True, "error": str(exc)}
    return {
        "configured": True,
        "plan": u.get("plan"),
        "monthly_used": u.get("monthly_used"),
        "monthly_quota": u.get("monthly_quota"),
        "rpm_limit": u.get("rpm_limit"),
    }
