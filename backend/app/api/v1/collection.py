import base64
import binascii
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Card, CardParallel, CollectionItem, CollectionItemPhoto, GradeCompany
from app.schemas.collection import CollectionItemCreate, CollectionItemOut, PhotoUpload
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


MAX_PHOTO_BYTES = 3 * 1024 * 1024
_MAGIC = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


@router.put("/{item_id}/photo", response_model=CollectionItemOut)
def upload_photo(item_id: int, body: PhotoUpload, db: Session = Depends(get_db)):
    _get_owned(db, item_id)
    try:
        data = base64.b64decode(body.data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Photo is not valid base64") from exc
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo must be under 3 MB")
    if not data.startswith(_MAGIC[body.content_type]):
        raise HTTPException(status_code=422, detail="File content does not match its image type")

    photo = db.get(CollectionItemPhoto, item_id)
    if photo is None:
        photo = CollectionItemPhoto(collection_item_id=item_id, content_type=body.content_type, data=data)
        db.add(photo)
    else:
        photo.content_type = body.content_type
        photo.data = data
        photo.updated_at = datetime.now(UTC)
    db.commit()
    return _one(db, item_id)


@router.get("/{item_id}/photo")
def get_photo(item_id: int, db: Session = Depends(get_db)):
    _get_owned(db, item_id)
    photo = db.get(CollectionItemPhoto, item_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="No photo")
    # URLs carry ?v=<updated_at>, so the bytes behind a given URL never change.
    return Response(
        content=photo.data,
        media_type=photo.content_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{item_id}/photo", response_model=CollectionItemOut)
def delete_photo(item_id: int, db: Session = Depends(get_db)):
    _get_owned(db, item_id)
    photo = db.get(CollectionItemPhoto, item_id)
    if photo is not None:
        db.delete(photo)
        db.commit()
    return _one(db, item_id)
