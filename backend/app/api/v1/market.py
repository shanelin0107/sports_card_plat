from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import settings
from app.models.entities import AiPriceResearch, Card, CardParallel, CardSet, MarketFetchLog, Player, SaleComp
from app.services import compsapi, ebay
from app.services.comps import CompError, create_confirmed_comp, ebay_item_id, listing_key

router = APIRouter(prefix="/market", tags=["market"])


def card_target(db: Session, card_id: int, grade: str | None, parallel_id: int | None = None) -> tuple[str, dict]:
    row = db.execute(
        select(Card, CardSet.name, Player.full_name)
        .join(CardSet, CardSet.id == Card.set_id)
        .join(Player, Player.id == Card.player_id)
        .where(Card.id == card_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Card not found")
    card, card_set, player = row
    rows = db.execute(select(CardParallel.id, CardParallel.parallel_name).where(CardParallel.card_id == card_id)).all()
    by_id = {pid: name for pid, name in rows}
    named = [n for n in by_id.values() if n.lower() != "base"]
    if parallel_id in by_id:  # the version the owner actually holds
        parallel = None if by_id[parallel_id].lower() == "base" else by_id[parallel_id]
    else:
        parallel = named[0] if len(named) == 1 else None
    target = {
        "player": player,
        "year": card.year,
        "product": card_set,
        "card_number": card.card_number,
        "parallel": parallel,
        "grade": grade,
    }
    # eBay's keyword search is AND-ish and punishes over-specific queries; keep it to the
    # identity words and let match_listing() decide what is an exact match.
    parts = [str(card.year), card_set, player, card.card_number]
    if parallel:
        parts.append(parallel)
    if grade and grade.lower() != "raw":
        parts.append(grade)
    return " ".join(parts), target


def _parallel_of(db: Session, card_id: int, parallel_id: int) -> bool:
    p = db.get(CardParallel, parallel_id)
    return p is not None and p.card_id == card_id


def _grade_text(g: str | None) -> str | None:
    if not g or g == "all":
        return None
    if g == "raw":
        return "Raw"
    import re

    m = re.match(r"^\s*(psa|bgs|beckett|sgc|cgc)\s*(\d+(?:\.5)?)\s*$", g, re.I)
    if m:
        company = "BGS" if m.group(1).lower() == "beckett" else m.group(1).upper()
        return f"{company} {m.group(2)}"
    return g


@router.get("/ebay/status")
def ebay_status():
    return ebay.check_access()


@router.get("/ebay/listings")
def ebay_listings(
    card_id: int | None = None,
    grade: str | None = Query(default=None, description="raw | psa10 | psa9 | all"),
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
):
    if not ebay.ebay_enabled():
        raise HTTPException(status_code=503, detail="eBay is off: set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET on the backend.")
    target = None
    if card_id is not None:
        query, target = card_target(db, card_id, _grade_text(grade))
        query = q or query
    elif q:
        query = q
    else:
        raise HTTPException(status_code=422, detail="Give card_id or q")
    try:
        return ebay.search_listings(query, target)
    except (ebay.EbayError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class SaveSoldIn(BaseModel):
    card_id: int
    item_id: str = Field(max_length=100)
    title: str = Field(max_length=500)
    url: str = Field(max_length=1000)
    price: float = Field(gt=0)
    date: str
    grade: str | None = None


@router.post("/ebay/save-sold")
def save_sold(body: SaveSoldIn, db: Session = Depends(get_db)):
    """Owner-confirmed eBay sold item (Marketplace Insights) -> comp."""
    if db.get(Card, body.card_id) is None:
        raise HTTPException(status_code=404, detail="Card not found")
    if not body.url.startswith("https://www.ebay.") and not body.url.startswith("https://ebay."):
        raise HTTPException(status_code=422, detail="Only eBay item URLs can be saved here")
    try:
        comp, created = create_confirmed_comp(
            db,
            card_id=body.card_id,
            listing_id=listing_key(body.url, body.item_id),
            title=body.title,
            url=body.url,
            price=body.price,
            date=body.date,
            grade=body.grade,
            source="eBay",
            match_method="ebay_insights_confirmed",
            payload=body.model_dump(),
        )
    except CompError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return {"sale_comp_id": comp.id, "already_saved": not created}


_last_sync: dict[tuple[int, str | None], float] = {}
SYNC_INTERVAL_SECONDS = 6 * 3600


@router.post("/sync/{card_id}")
def sync_card(
    card_id: int,
    background: BackgroundTasks,
    grade: str | None = None,
    force: bool = False,
    parallel_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Pull eBay sold history for one card and auto-save exact matches as comps.

    Only eBay's own sold records (Marketplace Insights) are auto-saved; listings that
    don't match the card exactly (player, year, set, #, parallel, grade) are skipped.
    """
    import time

    if compsapi.enabled():
        return _sync_compsapi(db, card_id, grade, force, parallel_id)
    if not ebay.ebay_enabled():
        return _ai_fallback(db, background, card_id, grade, force) or {"status": "ebay_off", "added": 0}
    key = (card_id, grade)
    if not force and time.time() - _last_sync.get(key, 0) < SYNC_INTERVAL_SECONDS:
        return {"status": "recent", "added": 0}
    query, target = card_target(db, card_id, _grade_text(grade))
    try:
        data = ebay.search_listings(query, target)
    except (ebay.EbayError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _last_sync[key] = time.time()
    if not data["insights_available"]:
        fb = _ai_fallback(db, background, card_id, grade, force)
        return fb or {"status": "no_sold_access", "added": 0, "active_listings": len(data["active"])}

    added = 0
    for s in data["sold"] or []:
        if not (s["exact_match"] and s["date"] and s["url"]):
            continue
        try:
            _, created = create_confirmed_comp(
                db,
                card_id=card_id,
                listing_id=listing_key(s["url"], s["item_id"]),
                title=s["title"],
                url=s["url"],
                price=s["price"],
                date=s["date"],
                grade=s["grade"],
                source="eBay",
                match_method="ebay_insights_auto",
                payload=s,
            )
            added += int(created)
        except CompError:
            continue
    db.commit()
    return {"status": "synced", "added": added, "sold_found": len(data["sold"] or [])}


def _sync_compsapi(db: Session, card_id: int, grade: str | None, force: bool, parallel_id: int | None = None) -> dict:
    """Pull sold history from CompsAPI and auto-save sales that match this exact card.

    Each call spends one request of the monthly quota, so a card+grade is fetched at most
    once per COMPSAPI_REFRESH_HOURS unless the owner presses the button (force).
    """
    gkey = (grade or "all").lower()
    last = db.scalars(
        select(MarketFetchLog)
        .where(MarketFetchLog.card_id == card_id, MarketFetchLog.grade == gkey, MarketFetchLog.source == "compsapi")
        .order_by(MarketFetchLog.fetched_at.desc())
    ).first()
    if last and not force and last.status in ("ok", "quota"):
        age = datetime.now(UTC) - last.fetched_at
        if age < timedelta(hours=settings.compsapi_refresh_hours):
            return {"status": "recent", "source": "compsapi", "added": 0, "fetched_at": last.fetched_at.isoformat()}

    gtext = _grade_text(grade)
    parallel_id = parallel_id if parallel_id and _parallel_of(db, card_id, parallel_id) else None
    query, target = card_target(db, card_id, None, parallel_id)  # grade goes in as a filter, not keywords
    target["grade"] = gtext
    log = MarketFetchLog(card_id=card_id, grade=gkey, source="compsapi", status="ok")
    try:
        data = compsapi.fetch_sold(query, target, gtext)
    except compsapi.QuotaReached as exc:
        log.status, log.error_message = "quota", str(exc)
        db.add(log)
        db.commit()
        return {"status": "quota", "source": "compsapi", "added": 0, "message": str(exc)}
    except (compsapi.CompsApiError, httpx.HTTPError) as exc:
        log.status, log.error_message = "error", str(exc)[:1000]
        db.add(log)
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    added = 0
    exact = [r for r in data["items"] if r["exact_match"] and r["date"]]
    for r in exact:
        try:
            _, created = create_confirmed_comp(
                db,
                card_id=card_id,
                listing_id=f"ebay-{r['item_id']}",  # same id a pasted eBay link gets, so no duplicates
                title=r["title"],
                url=r["url"],
                price=r["total"],
                date=r["sold_at"] or r["date"],
                grade=r["grade"],
                source="eBay",
                match_method="compsapi_auto",
                payload=r,
                card_parallel_id=parallel_id,
            )
            added += int(created)
        except CompError:
            continue  # removed earlier by the owner, or unusable
    log.found, log.added = len(data["items"]), added
    db.add(log)
    db.commit()
    # Closest misses first (fewest reasons), newest first within each group, so a sale the
    # matcher was too strict about is easy to spot and add by hand.
    skipped = [
        {"title": r["title"], "total": r["total"], "date": r["date"], "url": r["url"], "grade": r["grade"], "why": r["mismatches"]}
        for r in data["items"]
        if not r["exact_match"] and r["date"]
    ]
    skipped.sort(key=lambda x: x["date"], reverse=True)
    skipped.sort(key=lambda x: len(x["why"]))
    return {
        "status": "synced",
        "source": "compsapi",
        "query": data["query"],
        "found": len(data["items"]),
        "matched": len(exact),
        "added": added,
        "skipped": skipped[:25],
    }


@router.get("/compsapi/status")
def compsapi_status():
    """Is CompsAPI configured, and how much of this month's quota is used (free call)."""
    return compsapi.usage()


AI_SYNC_INTERVAL = timedelta(hours=24)


def _ai_fallback(db: Session, background: BackgroundTasks, card_id: int, grade: str | None, force: bool) -> dict | None:
    """No eBay sold access: if the card has no sales in the last 30 days, let Claude look for
    them (at most once per card+grade per day) and auto-save exact, dated, verified sales."""
    from app.api.v1.ai import _card_context, start_job
    from app.services.ai_research import ai_enabled

    if not ai_enabled():
        return None
    gtext = _grade_text(grade)
    from app.api.v1.ai import expire_stale_jobs

    expire_stale_jobs(db)
    running = db.scalars(
        select(AiPriceResearch).where(AiPriceResearch.card_id == card_id, AiPriceResearch.status == "running")
    ).first()
    if running:
        return {"status": "ai_running", "added": 0, "research_id": running.id}
    recent = db.scalars(
        select(AiPriceResearch)
        .where(
            AiPriceResearch.card_id == card_id,
            AiPriceResearch.grade.is_(None) if gtext is None else AiPriceResearch.grade == gtext,
            AiPriceResearch.created_at >= datetime.now(UTC) - AI_SYNC_INTERVAL,
        )
        .order_by(AiPriceResearch.created_at.desc())
    ).first()
    if recent and not force:
        return {"status": "ai_recent", "added": 0, "research_id": recent.id}
    stmt = select(SaleComp.id).where(SaleComp.card_id == card_id, SaleComp.sold_at >= datetime.now(UTC) - timedelta(days=30))
    if gtext:
        stmt = stmt.where(SaleComp.grade_value.is_(None) if gtext == "Raw" else SaleComp.grade_value == gtext.split()[-1])
    if db.scalars(stmt).first() and not force:
        return None  # already have recent sales; don't spend money
    query, ctx = _card_context(db, card_id)
    job = start_job(db, background, query=query, card_id=card_id, grade=gtext, ctx=ctx, auto_save=True)
    return {"status": "ai_started", "added": 0, "research_id": job.id}


@router.get("/ebay/item/{item_id}")
def ebay_item(item_id: str):
    """One listing with its seller-entered item specifics mapped to catalog fields."""
    if not ebay.ebay_enabled():
        raise HTTPException(status_code=503, detail="eBay is off: set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET on the backend.")
    try:
        return ebay.get_item(item_id)
    except (ebay.EbayError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# --------------------------------------------------------------------------- manual sales


def _sold_query(card_id: int, grade: str | None, db: Session) -> str:
    query, _ = card_target(db, card_id, _grade_text(grade))
    return query


@router.get("/sold-links/{card_id}")
def sold_links(card_id: int, grade: str | None = None, db: Session = Depends(get_db)):
    """Where to look up this card's sold prices by hand (eBay sold, Terapeak, 130point)."""
    from urllib.parse import quote_plus

    q = _sold_query(card_id, grade, db)
    enc = quote_plus(q)
    return {
        "query": q,
        "links": [
            {"name": "eBay sold", "url": f"https://www.ebay.com/sch/i.html?_nkw={enc}&_sacat=261328&LH_Sold=1&LH_Complete=1&_sop=13",
             "note": "Last 90 days on eBay.com (may ask you to sign in)"},
            {"name": "Terapeak", "url": f"https://www.ebay.com/sh/research?marketplace=EBAY-US&keywords={enc}&tabName=SOLD&dayRange=90",
             "note": "Seller Hub research, up to 3 years (needs your eBay seller login)"},
            {"name": "130point", "url": "https://130point.com/sales/",
             "note": "Shows real Best Offer prices; paste the search text"},
        ],
    }


class ManualSaleIn(BaseModel):
    price: float = Field(gt=0, le=10_000_000)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    grade: str | None = Field(default=None, max_length=20, description='"Raw" or e.g. "PSA 10"')
    shipping: float | None = Field(default=None, ge=0)
    url: str | None = Field(default=None, max_length=1000)
    title: str | None = Field(default=None, max_length=500)
    source: str | None = Field(default=None, max_length=50)
    card_parallel_id: int | None = None


@router.post("/sales/{card_id}", status_code=201)
def add_manual_sale(card_id: int, body: ManualSaleIn, db: Session = Depends(get_db)):
    """Owner-entered sale (e.g. seen on eBay sold / 130point). Becomes a comp immediately."""
    import uuid
    from datetime import date as _date

    if db.get(Card, card_id) is None:
        raise HTTPException(status_code=404, detail="Card not found")
    if _date.fromisoformat(body.date) > _date.today():
        raise HTTPException(status_code=422, detail="Sale date is in the future")
    url = (body.url or "").strip()
    if url and not url.startswith(("https://", "http://")):
        raise HTTPException(status_code=422, detail="Link must start with https://")
    m = ebay_item_id(url)
    listing_id = listing_key(url, f"manual-{uuid.uuid4().hex[:12]}")
    total = round(body.price + (body.shipping or 0), 2)
    try:
        comp, created = create_confirmed_comp(
            db,
            card_id=card_id,
            listing_id=listing_id,
            title=body.title or "",
            url=url,
            price=total,
            date=body.date,
            grade=body.grade or "Raw",
            source=body.source or ("eBay" if m else "Manual"),
            match_method="manual_entry",
            payload=body.model_dump(),
            restore_removed=True,  # adding by hand is an explicit "yes, this one counts"
            card_parallel_id=body.card_parallel_id if body.card_parallel_id and _parallel_of(db, card_id, body.card_parallel_id) else None,
        )
    except CompError as exc:
        raise HTTPException(status_code=409 if "already" in str(exc) else 422, detail=str(exc)) from exc
    db.commit()
    if not created:
        raise HTTPException(status_code=409, detail="That eBay sale is already on this card")
    return {"sale_comp_id": comp.id, "total_price": total}
