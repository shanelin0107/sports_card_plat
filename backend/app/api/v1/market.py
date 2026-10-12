from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import AiPriceResearch, Card, CardParallel, CardSet, Player, SaleComp
from app.services import ebay
from app.services.comps import CompError, create_confirmed_comp

router = APIRouter(prefix="/market", tags=["market"])


def card_target(db: Session, card_id: int, grade: str | None) -> tuple[str, dict]:
    row = db.execute(
        select(Card, CardSet.name, Player.full_name)
        .join(CardSet, CardSet.id == Card.set_id)
        .join(Player, Player.id == Card.player_id)
        .where(Card.id == card_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Card not found")
    card, card_set, player = row
    parallels = [p for (p,) in db.execute(select(CardParallel.parallel_name).where(CardParallel.card_id == card_id)).all()]
    named = [p for p in parallels if p.lower() != "base"]
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


def _grade_text(g: str | None) -> str | None:
    if not g or g == "all":
        return None
    if g == "raw":
        return "Raw"
    if g.lower().startswith("psa"):
        return f"PSA {g[3:].strip()}"
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
            listing_id=body.item_id,
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
    db: Session = Depends(get_db),
):
    """Pull eBay sold history for one card and auto-save exact matches as comps.

    Only eBay's own sold records (Marketplace Insights) are auto-saved; listings that
    don't match the card exactly (player, year, set, #, parallel, grade) are skipped.
    """
    import time

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
                listing_id=s["item_id"],
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


AI_SYNC_INTERVAL = timedelta(hours=24)


def _ai_fallback(db: Session, background: BackgroundTasks, card_id: int, grade: str | None, force: bool) -> dict | None:
    """No eBay sold access: if the card has no sales in the last 30 days, let Claude look for
    them (at most once per card+grade per day) and auto-save exact, dated, verified sales."""
    from app.api.v1.ai import _card_context, start_job
    from app.services.ai_research import ai_enabled

    if not ai_enabled():
        return None
    gtext = _grade_text(grade)
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
