"""Insert / SSP set guide: checklists with pack odds per box type, click-to-price."""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import compsapi, set_guide, set_import

router = APIRouter(prefix="/sets", tags=["sets"])


@router.get("")
def products(db: Session = Depends(get_db)):
    return set_guide.list_products(db)


@router.get("/{product_id}")
def product(product_id: int, db: Session = Depends(get_db)):
    p = set_guide.product_detail(db, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Set not found")
    return p


class BoxEdit(BaseModel):
    packs_per_box: int | None = Field(default=None, ge=1, le=1000)
    boxes_per_case: int | None = Field(default=None, ge=1, le=1000)


@router.patch("/{product_id}/box-types/{box_id}")
def edit_box(product_id: int, box_id: int, body: BoxEdit, db: Session = Depends(get_db)):
    """Packs per box differ between printings (e.g. a 6- vs 7-pack Mega): let the owner fix it."""
    n = db.execute(
        text(
            "UPDATE set_box_type SET packs_per_box = COALESCE(:ppb, packs_per_box), boxes_per_case = COALESCE(:bpc, boxes_per_case) "
            "WHERE id = :id AND product_id = :p"
        ),
        {"ppb": body.packs_per_box, "bpc": body.boxes_per_case, "id": box_id, "p": product_id},
    ).rowcount
    db.commit()
    if not n:
        raise HTTPException(status_code=404, detail="Box type not found")
    return {"ok": True}


@router.post("/cards/{card_id}/price")
def price(card_id: int, parallel_id: int, force: bool = False, db: Session = Depends(get_db)):
    """Sold prices for a checklist card in one parallel. Saved for 7 days: opening it again
    costs no CompsAPI quota unless `force` (↻)."""
    try:
        return set_guide.price_check(db, card_id, parallel_id, force)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except compsapi.QuotaReached as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except compsapi.Unavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except compsapi.CompsApiError as exc:
        raise HTTPException(status_code=exc.status if exc.status == 503 else 502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/inserts/{insert_id}/photos")
def photos(insert_id: int, force: bool = False, db: Session = Depends(get_db)):
    """Card photos for a whole insert from one search (done once per insert)."""
    try:
        return set_guide.load_photos(db, insert_id, force)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except compsapi.QuotaReached as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except compsapi.CompsApiError as exc:
        raise HTTPException(status_code=503 if exc.status == 503 else 502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class ImportIn(BaseModel):
    name: str = Field(min_length=6, max_length=150)
    checklist_url: str | None = Field(default=None, max_length=500)
    odds_url: str | None = Field(default=None, max_length=500)


@router.post("/import")
def import_set(body: ImportIn, db: Session = Depends(get_db)):
    """Read a checklist page and an odds page with Playwright and save what was found."""
    for u in (body.checklist_url, body.odds_url):
        if u and not u.startswith(("https://", "http://")):
            raise HTTPException(status_code=422, detail="Pages must be http(s) links")
    try:
        return set_import.run_import(db, body.name, body.checklist_url, body.odds_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
