from collections import defaultdict
from datetime import UTC
from statistics import mean, median

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import (
    Brand,
    Card,
    CardSet,
    CollectionItem,
    CollectionItemPhoto,
    NormalizedSale,
    Player,
    RawMarketListing,
    SaleComp,
    SourcePlatform,
    Sport,
)
from app.schemas.cards import (
    CardDetailOut,
    CardMetadataOut,
    CardSearchResultOut,
    CardStatsOut,
    CompOut,
    GradeOptionOut,
    RawVsPsaComparisonOut,
    SalesHistoryOut,
    SalesHistoryPricePoint,
    SalesHistoryVolumePoint,
    ValuationOut,
)
from app.services.portfolio import grade_company_names, grade_label
from app.services.valuation import (
    GradeKey,
    split_outliers,
    ValuationEngine,
    ValuationKey,
    normalize_window,
    parse_grade_param,
    window_cutoff,
)

router = APIRouter(prefix="/cards", tags=["cards"])


def _escape_like(token: str) -> str:
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_tokens(q: str) -> list[str]:
    """'2024-25 Prizm #12' -> ['2024', 'prizm', '12'].

    Basketball/hockey seasons are written "2024-25" but stored as the start year.
    """
    import re

    q = re.sub(r"\b((?:19|20)\d{2})\s*[-/]\s*\d{2,4}\b", r"\1", q.lower())
    # Grade words pick the preview price, they aren't part of a card's name.
    q = re.sub(r"\b(psa|bgs|sgc|cgc)\s*(10|[1-9](?:\.5)?)\b|\braw\b|\bungraded\b", " ", q)
    return [t for t in re.split(r"[\s#,]+", q) if t]


def _search_blob():
    # Everything a collector might type: title, normalized text, brand, set, player, card #.
    return func.lower(
        func.concat_ws(" ", Card.title, Card.search_text_normalized, Brand.name, CardSet.name, Player.full_name, Card.card_number)
    )


def _valuation_out(card_id: int, v: dict, label: str) -> ValuationOut:
    return ValuationOut(
        card_id=card_id,
        grade=label,
        estimated_price=v["estimated_price"],
        low_estimate=v["low_estimate"],
        high_estimate=v["high_estimate"],
        confidence_score=v["confidence_score"],
        exact_comp_count=v["exact_comp_count"],
        similar_comp_count=v["similar_comp_count"],
        method=v["methodology"],
        reason_codes=v["reason_codes"],
        explanation=v["explanation"],
        window_used=v.get("window_used"),
        last_sale_at=v.get("last_sale_at"),
    )


def _card_photos(db: Session, card_ids: set[int]) -> dict[int, tuple[int, str]]:
    """Most recent owner photo per card -> (collection_item_id, version)."""
    if not card_ids:
        return {}
    rows = db.execute(
        select(CollectionItem.card_id, CollectionItemPhoto.collection_item_id, CollectionItemPhoto.updated_at)
        .join(CollectionItem, CollectionItem.id == CollectionItemPhoto.collection_item_id)
        .where(CollectionItem.card_id.in_(card_ids))
        .order_by(CollectionItemPhoto.updated_at.desc())
    ).all()
    out: dict[int, tuple[int, str]] = {}
    for cid, iid, ts in rows:
        out.setdefault(cid, (iid, str(int(ts.timestamp() * 1000))))
    return out


def _grade_key_str(grade_value: str | None) -> str:
    return "raw" if grade_value is None else f"psa{grade_value}"


@router.get("/search", response_model=list[CardSearchResultOut])
def search_cards(
    q: str = Query(default="", max_length=200),
    year: int | None = None,
    brand: str | None = None,
    player: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Card, Brand.name, CardSet.name, Player.full_name)
        .join(Brand, Brand.id == Card.brand_id)
        .join(CardSet, CardSet.id == Card.set_id)
        .join(Player, Player.id == Card.player_id)
    )
    blob = _search_blob()
    # Every token must appear somewhere ("2023 topps ohtani psa 10" -> 5 AND-ed tokens).
    for token in search_tokens(q):
        stmt = stmt.where(blob.like(f"%{_escape_like(token)}%", escape="\\"))
    if year:
        stmt = stmt.where(Card.year == year)
    if brand:
        stmt = stmt.where(Brand.name.ilike(_escape_like(brand), escape="\\"))
    if player:
        stmt = stmt.where(Player.full_name.ilike(f"%{_escape_like(player)}%", escape="\\"))

    rows = db.execute(stmt.order_by(Card.year.desc(), Card.title).limit(limit)).all()
    if not rows:
        return []

    # If the query names a grade ("raw", "psa 10", "psa10"), price the preview at that grade;
    # otherwise at each card's most-traded grade, never a raw + slab mix.
    import re

    ql = q.lower()
    asked: GradeKey | None = None
    if re.search(r"\braw\b", ql):
        asked = GradeKey()
    elif m := re.search(r"\bpsa\s*(10|[1-9](?:\.5)?)\b", ql):
        asked = GradeKey(grade_company_id=1, grade_value=m.group(1))

    engine = ValuationEngine(db, {card.id for card, *_ in rows})
    photos = _card_photos(db, {card.id for card, *_ in rows})
    results = []
    for card, brand_name, set_name, player_name in rows:
        grade = asked
        if grade is None:
            counts: dict[str | None, int] = defaultdict(int)
            for c in engine.comps.get(card.id, []):
                counts[c.grade_value] += 1
            top = max(counts.items(), key=lambda kv: kv[1])[0] if counts else None
            grade = GradeKey(1 if top else None, top)
        v = engine.value(ValuationKey(card.id, grade))
        results.append(
            CardSearchResultOut(
                id=card.id,
                title=card.title,
                year=card.year,
                card_number=card.card_number,
                brand=brand_name,
                card_set=set_name,
                player=player_name,
                rookie_flag=bool(card.rookie_flag),
                default_image_url=card.default_image_url,
                photo_item_id=photos.get(card.id, (None, None))[0],
                photo_version=photos.get(card.id, (None, None))[1],
                valuation_preview=v["estimated_price"],
                comp_count=len(engine.comps.get(card.id, [])),
            )
        )
    return results


def _load_card(db: Session, card_id: int):
    row = db.execute(
        select(Card, Brand.name, CardSet.name, Player.full_name, Sport.name)
        .join(Brand, Brand.id == Card.brand_id)
        .join(CardSet, CardSet.id == Card.set_id)
        .join(Player, Player.id == Card.player_id)
        .join(Sport, Sport.id == Card.sport_id)
        .where(Card.id == card_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Card not found")
    return row


@router.get("/{card_id}", response_model=CardDetailOut)
def card_detail(
    card_id: int,
    grade: str | None = Query(default=None, description="raw | psa10 | psa9 | all"),
    window: str = "30d",
    db: Session = Depends(get_db),
):
    card, brand, card_set, player, sport = _load_card(db, card_id)
    window = normalize_window(window)
    engine = ValuationEngine(db, {card_id})
    comps = engine.comps.get(card_id, [])
    names = grade_company_names(db)
    photo = _card_photos(db, {card_id}).get(card_id, (None, None))
    from app.models.entities import CardParallel

    named_par = db.scalars(
        select(CardParallel).where(CardParallel.card_id == card_id, CardParallel.parallel_name != "Base").order_by(CardParallel.id)
    ).first()

    counts: dict[str | None, int] = defaultdict(int)
    for c in comps:
        counts[c.grade_value] += 1
    grade_opts = [
        GradeOptionOut(key=_grade_key_str(gv), label=grade_label(GradeKey(1 if gv else None, gv), names), comp_count=n)
        for gv, n in sorted(counts.items(), key=lambda kv: (kv[0] is not None, -kv[1]))
    ]

    # Default grade: the most-traded one, so the headline number is never a grade mix.
    if grade is None and comps:
        top = max(counts.items(), key=lambda kv: kv[1])[0]
        gkey = GradeKey(1 if top else None, top)
    else:
        gkey = parse_grade_param(grade)
    label = grade_label(gkey, names) if not gkey.any_grade else "All grades"

    v = engine.value(ValuationKey(card_id, gkey), window)
    scoped = [c.total_price for c in engine.comps_for(ValuationKey(card_id, gkey), window)]
    raw = [c.total_price for c in comps if c.grade_value is None]
    psa10 = [c.total_price for c in comps if c.grade_value == "10"]
    raw_med = float(median(raw)) if raw else None
    psa_med = float(median(psa10)) if psa10 else None

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
            sport=sport,
            parallel=named_par.parallel_name if named_par else None,
            print_run=named_par.print_run if named_par else None,
            rookie_flag=bool(card.rookie_flag),
            autograph_flag=bool(card.autograph_flag),
            patch_flag=bool(card.patch_flag),
            default_image_url=card.default_image_url,
            photo_item_id=photo[0],
            photo_version=photo[1],
        ),
        valuation=_valuation_out(card_id, v, label),
        stats=CardStatsOut(
            card_id=card_id,
            window=window,
            count=len(scoped),
            average_price=round(mean(scoped), 2) if scoped else None,
            median_price=round(float(median(scoped)), 2) if scoped else None,
        ),
        comparison=RawVsPsaComparisonOut(
            card_id=card_id,
            window="all",
            raw_count=len(raw),
            psa10_count=len(psa10),
            raw_median=raw_med,
            psa10_median=psa_med,
            grading_premium=round(psa_med / raw_med, 2) if raw_med and psa_med else None,
        ),
        grades=grade_opts,
    )


@router.get("/{card_id}/comps", response_model=list[CompOut])
def card_comps(
    card_id: int,
    window: str = "30d",
    grade: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    gkey = parse_grade_param(grade)
    names = grade_company_names(db)
    stmt = select(SaleComp.id, SaleComp.sold_at, SaleComp.total_price, SaleComp.grade_value, SaleComp.grade_company_id).where(
        SaleComp.card_id == card_id
    )
    cutoff = window_cutoff(window)
    if cutoff:
        stmt = stmt.where(SaleComp.sold_at >= cutoff)
    if not gkey.any_grade:
        stmt = stmt.where(SaleComp.grade_value.is_(None) if gkey.is_raw else SaleComp.grade_value == gkey.grade_value)
    rows = db.execute(stmt.order_by(SaleComp.sold_at.desc()).limit(limit)).all()
    return [
        CompOut(
            id=r.id,
            sold_at=r.sold_at,
            total_price=float(r.total_price),
            grade_value=r.grade_value,
            grade_label=grade_label(GradeKey(r.grade_company_id, r.grade_value), names),
        )
        for r in rows
    ]


@router.get("/{card_id}/stats", response_model=CardStatsOut)
def card_stats(card_id: int, window: str = "30d", grade: str | None = None, db: Session = Depends(get_db)):
    engine = ValuationEngine(db, {card_id})
    prices = [c.total_price for c in engine.comps_for(ValuationKey(card_id, parse_grade_param(grade)), window)]
    return CardStatsOut(
        card_id=card_id,
        window=normalize_window(window),
        count=len(prices),
        average_price=round(mean(prices), 2) if prices else None,
        median_price=round(float(median(prices)), 2) if prices else None,
    )


@router.get("/{card_id}/sales-history", response_model=SalesHistoryOut)
def card_sales_history(
    card_id: int,
    window: str = "30d",
    bucket: str = Query(default="day", pattern="^(day|week|month)$"),
    grade: str | None = None,
    db: Session = Depends(get_db),
):
    gkey = parse_grade_param(grade)
    engine = ValuationEngine(db, {card_id})
    comps = sorted(engine.comps_for(ValuationKey(card_id, gkey), window), key=lambda c: c.sold_at)

    grouped: dict[str, list[float]] = defaultdict(list)
    for comp in comps:
        sold = comp.sold_at.astimezone(UTC).date()  # bucket by UTC calendar day, not the DB session's zone
        if bucket == "month":
            key = sold.strftime("%Y-%m")
        elif bucket == "week":
            iso = sold.isocalendar()
            key = f"{iso.year}-W{iso.week:02d}"
        else:
            key = sold.isoformat()
        grouped[key].append(comp.total_price)

    ordered = sorted(grouped.items())
    return SalesHistoryOut(
        card_id=card_id,
        window=normalize_window(window),
        bucket=bucket,
        grade=gkey.label(),
        price_series=[
            SalesHistoryPricePoint(date=k, avg_price=round(mean(v), 2), median_price=round(median(v), 2)) for k, v in ordered
        ],
        volume_series=[SalesHistoryVolumePoint(date=k, sale_count=len(v)) for k, v in ordered],
    )


@router.get("/{card_id}/comparison/raw-vs-psa10", response_model=RawVsPsaComparisonOut)
def raw_vs_psa10(card_id: int, window: str = "90d", db: Session = Depends(get_db)):
    engine = ValuationEngine(db, {card_id})
    raw = [c.total_price for c in engine.comps_for(ValuationKey(card_id, GradeKey()), window)]
    psa10 = [c.total_price for c in engine.comps_for(ValuationKey(card_id, GradeKey(1, "10")), window)]
    raw_med = float(median(raw)) if raw else None
    psa_med = float(median(psa10)) if psa10 else None
    return RawVsPsaComparisonOut(
        card_id=card_id,
        window=normalize_window(window),
        raw_count=len(raw),
        psa10_count=len(psa10),
        raw_median=raw_med,
        psa10_median=psa_med,
        grading_premium=round(psa_med / raw_med, 2) if raw_med and psa_med else None,
    )


@router.get("/{card_id}/market-summary")
def market_summary(
    card_id: int,
    grade: str | None = Query(default=None, description="raw | psa10 | psa9 | all"),
    window: str = Query(default="30d", pattern="^(30d|90d|1y|all)$"),
    db: Session = Depends(get_db),
):
    """Card Ladder-style view: every sale in the window, median, volume, change vs prior window."""
    from datetime import datetime as _dt, timedelta

    _load_card(db, card_id)
    gkey = parse_grade_param(grade)
    names = grade_company_names(db)
    now = _dt.now(UTC)
    days = {"30d": 30, "90d": 90, "1y": 365}.get(window)
    start = now - timedelta(days=days) if days else None
    prev_start = now - timedelta(days=2 * days) if days else None

    stmt = (
        select(
            SaleComp.id,
            SaleComp.sold_at,
            SaleComp.total_price,
            SaleComp.grade_company_id,
            SaleComp.grade_value,
            SourcePlatform.name,
            RawMarketListing.listing_url_raw,
            RawMarketListing.listing_title_raw,
        )
        .join(NormalizedSale, NormalizedSale.id == SaleComp.normalized_sale_id)
        .join(RawMarketListing, RawMarketListing.id == NormalizedSale.raw_market_listing_id)
        .join(SourcePlatform, SourcePlatform.id == RawMarketListing.source_platform_id)
        .where(SaleComp.card_id == card_id)
        .order_by(SaleComp.sold_at.asc())
    )
    if not gkey.any_grade:
        stmt = stmt.where(SaleComp.grade_value.is_(None) if gkey.is_raw else SaleComp.grade_value == gkey.grade_value)
    if prev_start:
        stmt = stmt.where(SaleComp.sold_at >= prev_start)
    rows = db.execute(stmt).all()

    cur = [r for r in rows if start is None or r.sold_at >= start]
    prev = [r for r in rows if start is not None and r.sold_at < start]
    # Median, range and trend leave out far-off sales (same rule as the estimate).
    prices, outlier_prices = split_outliers([float(r.total_price) for r in cur])
    prev_prices, _ = split_outliers([float(r.total_price) for r in prev])
    kept_ok = set(prices)
    outlier_set = {p for p in outlier_prices if p not in kept_ok}
    med = round(float(median(prices)), 2) if prices else None
    prev_med = round(float(median(prev_prices)), 2) if prev_prices else None

    sales = []
    window_prices: list[float] = []
    for r in cur:
        window_prices.append(float(r.total_price))
        last5 = window_prices[-5:]
        sales.append(
            {
                "id": r.id,
                "sold_at": r.sold_at,
                "date": r.sold_at.astimezone(UTC).date().isoformat(),
                "ts": r.sold_at.astimezone(UTC).isoformat(),
                "price": float(r.total_price),
                "grade_label": grade_label(GradeKey(r.grade_company_id, r.grade_value), names),
                "source": r.name,
                "url": r.listing_url_raw if (r.listing_url_raw or "").startswith("http") else None,
                "title": r.listing_title_raw,
                "rolling_median": round(float(median(last5)), 2),  # median of this + previous 4 sales
                "outlier": float(r.total_price) in outlier_set,
            }
        )
    volume: dict[str, int] = defaultdict(int)
    for srow in sales:
        volume[srow["date"]] += 1

    # Trend line: one point per day that had sales = median of every sale in the trailing
    # N days. Time-based, so a burst of same-day sales doesn't make the line jump around.
    trail = {"30d": 7, "90d": 14}.get(window, 30)
    trend = []
    for d in sorted({s["date"] for s in sales if not s["outlier"]}):  # days with a sale that counts
        dd = _dt.fromisoformat(d).date()
        win_prices = [
            s["price"]
            for s in sales
            if not s["outlier"] and 0 <= (dd - _dt.fromisoformat(s["date"]).date()).days < trail
        ]
        if not win_prices:
            continue
        trend.append({"date": d, "median": round(float(median(win_prices)), 2), "n": len(win_prices)})

    return {
        "card_id": card_id,
        "grade": "All grades" if gkey.any_grade else grade_label(gkey, names),
        "window": window,
        "median": med,
        "average": round(mean(prices), 2) if prices else None,
        "low": min(prices) if prices else None,
        "high": max(prices) if prices else None,
        "count": len(cur),
        "prev_median": prev_med,
        "prev_count": len(prev),
        "change_pct": round((med - prev_med) / prev_med * 100, 1) if med and prev_med else None,
        "last_sale": sales[-1] if sales else None,
        "sales": sales,
        "volume": [{"date": d, "count": c} for d, c in sorted(volume.items())],
        "trend": trend,
        "outliers": len(outlier_prices),
        "trend_days": trail,
        "window_start": start.date().isoformat() if start else (sales[0]["date"] if sales else None),
        "window_end": now.date().isoformat(),
    }


@router.delete("/{card_id}/comps/{comp_id}")
def delete_comp(card_id: int, comp_id: int, db: Session = Depends(get_db)):
    """Remove a wrong sale from a card's history (the raw record is kept for traceability)."""
    from app.models.entities import ListingCardMatch

    comp = db.get(SaleComp, comp_id)
    if comp is None or comp.card_id != card_id:
        raise HTTPException(status_code=404, detail="Sale not found for this card")
    match = db.scalars(select(ListingCardMatch).where(ListingCardMatch.normalized_sale_id == comp.normalized_sale_id)).first()
    if match:
        match.match_method = "owner_rejected"
        match.is_primary = False
    db.delete(comp)
    db.commit()
    return {"deleted": True}
