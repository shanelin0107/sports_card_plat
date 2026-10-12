"""Catalog management: lets the owner add their own cards instead of only the 2 seeded ones."""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Brand, Card, CardParallel, CardSet, GradeCompany, Player, Sport

router = APIRouter(prefix="/catalog", tags=["catalog"])


class CardCreate(BaseModel):
    sport: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=1880, le=2100)
    brand: str = Field(min_length=1, max_length=100)
    set_name: str = Field(min_length=1, max_length=150)
    player: str = Field(min_length=1, max_length=150)
    card_number: str = Field(min_length=1, max_length=50)
    parallel: str = Field(default="Base", max_length=100)
    rookie: bool = False
    autograph: bool = False
    patch: bool = False
    image_url: str | None = None


def _get_or_create(db: Session, model, lookup: dict, extra: dict | None = None):
    stmt = select(model)
    for k, v in lookup.items():
        col = getattr(model, k)
        stmt = stmt.where(func.lower(col) == v.lower()) if isinstance(v, str) else stmt.where(col == v)
    obj = db.scalars(stmt).first()
    if obj:
        return obj
    obj = model(**lookup, **(extra or {}))
    db.add(obj)
    db.flush()
    return obj


def _slug(*parts) -> str:
    return re.sub(r"[^a-z0-9]+", "-", " ".join(str(p) for p in parts).lower()).strip("-")


@router.get("/grade-companies")
def grade_companies(db: Session = Depends(get_db)):
    return [{"id": i, "name": n} for i, n in db.execute(select(GradeCompany.id, GradeCompany.name).order_by(GradeCompany.id)).all()]


@router.get("/cards/{card_id}/parallels")
def card_parallels(card_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        select(CardParallel.id, CardParallel.parallel_name, CardParallel.variation_name).where(CardParallel.card_id == card_id)
    ).all()
    return [{"id": i, "parallel_name": p, "variation_name": v} for i, p, v in rows]


@router.post("/cards", status_code=201)
def create_card(body: CardCreate, db: Session = Depends(get_db)):
    sport = _get_or_create(db, Sport, {"name": body.sport.strip().title()})
    brand = _get_or_create(db, Brand, {"name": body.brand.strip()})
    set_name = body.set_name.strip()
    if not set_name.lower().startswith(brand.name.lower()):
        set_name = f"{brand.name} {set_name}"
    card_set = _get_or_create(
        db, CardSet, {"name": set_name, "release_year": body.year, "brand_id": brand.id}, {"sport_id": sport.id}
    )
    player = _get_or_create(db, Player, {"full_name": body.player.strip()}, {"sport_id": sport.id})
    number = body.card_number.strip().lstrip("#")
    parallel_name = body.parallel.strip() or "Base"

    slug = _slug(body.year, set_name, player.full_name, number)
    card = db.scalars(select(Card).where(Card.slug == slug)).first()
    created = card is None
    if created:
        title = f"{body.year} {set_name} {player.full_name} #{number}" + (" RC" if body.rookie else "")
        card = Card(
            sport_id=sport.id,
            year=body.year,
            brand_id=brand.id,
            set_id=card_set.id,
            player_id=player.id,
            card_number=number,
            title=title,
            slug=slug,
            search_text_normalized=" ".join(
                [str(body.year), set_name.lower(), player.full_name.lower(), number.lower(), "rc rookie" if body.rookie else "", "auto" if body.autograph else ""]
            ).strip(),
            default_image_url=body.image_url,
            rookie_flag=body.rookie,
            autograph_flag=body.autograph,
            patch_flag=body.patch,
        )
        db.add(card)
        db.flush()

    parallel = db.scalars(
        select(CardParallel).where(CardParallel.card_id == card.id, func.lower(CardParallel.parallel_name) == parallel_name.lower())
    ).first()
    if parallel is None:
        parallel = CardParallel(card_id=card.id, parallel_name=parallel_name, variation_name="Base")
        db.add(parallel)
        db.flush()
        if parallel_name.lower() != "base" and parallel_name.lower() not in card.search_text_normalized:
            card.search_text_normalized += f" {parallel_name.lower()}"

    db.commit()
    return {"card_id": card.id, "card_parallel_id": parallel.id, "title": card.title, "created": created}


class CardImageIn(BaseModel):
    image_url: str | None = Field(default=None, max_length=1000)


@router.put("/cards/{card_id}/image")
def set_card_image(card_id: int, body: CardImageIn, db: Session = Depends(get_db)):
    """Set (or clear) the catalog image, e.g. from an eBay listing photo."""
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    if body.image_url and not body.image_url.startswith("https://"):
        raise HTTPException(status_code=422, detail="Image URL must be https")
    card.default_image_url = body.image_url or None
    db.commit()
    return {"card_id": card_id, "default_image_url": card.default_image_url}
