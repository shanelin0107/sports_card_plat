from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Sport(Base):
    __tablename__ = "sport"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class Brand(Base):
    __tablename__ = "brand"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class CardSet(Base):
    __tablename__ = "card_set"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brand.id"), nullable=False)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sport.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    release_year: Mapped[int] = mapped_column(Integer, nullable=False)


class Player(Base):
    __tablename__ = "player"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sport.id"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)


class GradeCompany(Base):
    __tablename__ = "grade_company"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)


class SourcePlatform(Base):
    __tablename__ = "source_platform"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)


class Card(Base):
    __tablename__ = "card"
    __table_args__ = (UniqueConstraint("slug", name="uq_card_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sport.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brand.id"), nullable=False)
    set_id: Mapped[int] = mapped_column(ForeignKey("card_set.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("player.id"), nullable=False)
    card_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    search_text_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    default_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    rookie_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    autograph_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    patch_flag: Mapped[bool] = mapped_column(Boolean, default=False)


class CardParallel(Base):
    __tablename__ = "card_parallel"
    __table_args__ = (UniqueConstraint("card_id", "parallel_name", "variation_name", name="uq_card_parallel_identity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("card.id"), nullable=False, index=True)
    parallel_name: Mapped[str] = mapped_column(String(100), nullable=False)
    variation_name: Mapped[str] = mapped_column(String(100), default="Base")
    is_short_print: Mapped[bool] = mapped_column(Boolean, default=False)
    print_run: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CardGradeProfile(Base):
    __tablename__ = "card_grade_profile"
    __table_args__ = (
        UniqueConstraint("card_id", "card_parallel_id", "grade_company_id", "grade_value", name="uq_card_grade_profile"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("card.id"), nullable=False, index=True)
    card_parallel_id: Mapped[int | None] = mapped_column(ForeignKey("card_parallel.id"), nullable=True)
    grade_company_id: Mapped[int | None] = mapped_column(ForeignKey("grade_company.id"), nullable=True)
    grade_value: Mapped[str | None] = mapped_column(String(20), nullable=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    is_raw: Mapped[bool] = mapped_column(Boolean, default=False)


class RawMarketListing(Base):
    __tablename__ = "raw_market_listing"
    __table_args__ = (UniqueConstraint("source_platform_id", "source_listing_id", name="uq_raw_listing_source_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_platform_id: Mapped[int] = mapped_column(ForeignKey("source_platform.id"), nullable=False, index=True)
    source_listing_id: Mapped[str] = mapped_column(String(120), nullable=False)
    fetched_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sold_at_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    listing_title_raw: Mapped[str] = mapped_column(Text, nullable=False)
    listing_url_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    price_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    shipping_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class NormalizedSale(Base):
    __tablename__ = "normalized_sale"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_market_listing_id: Mapped[int] = mapped_column(
        ForeignKey("raw_market_listing.id"), nullable=False, unique=True, index=True
    )
    source_platform_id: Mapped[int] = mapped_column(ForeignKey("source_platform.id"), nullable=False, index=True)
    source_listing_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    sold_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    sale_price: Mapped[float] = mapped_column(Float, nullable=False)
    shipping_price: Mapped[float] = mapped_column(Float, default=0)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    grade_company_id: Mapped[int | None] = mapped_column(ForeignKey("grade_company.id"), nullable=True)
    grade_value: Mapped[str | None] = mapped_column(String(20), nullable=True)
    parsed_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parsed_brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parsed_set: Mapped[str | None] = mapped_column(String(150), nullable=True)
    parsed_player: Mapped[str | None] = mapped_column(String(150), nullable=True)
    parsed_card_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    parsed_parallel: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parsed_variation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    normalized_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ListingCardMatch(Base):
    __tablename__ = "listing_card_match"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normalized_sale_id: Mapped[int] = mapped_column(ForeignKey("normalized_sale.id"), nullable=False, index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("card.id"), nullable=False, index=True)
    card_parallel_id: Mapped[int | None] = mapped_column(ForeignKey("card_parallel.id"), nullable=True)
    match_method: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    reason_codes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)


class SaleComp(Base):
    __tablename__ = "sale_comp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normalized_sale_id: Mapped[int] = mapped_column(ForeignKey("normalized_sale.id"), nullable=False, unique=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("card.id"), nullable=False, index=True)
    card_parallel_id: Mapped[int | None] = mapped_column(ForeignKey("card_parallel.id"), nullable=True)
    grade_company_id: Mapped[int | None] = mapped_column(ForeignKey("grade_company.id"), nullable=True)
    grade_value: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sold_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    sale_price: Mapped[float] = mapped_column(Float, nullable=False)
    shipping_price: Mapped[float] = mapped_column(Float, default=0)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")


class OwnerProfile(Base):
    __tablename__ = "owner_profile"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)


class CollectionItem(Base):
    __tablename__ = "collection_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_profile_id: Mapped[int] = mapped_column(ForeignKey("owner_profile.id"), nullable=False)
    card_id: Mapped[int] = mapped_column(ForeignKey("card.id"), nullable=False)
    card_parallel_id: Mapped[int | None] = mapped_column(ForeignKey("card_parallel.id"), nullable=True)
    grade_company_id: Mapped[int | None] = mapped_column(ForeignKey("grade_company.id"), nullable=True)
    grade_value: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_graded: Mapped[bool] = mapped_column(Boolean, default=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    purchase_price: Mapped[float] = mapped_column(Float, nullable=False)
    purchase_date: Mapped[Date] = mapped_column(Date, nullable=False)
    condition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SavedSearch(Base):
    __tablename__ = "saved_search"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_text: Mapped[str] = mapped_column(String(255), nullable=False)
    filters_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_run_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)


class ValuationSnapshot(Base):
    __tablename__ = "valuation_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("card.id"), nullable=False, index=True)
    card_parallel_id: Mapped[int | None] = mapped_column(ForeignKey("card_parallel.id"), nullable=True)
    grade_company_id: Mapped[int | None] = mapped_column(ForeignKey("grade_company.id"), nullable=True)
    grade_value: Mapped[str | None] = mapped_column(String(20), nullable=True)
    as_of_date: Mapped[Date] = mapped_column(Date, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_price: Mapped[float] = mapped_column(Float, nullable=False)
    low_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    exact_comp_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    similar_comp_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    methodology: Mapped[str] = mapped_column(String(100), nullable=False)
    reason_codes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    explanation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class IngestionRun(Base):
    __tablename__ = "ingestion_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_platform_id: Mapped[int] = mapped_column(ForeignKey("source_platform.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_upserted_count: Mapped[int] = mapped_column(Integer, default=0)
    normalized_count: Mapped[int] = mapped_column(Integer, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    promoted_count: Mapped[int] = mapped_column(Integer, default=0)
    low_confidence_count: Mapped[int] = mapped_column(Integer, default=0)
    parse_error_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class IngestionIssue(Base):
    __tablename__ = "ingestion_issue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_run.id"), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(40), nullable=False)  # parse_error, unmatched, low_confidence
    source_listing_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    normalized_sale_id: Mapped[int | None] = mapped_column(ForeignKey("normalized_sale.id"), nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
