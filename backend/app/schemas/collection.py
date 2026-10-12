from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class CollectionItemCreate(BaseModel):
    card_id: int
    card_parallel_id: int | None = None
    grade_company_id: int | None = None
    grade_value: str | None = Field(default=None, max_length=20)
    is_graded: bool = False
    quantity: int = Field(default=1, ge=1, le=10_000)
    purchase_price: float = Field(ge=0)
    purchase_date: date
    condition: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    image_url: str | None = None
    uploaded_image_path: str | None = None

    @model_validator(mode="after")
    def _graded_consistency(self):
        if self.grade_value in ("", None):
            self.grade_value = None
        if self.grade_value is not None:
            self.is_graded = True
        if not self.is_graded:
            self.grade_company_id = None
            self.grade_value = None
        return self


class CollectionItemOut(CollectionItemCreate):
    id: int
    owner_profile_id: int
    created_at: datetime | None = None
    # Card identity, so the UI never has to show "Card #2"
    title: str | None = None
    player: str | None = None
    year: int | None = None
    brand: str | None = None
    card_set: str | None = None
    card_number: str | None = None
    parallel: str | None = None
    rookie_flag: bool = False
    card_image_url: str | None = None
    photo_version: str | None = None  # set when the owner uploaded a photo for this holding
    grade_label: str = "Raw"
    # Valuation
    estimated_value: float | None = None
    estimated_unit_price: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None
    confidence_score: float | None = None
    valuation_method: str | None = None
    exact_comp_count: int = 0
    spark: list[float] = []


class PhotoUpload(BaseModel):
    content_type: str = Field(pattern=r"^image/(jpeg|png|webp)$")
    data_base64: str = Field(max_length=4_000_000)  # ~3 MB decoded
