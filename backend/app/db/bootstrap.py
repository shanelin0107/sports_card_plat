"""Idempotent database bootstrap.

Runs scripts/init_db.sql (CREATE ... IF NOT EXISTS + additive migrations) on startup,
then loads seed/demo_seed.sql when the catalog is empty. This lets a fresh hosted
Postgres (Neon, Render, ...) come up without a manual psql step, and upgrades an
existing local database in place.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.core.config import PROJECT_ROOT, settings
from app.db.session import engine

logger = logging.getLogger(__name__)

INIT_SQL = PROJECT_ROOT / "scripts" / "init_db.sql"
SEED_SQL = PROJECT_ROOT / "seed" / "demo_seed.sql"


def _exec_script(path) -> None:
    sql = path.read_text()
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(sql)
        raw.commit()
    finally:
        raw.close()


def bootstrap_database() -> None:
    if not settings.auto_init_db:
        return
    if not INIT_SQL.exists():
        logger.warning("init_db.sql not found at %s; skipping bootstrap", INIT_SQL)
        return
    _exec_script(INIT_SQL)
    logger.info("Schema ensured from %s", INIT_SQL)

    if settings.seed_demo_data and SEED_SQL.exists():
        with engine.connect() as conn:
            empty = conn.execute(text("SELECT NOT EXISTS (SELECT 1 FROM sport)")).scalar()
        if empty:
            _exec_script(SEED_SQL)
            logger.info("Loaded demo seed data")

    # Built-in insert / SSP set guides (seed/sets/*.json), added once.
    from app.db.session import SessionLocal
    from app.services.set_guide import load_seeds

    with SessionLocal() as db:
        load_seeds(db)
