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
            f"{settings.ebay_api_base}/identity/v1/oauth2/token",
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
            f"{settings.ebay_api_base}{path}",
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
    t = re.sub(r"[^a-z0-9/#]+", " ", s.lower())
    t = re.sub(r"\bformula (1|one)\b", "f1", t)  # "Formula 1" / "Formula One" / "F1" are one word
    # Parallel names sellers split or join either way: "Ray Wave" = "RayWave", "X Fractor" = "Xfractor".
    return re.sub(r"\b(ray|x|sepia|tie) (wave|fractor|dye)\b", r"\1\2", t)


# Generic parallel words sellers often leave out ("Orange Raywave Auto" for an Orange RayWave
# Refractor): only the distinctive words of a parallel name have to appear in a title.
_GENERIC_PARALLEL = {"refractor", "refractors", "prizm", "prizms", "parallel", "chrome"}
_SERIAL = re.compile(r"(?<![\d.])(?:\d{1,4})?\s*/\s*(\d{1,4})\b")  # "/25", "12/25", "#/25"
_ANY_NUMBER = re.compile(r"#\s*[a-z0-9]")


# Words that mean a listing is a parallel/variation, not the base card.
_PARALLEL_WORDS = re.compile(
    r"\b(silver|holo|refractor|lazer|laser|mojo|wave|shimmer|hyper|disco|ice|camo|scope|cracked|"
    r"gold|red|blue|green|orange|purple|pink|black|white|neon|tie[ -]?dye|snakeskin|velocity|"
    r"pulsar|choice|fast break|no huddle|sp|ssp|variation|var|auto|autograph|patch|numbered)\b"
    r"|/\s*\d{1,4}\b"
)
_TEAMS = re.compile(
    r"\b(red sox|white sox|blue jays|red wings|blue jackets|golden state|vegas golden knights|orange county"
    r"|red bull|oracle red bull|racing bulls|visa cash app rb|black arrows)\b"  # F1 teams with colour words
)
# Listings that are never a single-card sale.
_JUNK = re.compile(r"\b(lot|lots|reprint|custom|digital|break|case|box|pack|you pick|u pick|choose)\b")


_SELF_WORDS = re.compile(r"\b(auto|autos|autograph|autographs|autographed|signed|signature|patch|relic|jersey|rpa)\b")


def _number_in(num: str, t: str) -> bool:
    """Card number in a normalised title. Hyphens/spaces inside the number are optional,
    so TAIR-DH matches "TAIR-DH", "TAIR DH" and "TAIRDH"."""
    parts = [re.escape(x) for x in re.split(r"[^a-z0-9]+", num) if x]
    if not parts:
        return True
    core = r"[\s\-]?".join(parts)
    if num.isdigit():  # plain numbers need a marker or spaces around them ("#329", " 329 ")
        return bool(re.search(rf"(#\s*{core}\b|\bno\.?\s*{core}\b|\s{core}\s)", t))
    return bool(re.search(rf"(?<![a-z0-9]){core}(?![a-z0-9])", t))


_COLOURS = {
    "silver", "gold", "red", "blue", "green", "orange", "purple", "pink", "black", "white", "bronze", "teal",
    "yellow", "aqua", "neon", "sapphire", "emerald", "ruby",
}


def search_query(year, card_set: str, player: str, card_number: str | None, parallel: str | None) -> str:
    """Keywords for a sold-listings search. eBay-style search needs EVERY word in the title,
    and sellers skip or vary a lot (insert codes, "Refractor", "F1" vs "Formula 1",
    "RayWave" vs "Ray Wave"), so only send words a matching title almost always has —
    year, set, player, the parallel's colour — and let match_listing() check the rest."""
    set_words = [w for w in card_set.split() if w.lower() not in {"f1", "formula", "1", "one"}]
    parts = [str(year), *set_words, player]
    par = [w for w in (parallel or "").split() if w.lower() not in _GENERIC_PARALLEL | {"base"}]
    colours = [w for w in par if w.lower() in _COLOURS]
    if par:
        parts.extend(colours or par[:1])
    elif card_number and card_number.isdigit():
        parts.append(card_number)  # base card: the number keeps parallels/inserts out
    return " ".join(parts)


def match_listing(title: str, target: dict | None, strict_base: bool = False) -> tuple[bool, list[str]]:
    """Heuristic: does this listing title describe the target card? Returns (exact, mismatches).

    strict_base: for a base card (no parallel), reject titles that name a parallel/variation,
    and reject lots, reprints, breaks and sealed product.
    """
    if not target:
        return False, []
    t = f" {_norm(title)} "
    misses: list[str] = []
    if strict_base and _JUNK.search(t):
        misses.append("not a single card")
    player = (target.get("player") or "").lower().split()
    if player and player[-1] not in t:
        misses.append("player")
    year = str(target.get("year") or "")
    if year and year not in t:
        misses.append("year")
    num = (target.get("card_number") or "").lower().lstrip("#")
    parallel = _norm(target.get("parallel") or "").strip()
    print_run = target.get("print_run")
    if num and not _number_in(num, t):
        # A title that names a different number is a different card. A title with no number
        # at all is common (sellers skip insert codes like CAC-BEA): accept it when the card
        # is otherwise specific (a named parallel or a print run) or the number is a code.
        specific = (parallel and parallel != "base") or print_run or not num.isdigit()
        if _ANY_NUMBER.search(t) or not specific:
            misses.append("card #")
    if print_run:
        serials = {int(m) for m in _SERIAL.findall(t)}
        if serials and int(print_run) not in serials:
            misses.append("print run")  # /50 is not /25
    if parallel and parallel != "base":
        words = parallel.split()
        need = [w for w in words if w not in _GENERIC_PARALLEL] or words
        if not all(f" {w} " in t for w in need):
            misses.append("parallel")
    elif strict_base and (not parallel or parallel == "base"):
        # Ignore words that belong to the player, the set ("Prizm Black") or a team ("Red Sox").
        rest = _TEAMS.sub(" ", t)
        for w in f"{target.get('player') or ''} {target.get('product') or ''}".lower().split():
            rest = rest.replace(f" {w} ", " ")
        # Insert / autograph cards (letters in the number, e.g. TAIR-DH, RA-JD) are autos
        # or memorabilia by nature, so "Auto" / "Patch" in the title is the card itself.
        if not num.isdigit():
            rest = _SELF_WORDS.sub(" ", rest)
        if _PARALLEL_WORDS.search(rest):
            misses.append("parallel")
    product = _norm(target.get("product") or "").strip()
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


def hires(url: str | None) -> str | None:
    """eBay image URLs embed a size (s-l225); ask for a sharper one."""
    return re.sub(r"/s-l\d+\.", "/s-l800.", url) if url else url


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
                "image": hires((it.get("image") or {}).get("imageUrl") or ((it.get("thumbnailImages") or [{}])[0].get("imageUrl"))),
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
                    "image": hires((it.get("image") or {}).get("imageUrl")),
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


# --------------------------------------------------------------------------- item details

_GRADERS = {
    "psa": "PSA", "professional sports authenticator": "PSA",
    "bgs": "BGS", "beckett": "BGS", "sgc": "SGC", "cgc": "CGC", "csg": "CGC",
}


def _aspect_map(item: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for a in item.get("localizedAspects") or []:
        name = (a.get("name") or "").strip().lower()
        val = (a.get("value") or "").strip()
        if name and val:
            out[name] = val
    return out


def _sport_name(s: str) -> str:
    from app.api.v1.catalog import normalize_sport

    return normalize_sport(s)


def card_fields_from_item(item: dict) -> dict:
    """Map eBay item specifics (seller-entered) to our catalog fields, falling back to the title."""
    from app.services.ingestion.parsing import parse_title

    a = _aspect_map(item)
    title = item.get("title") or ""
    parsed = parse_title(title)

    def first(*keys):
        for k in keys:
            if a.get(k):
                # sellers sometimes bracket values: "[Base]" -> "Base"
                v = a[k].strip().strip("[]()").strip()
                return v or None
        return None

    year = None
    for raw in (first("season", "year manufactured", "year"), title):
        m = re.search(r"(19|20)\d{2}", raw or "")
        if m:
            year = int(m.group(0))
            break

    manufacturer = first("manufacturer", "brand")
    set_name = first("set", "product")
    if set_name:  # "2024-25 Panini Prizm Black" -> "Prizm Black"
        set_name = re.sub(r"^\s*(19|20)\d{2}(\s*[-/]\s*\d{2,4})?\s*", "", set_name).strip() or set_name
    if set_name and manufacturer and set_name.lower().startswith(manufacturer.lower() + " "):
        set_name = set_name[len(manufacturer):].strip(" -") or set_name

    number = first("card number")
    if number:
        number = number.lstrip("#").strip()
    elif parsed.card_number:
        number = parsed.card_number

    print_run = None
    pr = first("print run")
    m = re.search(r"(\d+)", pr or "")
    if m:
        print_run = int(m.group(1))
    else:
        m = re.search(r"/\s*(\d{1,4})\b", title)
        if m:
            print_run = int(m.group(1))

    grader = None
    grade_value = None
    graded = (first("graded") or "").lower()
    if graded == "yes" or first("professional grader"):
        g = (first("professional grader") or "").lower()
        grader = next((v for k, v in _GRADERS.items() if k in g), None)
        gv = first("grade")
        m = re.search(r"\d+(\.5)?", gv or "")
        grade_value = m.group(0) if m else None
    if not grade_value and not parsed.is_raw:
        grader, grade_value = parsed.grader, parsed.grade_value

    features = (first("features", "card attributes") or "").lower()
    autographed = (first("autographed") or "").lower() == "yes" or "auto" in features
    sport = first("sport")
    return {
        "sport": _sport_name(sport) if sport else None,
        "year": year,
        "brand": manufacturer,
        "set_name": set_name,
        "player": first("player/athlete", "player", "athlete"),
        "card_number": number,
        "parallel": first("parallel/variety", "parallel"),
        "print_run": print_run,
        "rookie": "rookie" in features or bool(re.search(r"\b(rc|rookie)\b", title, re.I)),
        "autograph": autographed,
        "grader": grader,
        "grade_value": grade_value,
    }


def get_item(item_id: str) -> dict:
    from urllib.parse import quote

    data = _get(f"/buy/browse/v1/item/{quote(item_id, safe='')}", {})
    if data is None:
        raise EbayError("Item not available")
    price = data.get("price") or {}
    return {
        "item_id": data.get("itemId", item_id),
        "title": data.get("title"),
        "price": float(price["value"]) if price.get("value") else None,
        "url": data.get("itemWebUrl"),
        "image": hires((data.get("image") or {}).get("imageUrl")),
        "card": card_fields_from_item(data),
        "aspects": _aspect_map(data),
    }
