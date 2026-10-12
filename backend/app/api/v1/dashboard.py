from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Card, CollectionItem, Player, SaleComp
from app.services.portfolio import (
    OWNER_PROFILE_ID,
    grade_company_names,
    grade_label,
    load_holdings,
    previous_unit_prices,
    record_snapshots,
)
from app.services.valuation import GradeKey

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    holdings = load_holdings(db)
    # Lazily record today's valuation so daily change works without a cron job.
    record_snapshots(db, holdings)
    prev = previous_unit_prices(db, holdings)

    total_cost = sum(h.purchase_price * h.quantity for h in holdings)
    total_est = sum(h.estimated_value or 0 for h in holdings)
    unpriced = sum(1 for h in holdings if h.estimated_value is None)

    movers = []
    prev_total = 0.0
    have_prev = False
    for h in holdings:
        p = prev.get((h.card_id, h.grade_company_id, h.grade_value))
        cur = h.estimated_unit_price
        if p is not None and cur is not None:
            have_prev = True
            prev_total += p * h.quantity
            delta = (cur - p) * h.quantity
            movers.append(
                {
                    "collection_item_id": h.id,
                    "card_id": h.card_id,
                    "title": h.title,
                    "grade_label": h.grade_label,
                    "change": round(delta, 2),
                    "change_pct": round((cur - p) / p * 100, 2) if p else None,
                }
            )
        elif cur is not None:
            prev_total += cur * h.quantity  # new position: no change attributed today

    movers.sort(key=lambda m: m["change"], reverse=True)
    daily_change = round(total_est - prev_total, 2) if have_prev else None

    return {
        "total_items": sum(h.quantity for h in holdings),
        "positions": len(holdings),
        "graded_positions": sum(1 for h in holdings if h.is_graded),
        "unpriced_positions": unpriced,
        "cost_basis": round(total_cost, 2),
        "estimated_value": round(total_est, 2),
        "unrealized_pnl": round(total_est - total_cost, 2),
        "unrealized_pnl_pct": round((total_est - total_cost) / total_cost * 100, 2) if total_cost else None,
        "daily_change": daily_change,
        "daily_change_pct": round(daily_change / prev_total * 100, 2) if daily_change is not None and prev_total else None,
        "gainers": [m for m in movers if m["change"] > 0][:5],
        "losers": [m for m in reversed(movers) if m["change"] < 0][:5],
        "as_of": date.today().isoformat(),
    }


@router.get("/recent-additions")
def recent_additions(limit: int = Query(default=10, ge=1, le=100), db: Session = Depends(get_db)):
    stmt = (
        select(CollectionItem, Card.title)
        .join(Card, Card.id == CollectionItem.card_id)
        .where(CollectionItem.owner_profile_id == OWNER_PROFILE_ID)
        .order_by(CollectionItem.created_at.desc(), CollectionItem.id.desc())
        .limit(limit)
    )
    return [
        {
            "collection_item_id": item.id,
            "card_id": item.card_id,
            "title": title,
            "purchase_date": str(item.purchase_date),
            "purchase_price": float(item.purchase_price),
            "quantity": item.quantity,
        }
        for item, title in db.execute(stmt).all()
    ]


@router.get("/recent-comps")
def recent_comps(limit: int = Query(default=10, ge=1, le=100), held_only: bool = False, db: Session = Depends(get_db)):
    """Latest sold comps, optionally restricted to cards in the collection."""
    names = grade_company_names(db)
    stmt = (
        select(SaleComp, Card.title, Player.full_name)
        .join(Card, Card.id == SaleComp.card_id)
        .join(Player, Player.id == Card.player_id)
        .order_by(SaleComp.sold_at.desc())
        .limit(limit)
    )
    if held_only:
        held = select(CollectionItem.card_id).where(CollectionItem.owner_profile_id == OWNER_PROFILE_ID)
        stmt = stmt.where(SaleComp.card_id.in_(held))
    return [
        {
            "id": c.id,
            "card_id": c.card_id,
            "title": title,
            "player": player,
            "grade_label": grade_label(GradeKey(c.grade_company_id, c.grade_value), names),
            "sold_at": c.sold_at,
            "total_price": float(c.total_price),
        }
        for c, title, player in db.execute(stmt).all()
    ]


@router.get("/distribution")
def holdings_distribution(by: str = Query(default="brand", pattern="^(brand|player|grade|set|year)$"), db: Session = Depends(get_db)):
    holdings = load_holdings(db)
    counter: Counter[str] = Counter()
    value: Counter[str] = Counter()
    for h in holdings:
        key = {
            "player": h.player,
            "grade": h.grade_label,
            "set": h.card_set,
            "year": str(h.year) if h.year else None,
        }.get(by, h.brand)
        counter[key or "Unknown"] += h.quantity
        value[key or "Unknown"] += h.estimated_value or 0
    return [{"label": k, "count": v, "estimated_value": round(value[k], 2)} for k, v in counter.most_common()]
