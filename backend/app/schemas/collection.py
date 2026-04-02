from datetime import date

from pydantic import BaseModel


class CollectionItemCreate(BaseModel):
    card_id: int
    card_parallel_id: int | None = None
    grade_company_id: int | None = None
    grade_value: str | None = None
    is_graded: bool = False
    quantity: int = 1
    purchase_price: float
    purchase_date: date
    condition: str | None = None
    notes: str | None = None
    image_url: str | None = None
    uploaded_image_path: str | None = None


class CollectionItemOut(CollectionItemCreate):
    id: int
    owner_profile_id: int
    estimated_value: float | None = None
    unrealized_pnl: float | None = None
