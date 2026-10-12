from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models.entities import (
    AiPriceResearch,
    Brand,
    Card,
    CardParallel,
    CardSet,
    GradeCompany,
    ListingCardMatch,
    NormalizedSale,
    Player,
    RawMarketListing,
    SaleComp,
    SourcePlatform,
)
from app.services.ai_research import ai_enabled, execute_job
from app.services.ingestion.parsing import parse_sold_at, parse_title

router = APIRouter(prefix="/ai", tags=["ai"])


class ResearchIn(BaseModel):
    query: str | None = Field(default=None, max_length=300)
    card_id: int | None = None
    grade: str | None = Field(default=None, max_length=20)


class SaveCompIn(BaseModel):
    index: int = Field(ge=0)
    card_id: int | None = None  # defaults to the job's card


def _out(job: AiPriceResearch) -> dict:
    result = dict(job.result_json or {})
    result.pop("_card_context", None)
    return {
        "id": job.id,
        "card_id": job.card_id,
        "query": job.query,
        "grade": job.grade,
        "status": job.status,
        "model": job.model,
        "result": result if job.status == "completed" else None,
        "error_message": job.error_message,
        "searches_used": job.searches_used,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
    }


def _card_context(db: Session, card_id: int) -> tuple[str, dict]:
    row = db.execute(
        select(Card, Brand.name, CardSet.name, Player.full_name)
        .join(Brand, Brand.id == Card.brand_id)
        .join(CardSet, CardSet.id == Card.set_id)
        .join(Player, Player.id == Card.player_id)
        .where(Card.id == card_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Card not found")
    card, brand, card_set, player = row
    parallels = [p for (p,) in db.execute(select(CardParallel.parallel_name).where(CardParallel.card_id == card_id)).all()]
    named = [p for p in parallels if p.lower() != "base"]
    query = f"{card.year} {card_set} {player} #{card.card_number}" + (f" {named[0]}" if len(named) == 1 else "")
    ctx = {
        "year": card.year,
        "product": card_set,
        "brand": brand,
        "player": player,
        "card_number": card.card_number,
        "parallels_on_file": ", ".join(parallels) or None,
        "rookie": bool(card.rookie_flag),
        "autograph": bool(card.autograph_flag),
    }
    return query, ctx


@router.get("/status")
def ai_status():
    return {"enabled": ai_enabled(), "model": settings.ai_model if ai_enabled() else None}


@router.post("/price-research", status_code=202)
def start_research(body: ResearchIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    if not ai_enabled():
        raise HTTPException(status_code=503, detail="AI price research is off: set ANTHROPIC_API_KEY on the backend.")
    ctx = None
    query = (body.query or "").strip()
    if body.card_id is not None:
        card_query, ctx = _card_context(db, body.card_id)
        query = query or card_query
    if not query:
        raise HTTPException(status_code=422, detail="Give a card description or card_id")

    job = AiPriceResearch(
        card_id=body.card_id,
        query=query,
        grade=body.grade,
        status="running",
        model=settings.ai_model,
        result_json={"_card_context": ctx} if ctx else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background.add_task(execute_job, job.id, SessionLocal)
    return _out(job)


@router.get("/price-research")
def list_research(card_id: int | None = None, limit: int = Query(default=10, ge=1, le=50), db: Session = Depends(get_db)):
    stmt = select(AiPriceResearch).order_by(AiPriceResearch.created_at.desc()).limit(limit)
    if card_id is not None:
        stmt = stmt.where(AiPriceResearch.card_id == card_id)
    return [_out(j) for j in db.scalars(stmt).all()]


@router.get("/price-research/{job_id}")
def get_research(job_id: int, db: Session = Depends(get_db)):
    job = db.get(AiPriceResearch, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research not found")
    return _out(job)


def _source_platform(db: Session, url: str, fallback: str) -> SourcePlatform:
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    name = "eBay" if host.startswith("ebay.") else (fallback or host or "Web")[:100]
    src = db.scalars(select(SourcePlatform).where(SourcePlatform.name == name)).first()
    if src is None:
        src = SourcePlatform(name=name, source_type="ai_research")
        db.add(src)
        db.flush()
    return src


@router.post("/price-research/{job_id}/save-comp")
def save_comp(job_id: int, body: SaveCompIn, db: Session = Depends(get_db)):
    """Owner-confirmed: turn one AI-found sold record into a real comp."""
    job = db.get(AiPriceResearch, job_id)
    if job is None or job.status != "completed":
        raise HTTPException(status_code=404, detail="Completed research not found")
    sold = (job.result_json or {}).get("sold") or []
    if body.index >= len(sold):
        raise HTTPException(status_code=422, detail="No such sold record")
    item = sold[body.index]
    if item.get("saved_comp_id"):
        return {"sale_comp_id": item["saved_comp_id"], "already_saved": True}

    card_id = body.card_id or job.card_id
    if card_id is None or db.get(Card, card_id) is None:
        raise HTTPException(status_code=422, detail="Pick the catalog card this sale belongs to")
    sold_at = parse_sold_at(item.get("date"))
    if sold_at is None:
        raise HTTPException(status_code=422, detail="This record has no sale date, so it can't be used as a comp")

    parsed = parse_title(item.get("title", ""), item.get("grade"))
    grade_value = None if (item.get("grade") or "").strip().lower() in ("", "raw") else parsed.grade_value
    company_id = None
    if grade_value and parsed.grader:
        company_id = db.scalars(select(GradeCompany.id).where(GradeCompany.name == parsed.grader)).first()
        if company_id is None:
            gc = GradeCompany(name=parsed.grader)
            db.add(gc)
            db.flush()
            company_id = gc.id

    src = _source_platform(db, item["url"], item.get("source", ""))
    listing_id = f"ai-{job.id}-{body.index}"
    raw = RawMarketListing(
        source_platform_id=src.id,
        source_listing_id=listing_id,
        sold_at_raw=item.get("date"),
        listing_title_raw=item.get("title", "")[:2000],
        listing_url_raw=item["url"],
        condition_raw=item.get("grade"),
        price_raw=str(item["price"]),
        shipping_raw="0",
        payload_json={"ai_research_id": job.id, "item": item},
    )
    db.add(raw)
    db.flush()
    norm = NormalizedSale(
        raw_market_listing_id=raw.id,
        source_platform_id=src.id,
        source_listing_id=listing_id,
        sold_at=sold_at,
        sale_price=float(item["price"]),
        shipping_price=0.0,
        total_price=float(item["price"]),
        currency="USD",
        grade_company_id=company_id,
        grade_value=grade_value,
        parsed_year=parsed.year,
        parsed_card_number=parsed.card_number,
        normalized_notes="Added from AI price research after owner confirmation",
    )
    db.add(norm)
    db.flush()
    db.add(
        ListingCardMatch(
            normalized_sale_id=norm.id,
            card_id=card_id,
            match_method="ai_research_confirmed",
            confidence_score=1.0,
            is_primary=True,
            reason_codes=["OWNER_CONFIRMED", "AI_RESEARCH"],
        )
    )
    comp = SaleComp(
        normalized_sale_id=norm.id,
        card_id=card_id,
        grade_company_id=company_id,
        grade_value=grade_value,
        sold_at=sold_at,
        sale_price=float(item["price"]),
        shipping_price=0.0,
        total_price=float(item["price"]),
        currency="USD",
    )
    db.add(comp)
    db.flush()

    item["saved_comp_id"] = comp.id
    item["saved_at"] = datetime.now(UTC).isoformat()
    flag_modified(job, "result_json")
    db.commit()
    return {"sale_comp_id": comp.id, "already_saved": False}
