"""Collection valuation shared by the collection and dashboard endpoints."""

from __future__ import annotations

import statistics
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Brand,
    Card,
    CardParallel,
    CardSet,
    CollectionItem,
    CollectionItemPhoto,
    GradeCompany,
    Player,
    ValuationSnapshot,
)
from app.schemas.collection import CollectionItemOut
from app.services.valuation import GradeKey, ValuationEngine, ValuationKey, grade_key_for_item

OWNER_PROFILE_ID = 1
SNAPSHOT_WINDOW_DAYS = 90
SPARK_POINTS = 8


def grade_company_names(db: Session) -> dict[int, str]:
    return {gid: name for gid, name in db.execute(select(GradeCompany.id, GradeCompany.name)).all()}


def grade_label(key: GradeKey, names: dict[int, str]) -> str:
    if key.is_raw:
        return "Raw"
    company = names.get(key.grade_company_id or -1, "")
    return f"{company} {key.grade_value}".strip()


def load_holdings(db: Session, item_ids: list[int] | None = None) -> list[CollectionItemOut]:
    stmt = (
        select(CollectionItem, Card, Brand.name, CardSet.name, Player.full_name, CardParallel.parallel_name)
        .join(Card, Card.id == CollectionItem.card_id)
        .join(Brand, Brand.id == Card.brand_id)
        .join(CardSet, CardSet.id == Card.set_id)
        .join(Player, Player.id == Card.player_id)
        .outerjoin(CardParallel, CardParallel.id == CollectionItem.card_parallel_id)
        .where(CollectionItem.owner_profile_id == OWNER_PROFILE_ID)
        .order_by(CollectionItem.created_at.desc(), CollectionItem.id.desc())
    )
    if item_ids is not None:
        stmt = stmt.where(CollectionItem.id.in_(item_ids))
    rows = db.execute(stmt).all()
    if not rows:
        return []

    names = grade_company_names(db)
    engine = ValuationEngine(db, {item.card_id for item, *_ in rows})
    photo_versions = {
        iid: str(int(ts.timestamp() * 1000))
        for iid, ts in db.execute(
            select(CollectionItemPhoto.collection_item_id, CollectionItemPhoto.updated_at).where(
                CollectionItemPhoto.collection_item_id.in_([item.id for item, *_ in rows])
            )
        ).all()
    }
    out: list[CollectionItemOut] = []
    for item, card, brand, card_set, player, parallel in rows:
        gkey = grade_key_for_item(item.grade_company_id, item.grade_value, item.is_graded)
        vkey = ValuationKey(item.card_id, gkey, item.card_parallel_id)
        v = engine.value(vkey, "90d")
        unit = v["estimated_price"]
        cost = float(item.purchase_price) * item.quantity
        est = round(unit * item.quantity, 2) if unit is not None else None
        pnl = round(est - cost, 2) if est is not None else None
        spark = [c.total_price for c in reversed(engine.comps_for(vkey, "all")[:SPARK_POINTS])]
        last30 = [c.total_price for c in engine.comps_for(vkey, "30d")]
        out.append(
            CollectionItemOut(
                id=item.id,
                owner_profile_id=item.owner_profile_id,
                card_id=item.card_id,
                card_parallel_id=item.card_parallel_id,
                grade_company_id=item.grade_company_id,
                grade_value=item.grade_value,
                is_graded=item.is_graded,
                quantity=item.quantity,
                purchase_price=float(item.purchase_price),
                purchase_date=item.purchase_date,
                condition=item.condition,
                notes=item.notes,
                image_url=item.image_url,
                uploaded_image_path=item.uploaded_image_path,
                created_at=item.created_at,
                title=card.title,
                player=player,
                year=card.year,
                brand=brand,
                card_set=card_set,
                card_number=card.card_number,
                parallel=parallel,
                rookie_flag=bool(card.rookie_flag),
                card_image_url=card.default_image_url,
                photo_version=photo_versions.get(item.id),
                grade_label=grade_label(gkey, names),
                estimated_value=est,
                estimated_unit_price=unit,
                unrealized_pnl=pnl,
                unrealized_pnl_pct=round(pnl / cost * 100, 2) if pnl is not None and cost > 0 else None,
                confidence_score=v["confidence_score"],
                valuation_method=v["methodology"],
                exact_comp_count=v["exact_comp_count"],
                spark=spark,
                median_30d=round(float(statistics.median(last30)), 2) if last30 else None,
                sales_30d=len(last30),
            )
        )
    return out


def record_snapshots(db: Session, holdings: list[CollectionItemOut], as_of: date | None = None) -> None:
    """Store today's unit estimate per (card, grade). Idempotent per day."""
    as_of = as_of or date.today()
    seen: set[tuple] = set()
    for h in holdings:
        if h.estimated_unit_price is None:
            continue
        k = (h.card_id, h.grade_company_id, h.grade_value)
        if k in seen:
            continue
        seen.add(k)
        _upsert_snapshot(db, h, as_of)
    db.commit()


def _upsert_snapshot(db: Session, h: CollectionItemOut, as_of: date) -> None:
    existing = db.scalars(
        select(ValuationSnapshot).where(
            ValuationSnapshot.card_id == h.card_id,
            ValuationSnapshot.as_of_date == as_of,
            ValuationSnapshot.window_days == SNAPSHOT_WINDOW_DAYS,
            (ValuationSnapshot.grade_company_id == h.grade_company_id)
            if h.grade_company_id is not None
            else ValuationSnapshot.grade_company_id.is_(None),
            (ValuationSnapshot.grade_value == h.grade_value)
            if h.grade_value is not None
            else ValuationSnapshot.grade_value.is_(None),
        )
    ).first()
    if existing:
        existing.estimated_price = h.estimated_unit_price
        existing.confidence_score = h.confidence_score or 0
        existing.exact_comp_count = h.exact_comp_count
        existing.methodology = h.valuation_method or "unknown"
        return
    db.add(
        ValuationSnapshot(
            card_id=h.card_id,
            card_parallel_id=h.card_parallel_id,
            grade_company_id=h.grade_company_id,
            grade_value=h.grade_value,
            as_of_date=as_of,
            window_days=SNAPSHOT_WINDOW_DAYS,
            estimated_price=h.estimated_unit_price,
            confidence_score=h.confidence_score or 0,
            exact_comp_count=h.exact_comp_count,
            similar_comp_count=0,
            methodology=h.valuation_method or "unknown",
        )
    )


def previous_unit_prices(db: Session, holdings: list[CollectionItemOut], before: date | None = None) -> dict[tuple, float]:
    """Latest snapshot strictly before `before` (default today) for each (card, company, grade)."""
    before = before or date.today()
    card_ids = {h.card_id for h in holdings}
    if not card_ids:
        return {}
    rows = db.scalars(
        select(ValuationSnapshot)
        .where(
            ValuationSnapshot.card_id.in_(card_ids),
            ValuationSnapshot.as_of_date < before,
            ValuationSnapshot.window_days == SNAPSHOT_WINDOW_DAYS,
        )
        .order_by(ValuationSnapshot.as_of_date.desc())
    ).all()
    prev: dict[tuple, float] = {}
    for s in rows:
        k = (s.card_id, s.grade_company_id, s.grade_value)
        prev.setdefault(k, float(s.estimated_price))
    return prev
