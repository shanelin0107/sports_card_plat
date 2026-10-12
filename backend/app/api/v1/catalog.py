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
    print_run: int | None = Field(default=None, ge=1, le=100000)
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


def clean_player(name: str) -> str:
    """Drop serial numbers / card numbers that sneak into a pasted name ("Damian Lillard /60")."""
    words = [w for w in name.split() if not re.search(r"[\d/#]", w)]
    return " ".join(words).strip() or name.strip()


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


def upsert_card(db: Session, body: CardCreate):
    """Find or create the catalog card (and parallel) described by `body`. Caller commits."""
    sport = _get_or_create(db, Sport, {"name": body.sport.strip().title()})
    brand = _get_or_create(db, Brand, {"name": body.brand.strip()})
    set_name = body.set_name.strip()
    if not set_name.lower().startswith(brand.name.lower()):
        set_name = f"{brand.name} {set_name}"
    card_set = _get_or_create(
        db, CardSet, {"name": set_name, "release_year": body.year, "brand_id": brand.id}, {"sport_id": sport.id}
    )
    player = _get_or_create(db, Player, {"full_name": clean_player(body.player)}, {"sport_id": sport.id})
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
        parallel = CardParallel(card_id=card.id, parallel_name=parallel_name, variation_name="Base", print_run=body.print_run)
        db.add(parallel)
        db.flush()
        if parallel_name.lower() != "base" and parallel_name.lower() not in card.search_text_normalized:
            card.search_text_normalized += f" {parallel_name.lower()}"

    return card, parallel, created


@router.post("/cards", status_code=201)
def create_card(body: CardCreate, db: Session = Depends(get_db)):
    card, parallel, created = upsert_card(db, body)
    db.commit()
    return {"card_id": card.id, "card_parallel_id": parallel.id, "title": card.title, "created": created}


class CardImageIn(BaseModel):
    image_url: str | None = Field(default=None, max_length=1000)


@router.put("/cards/{card_id}/image")
def set_card_image(card_id: int, body: CardImageIn, only_if_empty: bool = False, db: Session = Depends(get_db)):
    """Set (or clear) the catalog image, e.g. from an eBay listing photo."""
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    if only_if_empty and card.default_image_url:
        return {"card_id": card_id, "default_image_url": card.default_image_url}
    if body.image_url and not body.image_url.startswith("https://"):
        raise HTTPException(status_code=422, detail="Image URL must be https")
    card.default_image_url = body.image_url or None
    db.commit()
    return {"card_id": card_id, "default_image_url": card.default_image_url}


class CardEdit(BaseModel):
    player: str | None = Field(default=None, max_length=150)
    year: int | None = Field(default=None, ge=1880, le=2100)
    card_number: str | None = Field(default=None, max_length=50)
    set_name: str | None = Field(default=None, max_length=150)
    parallel: str | None = Field(default=None, max_length=100)
    print_run: int | None = Field(default=None, ge=1, le=100000)
    rookie: bool | None = None


@router.patch("/cards/{card_id}")
def edit_card(card_id: int, body: CardEdit, db: Session = Depends(get_db)):
    """Fix a catalog card's details (e.g. a mistyped player name)."""
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    if body.player:
        name = clean_player(body.player)
        player = db.get(Player, card.player_id)
        others = db.scalars(select(Card.id).where(Card.player_id == card.player_id, Card.id != card_id)).first()
        if others is None:
            player.full_name = name  # only this card uses the record: rename it
        else:
            card.player_id = _get_or_create(db, Player, {"full_name": name}, {"sport_id": card.sport_id}).id
    if body.year:
        card.year = body.year
    if body.card_number:
        card.card_number = body.card_number.strip().lstrip("#")
    if body.set_name:
        cs = db.get(CardSet, card.set_id)
        brand = db.get(Brand, card.brand_id)
        name = body.set_name.strip()
        if not name.lower().startswith(brand.name.lower()):
            name = f"{brand.name} {name}"
        card.set_id = _get_or_create(db, CardSet, {"name": name, "release_year": card.year, "brand_id": card.brand_id}, {"sport_id": cs.sport_id}).id
    if body.rookie is not None:
        card.rookie_flag = body.rookie
    if body.parallel is not None or body.print_run is not None:
        parallels = db.scalars(select(CardParallel).where(CardParallel.card_id == card_id)).all()
        target = next((p for p in parallels if p.parallel_name.lower() != "base"), parallels[0] if parallels else None)
        if target is None:
            target = CardParallel(card_id=card_id, parallel_name=body.parallel or "Base", variation_name="Base")
            db.add(target)
        if body.parallel:
            target.parallel_name = body.parallel.strip()
        if body.print_run is not None:
            target.print_run = body.print_run
    db.flush()
    # rebuild display title + search text
    cs = db.get(CardSet, card.set_id)
    player = db.get(Player, card.player_id)
    par = db.scalars(select(CardParallel).where(CardParallel.card_id == card_id, CardParallel.parallel_name != "Base")).first()
    card.title = f"{card.year} {cs.name} {player.full_name} #{card.card_number}" + (" RC" if card.rookie_flag else "")
    card.search_text_normalized = " ".join(
        x for x in [str(card.year), cs.name.lower(), player.full_name.lower(), card.card_number.lower(),
                    "rc rookie" if card.rookie_flag else "", par.parallel_name.lower() if par else ""] if x
    )
    db.commit()
    return {"card_id": card.id, "title": card.title, "player": player.full_name, "parallel": par.parallel_name if par else "Base",
            "print_run": par.print_run if par else None}
