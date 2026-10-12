from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Card, CardParallel, CollectionItem, GradeCompany
from app.schemas.collection import CollectionItemCreate, CollectionItemOut
from app.services.portfolio import OWNER_PROFILE_ID, load_holdings

router = APIRouter(prefix="/collection/items", tags=["collection"])


def _validate_refs(db: Session, payload: CollectionItemCreate) -> None:
    if db.get(Card, payload.card_id) is None:
        raise HTTPException(status_code=422, detail=f"Card {payload.card_id} does not exist")
    if payload.card_parallel_id is not None:
        parallel = db.get(CardParallel, payload.card_parallel_id)
        if parallel is None or parallel.card_id != payload.card_id:
            raise HTTPException(status_code=422, detail="Parallel does not belong to this card")
    if payload.grade_company_id is not None and db.get(GradeCompany, payload.grade_company_id) is None:
        raise HTTPException(status_code=422, detail="Unknown grading company")


def _get_owned(db: Session, item_id: int) -> CollectionItem:
    item = db.get(CollectionItem, item_id)
    if not item or item.owner_profile_id != OWNER_PROFILE_ID:
        raise HTTPException(status_code=404, detail="Collection item not found")
    return item


def _one(db: Session, item_id: int) -> CollectionItemOut:
    return load_holdings(db, [item_id])[0]


@router.get("", response_model=list[CollectionItemOut])
def list_collection_items(db: Session = Depends(get_db)):
    return load_holdings(db)


@router.post("", response_model=CollectionItemOut, status_code=201)
def create_collection_item(payload: CollectionItemCreate, db: Session = Depends(get_db)):
    _validate_refs(db, payload)
    item = CollectionItem(owner_profile_id=OWNER_PROFILE_ID, **payload.model_dump())
    db.add(item)
    db.commit()
    return _one(db, item.id)


@router.get("/{item_id}", response_model=CollectionItemOut)
def get_collection_item(item_id: int, db: Session = Depends(get_db)):
    _get_owned(db, item_id)
    return _one(db, item_id)


@router.put("/{item_id}", response_model=CollectionItemOut)
def update_collection_item(item_id: int, payload: CollectionItemCreate, db: Session = Depends(get_db)):
    item = _get_owned(db, item_id)
    _validate_refs(db, payload)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return _one(db, item_id)


@router.delete("/{item_id}")
def delete_collection_item(item_id: int, db: Session = Depends(get_db)):
    item = _get_owned(db, item_id)
    db.delete(item)
    db.commit()
    return {"deleted": True}
