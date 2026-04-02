from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import CollectionItem
from app.schemas.collection import CollectionItemCreate, CollectionItemOut
from app.services.valuation import compute_card_valuation

router = APIRouter(prefix="/collection/items", tags=["collection"])
OWNER_PROFILE_ID = 1


def _to_out(db: Session, item: CollectionItem) -> CollectionItemOut:
    valuation = compute_card_valuation(db, item.card_id)
    estimated = (valuation["estimated_price"] or 0.0) * item.quantity
    cost = item.purchase_price * item.quantity
    return CollectionItemOut(
        id=item.id,
        owner_profile_id=item.owner_profile_id,
        card_id=item.card_id,
        card_parallel_id=item.card_parallel_id,
        grade_company_id=item.grade_company_id,
        grade_value=item.grade_value,
        is_graded=item.is_graded,
        quantity=item.quantity,
        purchase_price=item.purchase_price,
        purchase_date=item.purchase_date,
        condition=item.condition,
        notes=item.notes,
        image_url=item.image_url,
        uploaded_image_path=item.uploaded_image_path,
        estimated_value=round(estimated, 2),
        unrealized_pnl=round(estimated - cost, 2),
    )


@router.get("", response_model=list[CollectionItemOut])
def list_collection_items(db: Session = Depends(get_db)):
    items = db.scalars(select(CollectionItem).where(CollectionItem.owner_profile_id == OWNER_PROFILE_ID)).all()
    return [_to_out(db, item) for item in items]


@router.post("", response_model=CollectionItemOut)
def create_collection_item(payload: CollectionItemCreate, db: Session = Depends(get_db)):
    item = CollectionItem(owner_profile_id=OWNER_PROFILE_ID, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return _to_out(db, item)


@router.get("/{item_id}", response_model=CollectionItemOut)
def get_collection_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(CollectionItem, item_id)
    if not item or item.owner_profile_id != OWNER_PROFILE_ID:
        raise HTTPException(status_code=404, detail="Collection item not found")
    return _to_out(db, item)


@router.put("/{item_id}", response_model=CollectionItemOut)
def update_collection_item(item_id: int, payload: CollectionItemCreate, db: Session = Depends(get_db)):
    item = db.get(CollectionItem, item_id)
    if not item or item.owner_profile_id != OWNER_PROFILE_ID:
        raise HTTPException(status_code=404, detail="Collection item not found")

    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return _to_out(db, item)


@router.delete("/{item_id}")
def delete_collection_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(CollectionItem, item_id)
    if not item or item.owner_profile_id != OWNER_PROFILE_ID:
        raise HTTPException(status_code=404, detail="Collection item not found")
    db.delete(item)
    db.commit()
    return {"deleted": True}
