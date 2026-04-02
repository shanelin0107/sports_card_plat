from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.cards import ValuationOut
from app.services.valuation import compute_card_valuation

router = APIRouter(prefix="/valuations", tags=["valuations"])


@router.get("/cards/{card_id}", response_model=ValuationOut)
def get_card_valuation(card_id: int, window: str = "90d", db: Session = Depends(get_db)):
    result = compute_card_valuation(db=db, card_id=card_id, window=window)
    return ValuationOut(
        card_id=card_id,
        estimated_price=result["estimated_price"],
        low_estimate=result["low_estimate"],
        high_estimate=result["high_estimate"],
        confidence_score=result["confidence_score"],
        exact_comp_count=result["exact_comp_count"],
        similar_comp_count=result["similar_comp_count"],
        method=result["methodology"],
        reason_codes=result["reason_codes"],
        explanation=result["explanation"],
    )
