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
    default_image_url: str | None
    valuation_preview: float | None


class CardMetadataOut(BaseModel):
    id: int
    title: str
    slug: str
    year: int
    card_number: str
    brand: str
    card_set: str
    player: str
    rookie_flag: bool
    autograph_flag: bool
    patch_flag: bool
    default_image_url: str | None


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
    price_series: list[SalesHistoryPricePoint]
    volume_series: list[SalesHistoryVolumePoint]


class RawVsPsaComparisonOut(BaseModel):
    card_id: int
    window: str
    raw_count: int
    psa10_count: int
    raw_median: float | None
    psa10_median: float | None


class ValuationOut(BaseModel):
    card_id: int
    estimated_price: float | None
    low_estimate: float | None
    high_estimate: float | None
    confidence_score: float
    exact_comp_count: int
    similar_comp_count: int
    method: str
    reason_codes: list[str]
    explanation: str


class CardDetailOut(BaseModel):
    metadata: CardMetadataOut
    valuation: ValuationOut
    stats: CardStatsOut
    comparison: RawVsPsaComparisonOut
