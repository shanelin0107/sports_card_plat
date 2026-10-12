"""eBay official APIs (no scraping).

- Browse API (`buy/browse/v1/item_summary/search`): live listings. Every production keyset
  gets this with an application token (client-credentials grant).
- Marketplace Insights (`buy/marketplace_insights/v1_beta/item_sales/search`): sold items,
  last 90 days. Limited Release: only works if eBay approved the app. We detect access by
  requesting its OAuth scope; eBay answers `invalid_scope` when the app isn't approved.
"""

from __future__ import annotations

import base64
import logging
import re
import statistics
import threading
import time
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.services.ingestion.parsing import parse_title

logger = logging.getLogger(__name__)

API = "https://api.ebay.com"
SCOPE_BROWSE = "https://api.ebay.com/oauth/api_scope"
SCOPE_INSIGHTS = "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"
SPORTS_CARD_SINGLES = "261328"  # Sports Mem, Cards & Fan Shop > Sports Trading Cards > Trading Card Singles
LISTING_CACHE_SECONDS = 600


class EbayNotConfigured(RuntimeError):
    pass


class EbayError(RuntimeError):
    pass


def ebay_enabled() -> bool:
    return bool(settings.ebay_client_id and settings.ebay_client_secret)


@dataclass
class _Token:
    value: str
    expires_at: float


_tokens: dict[str, _Token] = {}
_denied_scopes: dict[str, float] = {}  # scope -> time we learned it's not granted
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def _http() -> httpx.Client:
    return httpx.Client(timeout=20.0)


def get_token(scope: str = SCOPE_BROWSE) -> str | None:
    """Application token for `scope`; None if eBay says the app doesn't have that scope."""
    if not ebay_enabled():
        raise EbayNotConfigured("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET are not set")
    with _lock:
        tok = _tokens.get(scope)
        if tok and tok.expires_at - 60 > time.time():
            return tok.value
        denied_at = _denied_scopes.get(scope)
        if denied_at and time.time() - denied_at < 3600:
            return None

    basic = base64.b64encode(f"{settings.ebay_client_id}:{settings.ebay_client_secret}".encode()).decode()
    with _http() as c:
        r = c.post(
            f"{API}/identity/v1/oauth2/token",
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "scope": scope},
        )
    if r.status_code == 200:
        body = r.json()
        with _lock:
            _tokens[scope] = _Token(body["access_token"], time.time() + int(body.get("expires_in", 7200)))
        return body["access_token"]
    err = _safe_json(r)
    if r.status_code == 400 and err.get("error") == "invalid_scope":
        with _lock:
            _denied_scopes[scope] = time.time()
        return None
    if r.status_code == 401:
        raise EbayError("eBay rejected the credentials (check EBAY_CLIENT_ID / EBAY_CLIENT_SECRET, and that the keyset is enabled)")
    raise EbayError(f"eBay token error {r.status_code}: {err.get('error_description') or err.get('error') or r.text[:200]}")


def _safe_json(r: httpx.Response) -> dict:
    try:
        return r.json()
    except ValueError:
        return {}


def _get(path: str, params: dict, scope: str = SCOPE_BROWSE) -> dict | None:
    token = get_token(scope)
    if token is None:
        return None
    with _http() as c:
        r = c.get(
            f"{API}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
        )
    if r.status_code == 403 and scope == SCOPE_INSIGHTS:
        with _lock:
            _denied_scopes[scope] = time.time()
        return None
    if r.status_code >= 400:
        err = _safe_json(r).get("errors", [{}])[0]
        raise EbayError(f"eBay API error {r.status_code}: {err.get('message') or r.text[:200]}")
    return r.json()


# --------------------------------------------------------------------------- matching


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9/#]+", " ", s.lower())


def match_listing(title: str, target: dict | None) -> tuple[bool, list[str]]:
    """Heuristic: does this listing title describe the target card? Returns (exact, mismatches)."""
    if not target:
        return False, []
    t = f" {_norm(title)} "
    misses: list[str] = []
    player = (target.get("player") or "").lower().split()
    if player and player[-1] not in t:
        misses.append("player")
    year = str(target.get("year") or "")
    if year and year not in t:
        misses.append("year")
    num = (target.get("card_number") or "").lower().lstrip("#")
    if num and not re.search(rf"(#\s*{re.escape(num)}\b|\bno\.?\s*{re.escape(num)}\b|\s{re.escape(num)}\s)", t):
        misses.append("card #")
    parallel = (target.get("parallel") or "").lower()
    if parallel and parallel != "base" and not all(w in t for w in parallel.split()):
        misses.append("parallel")
    product = (target.get("product") or "").lower()
    for w in [w for w in product.split() if w not in {"panini", "topps", "upper", "deck"}]:
        if w not in t:
            misses.append("set")
            break
    grade = target.get("grade")
    if grade:
        p = parse_title(title)
        if grade.lower() == "raw":
            if not p.is_raw:
                misses.append("grade")
        elif f"{p.grader} {p.grade_value}" != grade.upper():
            misses.append("grade")
    return not misses, misses


# --------------------------------------------------------------------------- public API


def _grade_of(title: str) -> str:
    p = parse_title(title)
    return "Raw" if p.is_raw else f"{p.grader} {p.grade_value}"


def search_listings(query: str, target: dict | None = None, limit: int = 50) -> dict:
    key = f"{query}|{limit}|{sorted((target or {}).items())}"
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < LISTING_CACHE_SECONDS:
            return hit[1]

    browse = _get(
        "/buy/browse/v1/item_summary/search",
        {"q": query, "category_ids": SPORTS_CARD_SINGLES, "limit": str(limit)},
    ) or {}
    active = []
    for it in browse.get("itemSummaries", []) or []:
        title = it.get("title", "")
        bid = it.get("currentBidPrice") or {}
        price = it.get("price") or bid
        try:
            amount = float(price.get("value"))
        except (TypeError, ValueError):
            continue
        ship = None
        for so in it.get("shippingOptions") or []:
            try:
                ship = float((so.get("shippingCost") or {}).get("value"))
                break
            except (TypeError, ValueError):
                pass
        exact, misses = match_listing(title, target)
        active.append(
            {
                "item_id": it.get("itemId"),
                "title": title,
                "price": amount,
                "shipping": ship,
                "currency": price.get("currency", "USD"),
                "url": it.get("itemWebUrl"),
                "image": (it.get("image") or {}).get("imageUrl") or ((it.get("thumbnailImages") or [{}])[0].get("imageUrl")),
                "buying_options": it.get("buyingOptions") or [],
                "bid_count": it.get("bidCount"),
                "ends_at": it.get("itemEndDate"),
                "grade": _grade_of(title),
                "exact_match": exact,
                "mismatches": misses,
            }
        )

    sold = None
    insights = _get(
        "/buy/marketplace_insights/v1_beta/item_sales/search",
        {"q": query, "category_ids": SPORTS_CARD_SINGLES, "limit": str(min(limit, 50))},
        scope=SCOPE_INSIGHTS,
    )
    if insights is not None:
        sold = []
        for it in insights.get("itemSales", []) or []:
            title = it.get("title", "")
            try:
                amount = float((it.get("lastSoldPrice") or {}).get("value"))
            except (TypeError, ValueError):
                continue
            exact, misses = match_listing(title, target)
            sold.append(
                {
                    "item_id": it.get("itemId"),
                    "title": title,
                    "price": amount,
                    "date": (it.get("lastSoldDate") or "")[:10] or None,
                    "quantity": it.get("totalSoldQuantity"),
                    "url": it.get("itemWebUrl"),
                    "image": (it.get("image") or {}).get("imageUrl"),
                    "grade": _grade_of(title),
                    "exact_match": exact,
                    "mismatches": misses,
                }
            )

    def stats(rows: list[dict]) -> dict | None:
        prices = sorted(r["price"] for r in rows)
        if not prices:
            return None
        return {"count": len(prices), "low": prices[0], "median": round(statistics.median(prices), 2), "high": prices[-1]}

    exact_active = [a for a in active if a["exact_match"]]
    out = {
        "query": query,
        "active": sorted(active, key=lambda a: (not a["exact_match"], a["price"])),
        "active_stats": stats(exact_active) if target else stats(active),
        "sold": sold,
        "sold_stats": stats([s for s in sold if s["exact_match"]] if target else sold) if sold is not None else None,
        "insights_available": insights is not None,
        "total_found": browse.get("total"),
    }
    with _lock:
        _cache[key] = (time.time(), out)
    return out


def check_access() -> dict:
    """Live connectivity check used by /market/ebay/status (never returns secrets)."""
    out = {"configured": ebay_enabled(), "browse": False, "insights": False, "error": None}
    if not out["configured"]:
        return out
    try:
        out["browse"] = get_token(SCOPE_BROWSE) is not None
        out["insights"] = get_token(SCOPE_INSIGHTS) is not None
    except (EbayError, httpx.HTTPError) as exc:
        out["error"] = str(exc)
    return out
