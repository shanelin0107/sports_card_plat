from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import median

from sqlalchemy import Select, and_, select
from sqlalchemy.orm import Session

from app.models.entities import Card, SaleComp


WINDOW_TO_DAYS = {"30d": 30, "90d": 90, "1y": 365, "all": None}


def _window_cutoff(window: str) -> datetime | None:
    days = WINDOW_TO_DAYS.get(window.lower())
    if days is None:
        return None
    return datetime.now(UTC) - timedelta(days=days)


def _range_from_prices(prices: list[float]) -> tuple[float, float]:
    sorted_prices = sorted(prices)
    low_idx = max(0, int(len(sorted_prices) * 0.25) - 1)
    high_idx = min(len(sorted_prices) - 1, int(len(sorted_prices) * 0.75))
    return float(sorted_prices[low_idx]), float(sorted_prices[high_idx])


def compute_card_valuation(db: Session, card_id: int, window: str = "90d") -> dict:
    cutoff = _window_cutoff(window)
    exact_stmt: Select[tuple[SaleComp]] = select(SaleComp).where(SaleComp.card_id == card_id)
    if cutoff:
        exact_stmt = exact_stmt.where(SaleComp.sold_at >= cutoff)
    exact_comps = db.scalars(exact_stmt.order_by(SaleComp.sold_at.desc()).limit(20)).all()

    exact_prices = [c.total_price for c in exact_comps]
    if len(exact_prices) >= 3:
        low_estimate, high_estimate = _range_from_prices(exact_prices)
        return {
            "estimated_price": float(median(exact_prices)),
            "low_estimate": low_estimate,
            "high_estimate": high_estimate,
            "confidence_score": min(1.0, 0.45 + len(exact_prices) * 0.05),
            "exact_comp_count": len(exact_prices),
            "similar_comp_count": 0,
            "reason_codes": ["EXACT_COMPS", f"WINDOW_{window.upper()}"],
            "explanation": "Median from exact recent comps",
            "methodology": "exact_recent_comps_median",
        }

    card = db.get(Card, card_id)
    if card is None:
        return {
            "estimated_price": None,
            "low_estimate": None,
            "high_estimate": None,
            "confidence_score": 0.0,
            "exact_comp_count": 0,
            "similar_comp_count": 0,
            "reason_codes": ["CARD_NOT_FOUND"],
            "explanation": "Card not found",
            "methodology": "not_found",
        }

    similar_stmt = (
        select(SaleComp.total_price)
        .join(Card, Card.id == SaleComp.card_id)
        .where(
            and_(
                Card.player_id == card.player_id,
                Card.brand_id == card.brand_id,
                Card.year == card.year,
                SaleComp.card_id != card_id,
            )
        )
    )
    if cutoff:
        similar_stmt = similar_stmt.where(SaleComp.sold_at >= cutoff)

    similar_prices = [row[0] for row in db.execute(similar_stmt.limit(30)).all()]
    if exact_prices and similar_prices:
        blended = exact_prices + similar_prices[: max(1, 6 - len(exact_prices))]
    elif exact_prices:
        blended = exact_prices
    else:
        blended = similar_prices

    if not blended:
        return {
            "estimated_price": None,
            "low_estimate": None,
            "high_estimate": None,
            "confidence_score": 0.0,
            "exact_comp_count": len(exact_prices),
            "similar_comp_count": len(similar_prices),
            "reason_codes": ["NO_COMPS"],
            "explanation": "No exact or similar comps available",
            "methodology": "no_data",
        }

    low_estimate, high_estimate = _range_from_prices(blended)
    return {
        "estimated_price": float(median(blended)),
        "low_estimate": low_estimate,
        "high_estimate": high_estimate,
        "confidence_score": 0.35 if len(exact_prices) == 0 else 0.5,
        "exact_comp_count": len(exact_prices),
        "similar_comp_count": len(similar_prices),
        "reason_codes": ["LOW_LIQUIDITY_FALLBACK", f"WINDOW_{window.upper()}"],
        "explanation": "Blended exact and similar comps due to low liquidity",
        "methodology": "blended_similarity_fallback",
    }
