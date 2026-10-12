from datetime import datetime

from pydantic import BaseModel


class CardSearchResultOut(BaseModel):
    id: int
    title: str
    year: int
    card_number: str
    brand: str
    card_set: str
    player: str
    rookie_flag: bool = False
    default_image_url: str | None
    photo_item_id: int | None = None
    photo_version: str | None = None
    valuation_preview: float | None
    comp_count: int = 0


class CardMetadataOut(BaseModel):
    id: int
    title: str
    slug: str
    year: int
    card_number: str
    brand: str
    card_set: str
    player: str
    sport: str | None = None
    parallel: str | None = None
    print_run: int | None = None
    rookie_flag: bool
    autograph_flag: bool
    patch_flag: bool
    default_image_url: str | None
    photo_item_id: int | None = None
    photo_version: str | None = None


class CardStatsOut(BaseModel):
    card_id: int
    window: str
    count: int
    average_price: float | None
    median_price: float | None


class CompOut(BaseModel):
    id: int
    sold_at: datetime
    total_price: float
    grade_value: str | None
    grade_label: str


class SalesHistoryPricePoint(BaseModel):
    date: str
    avg_price: float | None
    median_price: float | None


class SalesHistoryVolumePoint(BaseModel):
    date: str
    sale_count: int


class SalesHistoryOut(BaseModel):
    card_id: int
    window: str
    bucket: str
    grade: str
    price_series: list[SalesHistoryPricePoint]
    volume_series: list[SalesHistoryVolumePoint]


class RawVsPsaComparisonOut(BaseModel):
    card_id: int
    window: str
    raw_count: int
    psa10_count: int
    raw_median: float | None
    psa10_median: float | None
    grading_premium: float | None = None


class ValuationOut(BaseModel):
    card_id: int
    grade: str = "All grades"
    estimated_price: float | None
    low_estimate: float | None
    high_estimate: float | None
    confidence_score: float
    exact_comp_count: int
    similar_comp_count: int
    method: str
    reason_codes: list[str]
    explanation: str
    window_used: str | None = None
    last_sale_at: datetime | None = None


class GradeOptionOut(BaseModel):
    key: str  # "raw" | "psa10" | "psa9" ...
    label: str
    comp_count: int


class CardDetailOut(BaseModel):
    metadata: CardMetadataOut
    valuation: ValuationOut
    stats: CardStatsOut
    comparison: RawVsPsaComparisonOut
    grades: list[GradeOptionOut] = []
