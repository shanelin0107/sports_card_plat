"""Create an owner-confirmed comp from an external sale record (eBay sold item, AI research)."""

from __future__ import annotations

from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    GradeCompany,
    ListingCardMatch,
    NormalizedSale,
    RawMarketListing,
    SaleComp,
    SourcePlatform,
)
from app.services.ingestion.parsing import parse_sold_at, parse_title


class CompError(ValueError):
    pass


def _source_platform(db: Session, url: str, fallback: str) -> SourcePlatform:
    host = urlsplit(url or "").netloc.lower().removeprefix("www.")
    name = "eBay" if host.startswith("ebay.") else (fallback or host or "Web")[:100]
    src = db.scalars(select(SourcePlatform).where(SourcePlatform.name == name)).first()
    if src is None:
        src = SourcePlatform(name=name, source_type="external")
        db.add(src)
        db.flush()
    return src


def create_confirmed_comp(
    db: Session,
    *,
    card_id: int,
    listing_id: str,
    title: str,
    url: str,
    price: float,
    date: str | None,
    grade: str | None,
    source: str,
    match_method: str,
    payload: dict,
) -> tuple[SaleComp, bool]:
    """Returns (comp, created). Idempotent on (source platform, listing_id)."""
    sold_at = parse_sold_at(date)
    if sold_at is None:
        raise CompError("This record has no sale date, so it can't be used as a comp")
    if not price or price <= 0:
        raise CompError("This record has no price")

    src = _source_platform(db, url, source)
    existing = db.scalars(
        select(RawMarketListing).where(RawMarketListing.source_platform_id == src.id, RawMarketListing.source_listing_id == listing_id)
    ).first()
    if existing:
        norm = db.scalars(select(NormalizedSale).where(NormalizedSale.raw_market_listing_id == existing.id)).first()
        comp = db.scalars(select(SaleComp).where(SaleComp.normalized_sale_id == norm.id)).first() if norm else None
        if comp:
            return comp, False
        if norm is not None:
            # The owner removed this sale earlier; don't bring it back automatically.
            raise CompError("This sale was removed from the card earlier")

    parsed = parse_title(title or "", grade)
    grade_value = None if (grade or "").strip().lower() in ("", "raw") else parsed.grade_value
    company_id = None
    if grade_value and parsed.grader:
        company_id = db.scalars(select(GradeCompany.id).where(GradeCompany.name == parsed.grader)).first()
        if company_id is None:
            gc = GradeCompany(name=parsed.grader)
            db.add(gc)
            db.flush()
            company_id = gc.id

    raw = existing or RawMarketListing(source_platform_id=src.id, source_listing_id=listing_id)
    raw.sold_at_raw = date
    raw.listing_title_raw = (title or "")[:2000]
    raw.listing_url_raw = url
    raw.condition_raw = grade
    raw.price_raw = str(price)
    raw.shipping_raw = "0"
    raw.payload_json = payload
    if existing is None:
        db.add(raw)
    db.flush()

    norm = NormalizedSale(
        raw_market_listing_id=raw.id,
        source_platform_id=src.id,
        source_listing_id=listing_id,
        sold_at=sold_at,
        sale_price=float(price),
        shipping_price=0.0,
        total_price=float(price),
        currency="USD",
        grade_company_id=company_id,
        grade_value=grade_value,
        parsed_year=parsed.year,
        parsed_card_number=parsed.card_number,
        normalized_notes=f"Owner-confirmed ({match_method})",
    )
    db.add(norm)
    db.flush()
    db.add(
        ListingCardMatch(
            normalized_sale_id=norm.id,
            card_id=card_id,
            match_method=match_method,
            confidence_score=1.0,
            is_primary=True,
            reason_codes=["OWNER_CONFIRMED"],
        )
    )
    comp = SaleComp(
        normalized_sale_id=norm.id,
        card_id=card_id,
        grade_company_id=company_id,
        grade_value=grade_value,
        sold_at=sold_at,
        sale_price=float(price),
        shipping_price=0.0,
        total_price=float(price),
        currency="USD",
    )
    db.add(comp)
    db.flush()
    return comp, True
