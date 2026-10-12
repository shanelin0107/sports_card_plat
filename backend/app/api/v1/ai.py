from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models.entities import AiPriceResearch, Brand, Card, CardParallel, CardSet, Player
from app.services.ai_research import ai_enabled, execute_job
from app.services.comps import CompError, create_confirmed_comp, listing_key

router = APIRouter(prefix="/ai", tags=["ai"])


class ResearchIn(BaseModel):
    query: str | None = Field(default=None, max_length=300)
    card_id: int | None = None
    grade: str | None = Field(default=None, max_length=20)
    auto_save: bool = False  # save exact, dated, verified sales without asking


class SaveCompIn(BaseModel):
    index: int = Field(ge=0)
    card_id: int | None = None  # defaults to the job's card


def _out(job: AiPriceResearch) -> dict:
    result = {k: v for k, v in (job.result_json or {}).items() if not k.startswith("_")}
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


STALE_AFTER_MINUTES = 15  # a run takes 30-90 s; anything older died with a restart


def expire_stale_jobs(db: Session) -> None:
    """A job left "running" by a server restart would block that card's AI search forever."""
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(minutes=STALE_AFTER_MINUTES)
    stale = db.scalars(
        select(AiPriceResearch).where(AiPriceResearch.status == "running", AiPriceResearch.created_at < cutoff)
    ).all()
    for job in stale:
        job.status = "failed"
        job.error_message = "Interrupted (the server restarted). Run it again."
        job.completed_at = datetime.now(UTC)
    if stale:
        db.commit()


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

    job = start_job(db, background, query=query, card_id=body.card_id, grade=body.grade, ctx=ctx, auto_save=body.auto_save)
    return _out(job)


def start_job(db: Session, background: BackgroundTasks, *, query: str, card_id: int | None, grade: str | None, ctx: dict | None, auto_save: bool):
    meta: dict = {}
    if ctx:
        meta["_card_context"] = ctx
    if auto_save:
        meta["_auto_save"] = True
    job = AiPriceResearch(
        card_id=card_id,
        query=query,
        grade=grade,
        status="running",
        model=settings.ai_model,
        result_json=meta or None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background.add_task(execute_job, job.id, SessionLocal)
    return job


@router.get("/price-research")
def list_research(card_id: int | None = None, limit: int = Query(default=10, ge=1, le=50), db: Session = Depends(get_db)):
    expire_stale_jobs(db)
    stmt = select(AiPriceResearch).order_by(AiPriceResearch.created_at.desc()).limit(limit)
    if card_id is not None:
        stmt = stmt.where(AiPriceResearch.card_id == card_id)
    return [_out(j) for j in db.scalars(stmt).all()]


@router.get("/price-research/{job_id}")
def get_research(job_id: int, db: Session = Depends(get_db)):
    expire_stale_jobs(db)
    job = db.get(AiPriceResearch, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research not found")
    return _out(job)


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
    try:
        comp, created = create_confirmed_comp(
            db,
            card_id=card_id,
            listing_id=listing_key(item.get("url"), f"ai-{job.id}-{body.index}"),
            title=item.get("title", ""),
            url=item["url"],
            price=float(item["price"]),
            date=item.get("date"),
            grade=item.get("grade"),
            source=item.get("source", ""),
            match_method="ai_research_confirmed",
            payload={"ai_research_id": job.id, "item": item},
        )
    except CompError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    item["saved_comp_id"] = comp.id
    item["saved_at"] = datetime.now(UTC).isoformat()
    flag_modified(job, "result_json")
    db.commit()
    return {"sale_comp_id": comp.id, "already_saved": not created}
