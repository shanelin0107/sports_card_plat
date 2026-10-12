from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Card, IngestionIssue, IngestionRun, SourcePlatform
from app.services.ingestion.pipeline import IngestionService, resolve_issue_to_card

router = APIRouter(prefix="/internal/ingestion", tags=["ingestion"])

ISSUE_TYPES = ("unmatched", "low_confidence", "parse_error")


def _run_out(r: IngestionRun) -> dict:
    return {
        "id": r.id,
        "mode": r.mode,
        "status": r.status,
        "started_at": r.started_at,
        "completed_at": r.completed_at,
        "fetched_count": r.fetched_count,
        "normalized_count": r.normalized_count,
        "matched_count": r.matched_count,
        "promoted_count": r.promoted_count,
        "low_confidence_count": r.low_confidence_count,
        "parse_error_count": r.parse_error_count,
        "error_message": r.error_message,
    }


def _issue_out(i: IngestionIssue) -> dict:
    return {
        "id": i.id,
        "issue_type": i.issue_type,
        "status": i.status,
        "ingestion_run_id": i.ingestion_run_id,
        "source_listing_id": i.source_listing_id,
        "normalized_sale_id": i.normalized_sale_id,
        "details": i.details_json,
        "created_at": i.created_at,
        "resolved_at": i.resolved_at,
        "resolution_card_id": i.resolution_card_id,
    }


@router.post("/run")
def run_ingestion(
    mode: str = Query(default="daily", pattern="^(daily|hourly)$"),
    tracked_card_ids: str | None = Query(default=None, pattern=r"^\d+(,\d+)*$"),
    db: Session = Depends(get_db),
):
    tracked = [int(x) for x in tracked_card_ids.split(",")] if tracked_card_ids else None
    try:
        run = IngestionService(db).run(mode=mode, tracked_card_ids=tracked)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _run_out(run)


@router.get("/runs")
def list_runs(limit: int = Query(default=20, ge=1, le=200), db: Session = Depends(get_db)):
    runs = db.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(limit)).all()
    return [_run_out(r) for r in runs]


@router.get("/issues")
def list_issues(
    status: str = Query(default="open", pattern="^(open|resolved|dismissed|all)$"),
    issue_type: str | None = Query(default=None, pattern="^(unmatched|low_confidence|parse_error)$"),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(IngestionIssue).order_by(IngestionIssue.created_at.desc()).limit(limit)
    if status != "all":
        stmt = stmt.where(IngestionIssue.status == status)
    if issue_type:
        stmt = stmt.where(IngestionIssue.issue_type == issue_type)
    return [_issue_out(i) for i in db.scalars(stmt).all()]


class ResolveIn(BaseModel):
    card_id: int


@router.post("/issues/{issue_id}/resolve")
def resolve_issue(issue_id: int, body: ResolveIn, db: Session = Depends(get_db)):
    issue = db.get(IngestionIssue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    if issue.status != "open":
        raise HTTPException(status_code=409, detail=f"Issue already {issue.status}")
    if db.get(Card, body.card_id) is None:
        raise HTTPException(status_code=422, detail="Card not found")
    try:
        comp = resolve_issue_to_card(db, issue, body.card_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"issue": _issue_out(issue), "sale_comp_id": comp.id}


@router.post("/issues/{issue_id}/dismiss")
def dismiss_issue(issue_id: int, db: Session = Depends(get_db)):
    issue = db.get(IngestionIssue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    issue.status = "dismissed"
    issue.resolved_at = datetime.now(UTC)
    db.commit()
    return _issue_out(issue)


# Backwards-compatible views used by the README examples
@router.get("/unmatched")
def unmatched(limit: int = 50, db: Session = Depends(get_db)):
    return list_issues(status="open", issue_type="unmatched", limit=limit, db=db)


@router.get("/low-confidence")
def low_confidence(limit: int = 50, db: Session = Depends(get_db)):
    return list_issues(status="open", issue_type="low_confidence", limit=limit, db=db)


@router.get("/parse-errors")
def parse_errors(limit: int = 50, db: Session = Depends(get_db)):
    return list_issues(status="open", issue_type="parse_error", limit=limit, db=db)


@router.get("/source-health")
def source_health(db: Session = Depends(get_db)):
    since = datetime.now(UTC) - timedelta(days=7)
    stats = db.execute(
        select(
            SourcePlatform.name,
            func.count(IngestionRun.id),
            func.coalesce(func.sum(IngestionRun.parse_error_count), 0),
            func.coalesce(func.sum(IngestionRun.promoted_count), 0),
            func.count(IngestionRun.id).filter(IngestionRun.status == "failed"),
            func.max(IngestionRun.started_at),
        )
        .join(IngestionRun, IngestionRun.source_platform_id == SourcePlatform.id)
        .where(IngestionRun.started_at >= since)
        .group_by(SourcePlatform.name)
    ).all()
    open_counts = dict(
        db.execute(
            select(IngestionIssue.issue_type, func.count()).where(IngestionIssue.status == "open").group_by(IngestionIssue.issue_type)
        ).all()
    )
    last = db.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(1)).first()
    return {
        "sources": [
            {
                "source": name,
                "runs_last_7d": int(runs),
                "parse_errors_last_7d": int(perr),
                "promoted_last_7d": int(promoted),
                "failed_runs_last_7d": int(failed),
                "last_run_at": last_at,
                "healthy": int(failed) == 0,
            }
            for name, runs, perr, promoted, failed, last_at in stats
        ],
        "open_issues": {t: int(open_counts.get(t, 0)) for t in ISSUE_TYPES},
        "last_run": _run_out(last) if last else None,
    }
