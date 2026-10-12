import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Card, CardParallel, CardSet, Player
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
