from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import mean, median

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Brand, Card, CardSet, Player, SaleComp
from app.schemas.cards import (
    CardDetailOut,
    CardMetadataOut,
    CardSearchResultOut,
    CardStatsOut,
    CompOut,
    RawVsPsaComparisonOut,
    SalesHistoryOut,
    SalesHistoryPricePoint,
    SalesHistoryVolumePoint,
    ValuationOut,
)
from app.services.valuation import compute_card_valuation

router = APIRouter(prefix="/cards", tags=["cards"])
WINDOW_MAP = {"30d": 30, "90d": 90, "1y": 365, "all": None}


def _apply_window(stmt, window: str):
    days = WINDOW_MAP.get(window.lower(), 90)
    if days is None:
        return stmt
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return stmt.where(SaleComp.sold_at >= cutoff)


@router.get("/search", response_model=list[CardSearchResultOut])
def search_cards(
    q: str = Query(default=""),
    year: int | None = None,
    db: Session = Depends(get_db),
):
    stmt = (
        select(Card, Brand.name, CardSet.name, Player.full_name)
        .join(Brand, Brand.id == Card.brand_id)
        .join(CardSet, CardSet.id == Card.set_id)
        .join(Player, Player.id == Card.player_id)
    )

    if q:
        q_like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Card.title.ilike(q_like),
                Card.search_text_normalized.ilike(f"%{q.lower()}%"),
                Card.card_number.ilike(q_like),
                Brand.name.ilike(q_like),
                CardSet.name.ilike(q_like),
                Player.full_name.ilike(q_like),
            )
        )
    if year:
        stmt = stmt.where(Card.year == year)

    rows = db.execute(stmt.limit(50)).all()
    results: list[CardSearchResultOut] = []
    for card, brand, card_set, player in rows:
        valuation = compute_card_valuation(db, card.id)
        results.append(
            CardSearchResultOut(
                id=card.id,
                title=card.title,
                year=card.year,
                card_number=card.card_number,
                brand=brand,
                card_set=card_set,
                player=player,
                default_image_url=card.default_image_url,
                valuation_preview=valuation["estimated_price"],
            )
        )
    return results


@router.get("/{card_id}", response_model=CardDetailOut)
def card_detail(card_id: int, db: Session = Depends(get_db)):
    row = (
        db.execute(
            select(Card, Brand.name, CardSet.name, Player.full_name)
            .join(Brand, Brand.id == Card.brand_id)
            .join(CardSet, CardSet.id == Card.set_id)
            .join(Player, Player.id == Card.player_id)
            .where(Card.id == card_id)
        )
        .all()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Card not found")

    card, brand, card_set, player = row[0]
    valuation_result = compute_card_valuation(db, card_id)

    prices = [r[0] for r in db.execute(select(SaleComp.total_price).where(SaleComp.card_id == card_id)).all()]
    stats = CardStatsOut(
        card_id=card_id,
        window="all",
        count=len(prices),
        average_price=(sum(prices) / len(prices)) if prices else None,
        median_price=float(median(prices)) if prices else None,
    )

    raw_prices = [
        row[0]
        for row in db.execute(
            select(SaleComp.total_price).where(
                and_(SaleComp.card_id == card_id, SaleComp.grade_company_id.is_(None), SaleComp.grade_value.is_(None))
            )
        ).all()
    ]
    psa10_prices = [
        row[0]
        for row in db.execute(
            select(SaleComp.total_price).where(and_(SaleComp.card_id == card_id, SaleComp.grade_value == "10"))
        ).all()
    ]

    return CardDetailOut(
        metadata=CardMetadataOut(
            id=card.id,
            title=card.title,
            slug=card.slug,
            year=card.year,
            card_number=card.card_number,
            brand=brand,
            card_set=card_set,
            player=player,
            rookie_flag=card.rookie_flag,
            autograph_flag=card.autograph_flag,
            patch_flag=card.patch_flag,
            default_image_url=card.default_image_url,
        ),
        valuation=ValuationOut(
            card_id=card_id,
            estimated_price=valuation_result["estimated_price"],
            low_estimate=valuation_result["low_estimate"],
            high_estimate=valuation_result["high_estimate"],
            confidence_score=valuation_result["confidence_score"],
            exact_comp_count=valuation_result["exact_comp_count"],
            similar_comp_count=valuation_result["similar_comp_count"],
            method=valuation_result["methodology"],
            reason_codes=valuation_result["reason_codes"],
            explanation=valuation_result["explanation"],
        ),
        stats=stats,
        comparison=RawVsPsaComparisonOut(
            card_id=card_id,
            window="all",
            raw_count=len(raw_prices),
            psa10_count=len(psa10_prices),
            raw_median=float(median(raw_prices)) if raw_prices else None,
            psa10_median=float(median(psa10_prices)) if psa10_prices else None,
        ),
    )


@router.get("/{card_id}/comps", response_model=list[CompOut])
def card_comps(card_id: int, window: str = "90d", limit: int = 10, db: Session = Depends(get_db)):
    stmt = select(SaleComp).where(SaleComp.card_id == card_id).order_by(SaleComp.sold_at.desc())
    stmt = _apply_window(stmt, window)
    comps = db.scalars(stmt.limit(limit)).all()
    return [CompOut(id=c.id, sold_at=c.sold_at, total_price=c.total_price, grade_value=c.grade_value) for c in comps]


@router.get("/{card_id}/stats", response_model=CardStatsOut)
def card_stats(card_id: int, window: str = "90d", db: Session = Depends(get_db)):
    stmt = _apply_window(select(SaleComp.total_price).where(SaleComp.card_id == card_id), window)
    prices = [row[0] for row in db.execute(stmt).all()]
    return CardStatsOut(
        card_id=card_id,
        window=window,
        count=len(prices),
        average_price=(sum(prices) / len(prices)) if prices else None,
        median_price=float(median(prices)) if prices else None,
    )


@router.get("/{card_id}/sales-history", response_model=SalesHistoryOut)
def card_sales_history(card_id: int, window: str = "90d", bucket: str = "day", db: Session = Depends(get_db)):
    stmt = _apply_window(select(SaleComp).where(SaleComp.card_id == card_id).order_by(SaleComp.sold_at.asc()), window)
    comps = db.scalars(stmt).all()

    grouped: dict[str, list[float]] = defaultdict(list)
    for comp in comps:
        sold = comp.sold_at.date()
        if bucket == "month":
            key = sold.strftime("%Y-%m")
        elif bucket == "week":
            key = f"{sold.isocalendar().year}-W{sold.isocalendar().week:02d}"
        else:
            key = sold.isoformat()
        grouped[key].append(comp.total_price)

    ordered = sorted(grouped.items(), key=lambda x: x[0])
    price_series = [
        SalesHistoryPricePoint(date=k, avg_price=round(mean(v), 2), median_price=round(median(v), 2)) for k, v in ordered
    ]
    volume_series = [SalesHistoryVolumePoint(date=k, sale_count=len(v)) for k, v in ordered]

    return SalesHistoryOut(
        card_id=card_id,
        window=window,
        bucket=bucket,
        price_series=price_series,
        volume_series=volume_series,
    )


@router.get("/{card_id}/comparison/raw-vs-psa10", response_model=RawVsPsaComparisonOut)
def raw_vs_psa10(card_id: int, window: str = "90d", db: Session = Depends(get_db)):
    raw_stmt = _apply_window(
        select(SaleComp.total_price).where(
            and_(SaleComp.card_id == card_id, SaleComp.grade_company_id.is_(None), SaleComp.grade_value.is_(None))
        ),
        window,
    )
    psa10_stmt = _apply_window(
        select(SaleComp.total_price).where(and_(SaleComp.card_id == card_id, SaleComp.grade_value == "10")),
        window,
    )

    raw_prices = [row[0] for row in db.execute(raw_stmt).all()]
    psa10_prices = [row[0] for row in db.execute(psa10_stmt).all()]

    return RawVsPsaComparisonOut(
        card_id=card_id,
        window=window,
        raw_count=len(raw_prices),
        psa10_count=len(psa10_prices),
        raw_median=float(median(raw_prices)) if raw_prices else None,
        psa10_median=float(median(psa10_prices)) if psa10_prices else None,
    )
