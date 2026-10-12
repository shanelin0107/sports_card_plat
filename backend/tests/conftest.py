"""Integration tests run against a real Postgres (the app uses Postgres-specific SQL).

Set TEST_DATABASE_URL to an empty, disposable database, e.g.
  TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/sports_cards_test
Tests that need the DB are skipped when it is not set.
"""

import os

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB
    os.environ["API_KEY"] = ""
    os.environ["SEED_DEMO_DATA"] = "true"


@pytest.fixture()
def client():
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL not set")
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app.db.session import engine
    from app.main import app

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    with TestClient(app) as c:  # lifespan -> bootstrap schema + seed
        yield c
