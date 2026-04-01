from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import IngestionIssue, IngestionRun, NormalizedSale, SourcePlatform
from app.services.ingestion.pipeline import IngestionService

router = APIRouter(prefix="/internal/ingestion", tags=["ingestion"])


@router.post("/run")
def run_ingestion(
    mode: str = Query(default="daily", pattern="^(daily|hourly)$"),
    tracked_card_ids: str | None = None,
    db: Session = Depends(get_db),
):
    tracked = [int(x) for x in tracked_card_ids.split(",")] if tracked_card_ids else None
    service = IngestionService(db)
    run = service.run(mode=mode, tracked_card_ids=tracked)
    return {"run_id": run.id, "status": run.status, "fetched": run.fetched_count, "promoted": run.promoted_count}


@router.get("/runs")
def list_runs(limit: int = 20, db: Session = Depends(get_db)):
    runs = db.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(limit)).all()
    return [
        {
            "id": r.id,
            "mode": r.mode,
            "status": r.status,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "fetched_count": r.fetched_count,
            "promoted_count": r.promoted_count,
            "parse_error_count": r.parse_error_count,
        }
        for r in runs
    ]


@router.get("/unmatched")
def unmatched(limit: int = 50, db: Session = Depends(get_db)):
    issues = db.scalars(
        select(IngestionIssue)
        .where(IngestionIssue.issue_type == "unmatched")
        .order_by(IngestionIssue.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": i.id,
            "ingestion_run_id": i.ingestion_run_id,
            "source_listing_id": i.source_listing_id,
            "details": i.details_json,
        }
        for i in issues
    ]


@router.get("/low-confidence")
def low_confidence(limit: int = 50, db: Session = Depends(get_db)):
    issues = db.scalars(
        select(IngestionIssue)
        .where(IngestionIssue.issue_type == "low_confidence")
        .order_by(IngestionIssue.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": i.id,
            "ingestion_run_id": i.ingestion_run_id,
            "source_listing_id": i.source_listing_id,
            "details": i.details_json,
        }
        for i in issues
    ]


@router.get("/parse-errors")
def parse_errors(limit: int = 50, db: Session = Depends(get_db)):
    issues = db.scalars(
        select(IngestionIssue)
        .where(IngestionIssue.issue_type == "parse_error")
        .order_by(IngestionIssue.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": i.id,
            "ingestion_run_id": i.ingestion_run_id,
            "source_listing_id": i.source_listing_id,
            "details": i.details_json,
        }
        for i in issues
    ]


@router.get("/source-health")
def source_health(db: Session = Depends(get_db)):
    since = datetime.now(UTC) - timedelta(days=7)
    stats = db.execute(
        select(SourcePlatform.name, func.count(IngestionRun.id), func.sum(IngestionRun.parse_error_count))
        .join(IngestionRun, IngestionRun.source_platform_id == SourcePlatform.id)
        .where(IngestionRun.started_at >= since)
        .group_by(SourcePlatform.name)
    ).all()

    return [
        {
            "source": name,
            "runs_last_7d": int(run_count or 0),
            "parse_errors_last_7d": int(parse_errors or 0),
        }
        for name, run_count, parse_errors in stats
    ]
