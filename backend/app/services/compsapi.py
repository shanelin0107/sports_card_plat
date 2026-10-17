"""CompsAPI (compsapi.com): eBay sold listings as JSON.

eBay's own sold-history API is partner-only and its sold search page is behind a
captcha + login, so a paid aggregator is the reliable way to get recent sales.

Docs: https://compsapi.com/docs  ·  Each /v1/sold call costs one request of the monthly
quota (free plan: 100/month, 10/min, 1 year of history). /v1/usage is free.
"""

from __future__ import annotations

import re
import time

import httpx

from app.core.config import settings
from app.services.ebay import match_listing
from app.services.ingestion.parsing import parse_title
from app.services.names import TEAM_WORDS

USER_AGENT = "sports-card-portfolio/0.6 (+compsapi)"  # the API rejects requests without one


class CompsApiError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class QuotaReached(CompsApiError):
    pass


class Unavailable(CompsApiError):
    """CompsAPI is overloaded or timed out (5xx). Failed searches don't use quota."""


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
            if r.status_code in (500, 502, 503, 504):
                if attempt == 0:
                    time.sleep(2)
                    continue
                raise Unavailable(f"CompsAPI {r.status_code}: {_json(r).get('error') or 'temporarily unavailable'}", r.status_code)
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
    # Popular players (thousands of sales a year) can make a 1-year search time out on
    # CompsAPI's side (503). Step down to a shorter window rather than giving up.
    first = max(1, min(days or settings.compsapi_days, 1095))
    plan = [(first, size)] + [(d, min(size, 60)) for d in (90, 30) if d < first]
    data: dict | None = None
    last_err: Exception | None = None
    for span, sz in plan:
        try:
            data = _get(
                "/v1/sold",
                {
                    "q": query[:300],
                    "days": span,
                    "size": sz,
                    "site": "US",
                    "best_offer": "1",  # real accepted price on Best Offer sales
                    **grade_params(grade),
                },
            )
            days_used = span
            break
        except (Unavailable, httpx.TimeoutException) as exc:
            last_err = exc
    if data is None:
        raise Unavailable(
            "CompsAPI is busy right now (no search was used). Press ↻ again in a minute.",
            getattr(last_err, "status", 503),
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
    return {"query": query, "count": int(data.get("count") or len(rows)), "items": rows, "days": days_used}


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


# --------------------------------------------------------------------------- free-text sold search

SEARCH_CACHE_SECONDS = 6 * 3600  # the same search within 6 h reuses the result (no quota spent)
_search_cache: dict[str, tuple[float, dict]] = {}


def _stats(prices: list[float]) -> dict | None:
    if not prices:
        return None
    s = sorted(prices)
    n = len(s)
    med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return {"count": n, "low": s[0], "median": round(med, 2), "high": s[-1]}


_DROP = {
    "rc", "rookie", "rookies", "auto", "autos", "autograph", "autographs", "autographed", "signed",
    "refractor", "refractors", "f1", "card", "cards", "ssp", "sp", "numbered", "raw", "ungraded",
    "psa", "bgs", "sgc", "cgc", "gem", "mint", "mt", "nm",
}
# Team nicknames: many titles leave them out, and they never identify the card.
# Team nicknames: many titles leave them out, and they never identify the card.
_TEAM_WORDS = TEAM_WORDS


# Pattern words sellers spell several ways ("RayWave" / "Ray Wave"): checked on the result
# titles after normalising, instead of being sent as search keywords.
_PATTERNS = {
    "raywave", "lazer", "laser", "mojo", "wave", "shimmer", "hyper", "disco", "ice", "camo", "scope", "cracked",
    "pulsar", "velocity", "snakeskin", "speckle", "sparkle", "geometric", "checkerboard", "xfractor", "tiedye",
    "sepiafractor", "kaleidoscope", "lava", "atomic", "nebula", "galactic", "zebra", "tiger", "peacock",
}


def simplify_query(q: str) -> tuple[str, list[str], int | None]:
    """Typed text -> (keywords to search, words every result title must contain, print run).

    "2025 Topps Chrome F1 Oliver Bearman Auto Orange RayWave Refractor RC #/25"
    -> ("2025 topps chrome oliver bearman orange", ["raywave"], 25)"""
    from app.services.ebay import _SERIAL, _norm, strip_seasons

    # Card codes (FAN-21, CAC-BEA) are often left out of titles: don't make them keywords.
    q = re.sub(r"(?<![\w-])#?[A-Za-z]{1,5}-(?:\d{1,4}[A-Za-z]?|[A-Za-z]{2,4})(?![\w-])", " ", q)
    t = strip_seasons(_norm(q))
    serial = _SERIAL.search(t)
    run = int(serial.group(1)) if serial else None
    t = _SERIAL.sub(" ", t)
    t = re.sub(r"\b(psa|bgs|sgc|cgc)\s*(10|[1-9](\.5)?)\b", " ", t)
    keep, must = [], []
    for w in t.split():
        if w.startswith("#") or w in _DROP or w in _TEAM_WORDS:
            continue  # card numbers / codes, team names and words sellers often leave out
        bucket = must if w in _PATTERNS else keep
        if w not in bucket:
            bucket.append(w)
    return " ".join(keep) or q.strip(), must, run


def search_sold(query: str, days: int | None = None) -> dict:
    """Sold eBay listings for whatever the owner typed (search page). One CompsAPI request,
    cached for 6 hours; grades are read from titles so the page can filter without
    spending more requests. Lots, breaks, reprints and sealed product are left out."""
    from app.services.ebay import _norm, is_junk

    q = " ".join(query.split())[:300]
    key = f"{q.lower()}|{days or settings.compsapi_days}"
    hit = _search_cache.get(key)
    if hit and time.time() - hit[0] < SEARCH_CACHE_SECONDS:
        return {**hit[1], "cached": True}

    keywords, must, run = simplify_query(q)
    data = fetch_sold(keywords, {}, None, days=days, size=200)

    def relevant(r: dict) -> bool:
        t = f" {_norm(r['title'])} "
        if is_junk(t) or not all(f" {w} " in t for w in must):
            return False
        if run:
            from app.services.ebay import serials_in

            serials = serials_in(t)
            if serials and run not in serials:
                return False  # a /50 is not the /25 that was asked for
        return True

    items = [r for r in data["items"] if r["date"] and relevant(r)]
    for r in items:
        for k in ("exact_match", "mismatches"):
            r.pop(k, None)
    items.sort(key=lambda r: r.get("sold_at") or r["date"], reverse=True)
    out = {
        "query": q,
        "searched_for": keywords,
        "must_include": must + ([f"/{run}"] if run else []),
        "days": data.get("days"),
        "count": len(items),
        "items": items,
        "stats": _stats([r["total"] for r in items]),
        "last_sale": items[0] if items else None,
        "cached": False,
    }
    _search_cache[key] = (time.time(), out)
    if len(_search_cache) > 200:  # keep memory bounded
        for k, _ in sorted(_search_cache.items(), key=lambda kv: kv[1][0])[:50]:
            _search_cache.pop(k, None)
    return out
