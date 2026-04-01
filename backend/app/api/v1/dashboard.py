from collections import Counter

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Brand, Card, CollectionItem, GradeCompany, Player
from app.services.valuation import compute_card_valuation

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
OWNER_PROFILE_ID = 1


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    items = db.scalars(select(CollectionItem).where(CollectionItem.owner_profile_id == OWNER_PROFILE_ID)).all()
    total_cost = 0.0
    total_estimated = 0.0

    for item in items:
        total_cost += item.purchase_price * item.quantity
        result = compute_card_valuation(db=db, card_id=item.card_id)
        total_estimated += (result["estimated_price"] or 0.0) * item.quantity

    return {
        "total_items": len(items),
        "cost_basis": round(total_cost, 2),
        "estimated_value": round(total_estimated, 2),
        "unrealized_pnl": round(total_estimated - total_cost, 2),
        "todo_daily_change": "TODO: add valuation_snapshot time-series for day-over-day delta",
        "todo_gainers_losers": "TODO: add item-level prior snapshot comparison",
    }


@router.get("/recent-additions")
def recent_additions(limit: int = 10, db: Session = Depends(get_db)):
    stmt = (
        select(CollectionItem, Card.title)
        .join(Card, Card.id == CollectionItem.card_id)
        .where(CollectionItem.owner_profile_id == OWNER_PROFILE_ID)
        .order_by(CollectionItem.created_at.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    return [
        {
            "collection_item_id": item.id,
            "card_id": item.card_id,
            "title": title,
            "purchase_date": str(item.purchase_date),
            "purchase_price": item.purchase_price,
            "quantity": item.quantity,
        }
        for item, title in rows
    ]


@router.get("/distribution")
def holdings_distribution(by: str = Query(default="brand"), db: Session = Depends(get_db)):
    items = db.scalars(select(CollectionItem).where(CollectionItem.owner_profile_id == OWNER_PROFILE_ID)).all()
    counter: Counter[str] = Counter()

    for item in items:
        if by == "player":
            key = db.execute(select(Player.full_name).join(Card, Card.player_id == Player.id).where(Card.id == item.card_id)).scalar()
        elif by == "grade":
            if item.grade_company_id:
                company = db.get(GradeCompany, item.grade_company_id)
                key = f"{company.name} {item.grade_value}"
            else:
                key = "Raw"
        else:
            key = db.execute(select(Brand.name).join(Card, Card.brand_id == Brand.id).where(Card.id == item.card_id)).scalar()
        counter[key or "Unknown"] += item.quantity

    return [{"label": k, "count": v} for k, v in counter.items()]
