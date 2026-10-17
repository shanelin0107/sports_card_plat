from datetime import date, timedelta


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_dashboard_values_by_holding_grade(client):
    s = client.get("/api/v1/dashboard/summary").json()
    # Ohtani PSA10 = median(185, 180) = 182.5 ; Wemby PSA10 = 430 (PSA 9 sale excluded)
    assert s["cost_basis"] == 540.0
    assert s["estimated_value"] == 612.5
    assert s["unrealized_pnl"] == 72.5


def test_multi_token_search(client):
    r = client.get("/api/v1/cards/search", params={"q": "2023 topps ohtani psa 10"}).json()
    assert [c["id"] for c in r] == [1]
    assert r[0]["valuation_preview"] == 182.5
    assert client.get("/api/v1/cards/search", params={"q": "100%_"}).json() == []


def test_ingestion_is_idempotent_and_review_queue(client):
    first = client.post("/api/v1/internal/ingestion/run").json()
    assert first["status"] == "completed"
    assert first["promoted_count"] == 2
    second = client.post("/api/v1/internal/ingestion/run").json()
    assert second["status"] == "completed"
    assert second["promoted_count"] == 0  # nothing new the second time

    issues = client.get("/api/v1/internal/ingestion/issues").json()
    kinds = sorted(i["issue_type"] for i in issues)
    assert kinds == ["low_confidence", "parse_error", "unmatched"]  # no duplicates after 2 runs

    unmatched = next(i for i in issues if i["issue_type"] == "unmatched")
    card = client.post(
        "/api/v1/catalog/cards",
        json={"sport": "Baseball", "year": 2023, "brand": "Topps", "set_name": "Chrome", "player": "Julio Rodriguez", "card_number": "10"},
    ).json()
    r = client.post(f"/api/v1/internal/ingestion/issues/{unmatched['id']}/resolve", json={"card_id": card["card_id"]})
    assert r.status_code == 200
    assert client.get(f"/api/v1/cards/{card['card_id']}").json()["valuation"]["estimated_price"] == 125.0


def test_collection_crud_and_validation(client):
    bad = client.post("/api/v1/collection/items", json={"card_id": 999, "purchase_price": 1, "purchase_date": "2026-01-01"})
    assert bad.status_code == 422
    new = client.post(
        "/api/v1/collection/items",
        json={"card_id": 1, "purchase_price": 80, "purchase_date": "2026-02-01", "is_graded": False},
    )
    assert new.status_code == 201
    item = new.json()
    assert item["grade_label"] == "Raw" and item["estimated_unit_price"] == 100.0
    upd = client.put(
        f"/api/v1/collection/items/{item['id']}",
        json={"card_id": 1, "purchase_price": 85, "purchase_date": "2026-02-01", "grade_company_id": 1, "grade_value": "10"},
    ).json()
    assert upd["is_graded"] and upd["grade_label"] == "PSA 10"
    assert client.delete(f"/api/v1/collection/items/{item['id']}").json() == {"deleted": True}


def test_daily_change_from_snapshots(client):
    from app.db.session import SessionLocal
    from app.models.entities import ValuationSnapshot

    client.get("/api/v1/dashboard/summary")  # records today's snapshot
    with SessionLocal() as db:
        db.add(
            ValuationSnapshot(
                card_id=2, grade_company_id=1, grade_value="10", as_of_date=date.today() - timedelta(days=1),
                window_days=90, estimated_price=400.0, confidence_score=0.5, exact_comp_count=1,
                similar_comp_count=0, methodology="test",
            )
        )
        db.commit()
    s = client.get("/api/v1/dashboard/summary").json()
    assert s["daily_change"] == 30.0
    assert s["gainers"][0]["card_id"] == 2


def test_api_key_guard(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_key", "secret")
    assert client.get("/api/v1/dashboard/summary").status_code == 401
    assert client.get("/api/v1/dashboard/summary", headers={"X-API-Key": "secret"}).status_code == 200


def test_holding_photo_roundtrip(client):
    import base64

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    item_id = client.get("/api/v1/collection/items").json()[0]["id"]
    assert client.get(f"/api/v1/collection/items/{item_id}/photo").status_code == 404

    bad = client.put(f"/api/v1/collection/items/{item_id}/photo", json={"content_type": "image/jpeg", "data_base64": base64.b64encode(png).decode()})
    assert bad.status_code == 422  # PNG bytes labelled as JPEG

    r = client.put(f"/api/v1/collection/items/{item_id}/photo", json={"content_type": "image/png", "data_base64": base64.b64encode(png).decode()})
    assert r.status_code == 200 and r.json()["photo_version"]
    img = client.get(f"/api/v1/collection/items/{item_id}/photo")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content == png

    card_id = r.json()["card_id"]
    assert client.get(f"/api/v1/cards/{card_id}").json()["metadata"]["photo_item_id"] == item_id

    assert client.delete(f"/api/v1/collection/items/{item_id}/photo").json()["photo_version"] is None
    # deleting the holding also removes its photo (FK cascade)
    client.put(f"/api/v1/collection/items/{item_id}/photo", json={"content_type": "image/png", "data_base64": base64.b64encode(png).decode()})
    assert client.delete(f"/api/v1/collection/items/{item_id}").status_code == 200


def test_catalog_cleans_player_and_edit(client):
    c = client.post("/api/v1/catalog/cards", json={"sport": "Basketball", "year": 2024, "brand": "Panini", "set_name": "Prizm Black",
                                                   "player": "Damian Lillard /60", "card_number": "91", "parallel": "Orange", "print_run": 60}).json()
    d = client.get(f"/api/v1/cards/{c['card_id']}").json()["metadata"]
    assert d["player"] == "Damian Lillard"
    e = client.patch(f"/api/v1/catalog/cards/{c['card_id']}", json={"parallel": "Orange Wave", "player": "Damian Lillard"}).json()
    assert e["parallel"] == "Orange Wave" and e["print_run"] == 60 and e["title"] == "2024 Panini Prizm Black Damian Lillard #91"
    assert client.get("/api/v1/cards/search", params={"q": "lillard orange wave"}).json()[0]["id"] == c["card_id"]


def test_manual_sale_and_links(client):
    links = client.get("/api/v1/market/sold-links/1", params={"grade": "psa10"}).json()
    assert "PSA+10" in links["links"][0]["url"] and "LH_Sold=1" in links["links"][0]["url"]
    r = client.post("/api/v1/market/sales/1", json={"price": 200, "shipping": 5, "date": "2026-10-01", "grade": "PSA 10",
                                                    "url": "https://www.ebay.com/itm/2024-topps-ohtani/123456789012"})
    assert r.status_code == 201 and r.json()["total_price"] == 205.0
    dup = client.post("/api/v1/market/sales/1", json={"price": 200, "date": "2026-10-01", "grade": "PSA 10",
                                                      "url": "https://www.ebay.com/itm/123456789012"})
    assert dup.status_code == 409
    assert client.post("/api/v1/market/sales/1", json={"price": 10, "date": "2999-01-01"}).status_code == 422
    raw = client.post("/api/v1/market/sales/1", json={"price": 90, "date": "2026-10-02"})  # no link, raw
    assert raw.status_code == 201
    ms = client.get("/api/v1/cards/1/market-summary", params={"grade": "psa10", "window": "all"}).json()
    assert any(s["price"] == 205.0 and s["source"] == "eBay" for s in ms["sales"])
    ms_raw = client.get("/api/v1/cards/1/market-summary", params={"grade": "raw", "window": "all"}).json()
    assert any(s["price"] == 90.0 and s["source"] == "Manual" for s in ms_raw["sales"])


def test_no_estimate_from_other_cards_until_this_card_sells(client):
    base = {"sport": "Football", "year": 2024, "brand": "Panini", "set_name": "Prizm", "player": "Test Rookie"}
    peer = client.post("/api/v1/catalog/cards", json={**base, "card_number": "1"}).json()["card_id"]
    mine = client.post("/api/v1/catalog/cards", json={**base, "card_number": "329", "parallel": "Lazer"}).json()["card_id"]
    for d in ("2026-10-01", "2026-10-02", "2026-10-03"):
        assert client.post(f"/api/v1/market/sales/{peer}", json={"price": 20, "date": d}).status_code == 201
    # Sales of a different card must not price this one.
    v = client.get(f"/api/v1/valuations/cards/{mine}", params={"grade": "raw"}).json()
    assert v["estimated_price"] is None
    assert client.post(f"/api/v1/market/sales/{mine}", json={"price": 32, "date": "2026-10-04"}).status_code == 201
    v = client.get(f"/api/v1/valuations/cards/{mine}", params={"grade": "raw"}).json()
    assert v["estimated_price"] is not None and v["exact_comp_count"] == 1


def test_trend_is_one_point_per_day(client):
    from datetime import date, timedelta

    card = client.post("/api/v1/catalog/cards", json={"sport": "Football", "year": 2024, "brand": "Panini",
                                                      "set_name": "Prizm", "player": "Trend Test", "card_number": "7"}).json()["card_id"]
    d0, d1 = (date.today() - timedelta(days=3)).isoformat(), (date.today() - timedelta(days=1)).isoformat()
    for d, p in [(d0, 10), (d0, 30), (d0, 20), (d1, 50)]:
        assert client.post(f"/api/v1/market/sales/{card}", json={"price": p, "date": d}).status_code == 201
    ms = client.get(f"/api/v1/cards/{card}/market-summary", params={"grade": "raw", "window": "30d"}).json()
    assert ms["trend_days"] == 7
    assert ms["trend"] == [{"date": d0, "median": 20.0, "n": 3}, {"date": d1, "median": 25.0, "n": 4}]
    assert all(s["ts"].startswith(s["date"]) for s in ms["sales"])


def test_outlier_left_out_of_estimate_and_trend(client):
    from datetime import date, timedelta

    card = client.post("/api/v1/catalog/cards", json={"sport": "Football", "year": 2024, "brand": "Panini",
                                                      "set_name": "Prizm", "player": "Outlier Test", "card_number": "9"}).json()["card_id"]
    d = (date.today() - timedelta(days=2)).isoformat()
    for p in (24, 26, 25, 27, 140):
        client.post(f"/api/v1/market/sales/{card}", json={"price": p, "date": d})
    v = client.get(f"/api/v1/valuations/cards/{card}", params={"grade": "raw"}).json()
    assert v["estimated_price"] == 25.5 and v["exact_comp_count"] == 4
    ms = client.get(f"/api/v1/cards/{card}/market-summary", params={"grade": "raw"}).json()
    assert ms["count"] == 5 and ms["outliers"] == 1 and ms["median"] == 25.5 and ms["high"] == 27
    assert [s["price"] for s in ms["sales"] if s["outlier"]] == [140.0]
    assert ms["trend"][-1]["median"] == 25.5


def test_thin_card_is_not_priced_off_other_cards(client):
    from datetime import date, timedelta

    base = {"sport": "Football", "year": 2024, "brand": "Panini", "set_name": "Prizm", "player": "Thin Test"}
    peer = client.post("/api/v1/catalog/cards", json={**base, "card_number": "1"}).json()["card_id"]
    mine = client.post("/api/v1/catalog/cards", json={**base, "card_number": "2", "parallel": "Lazer"}).json()["card_id"]
    d = (date.today() - timedelta(days=3)).isoformat()
    for _ in range(5):
        client.post(f"/api/v1/market/sales/{peer}", json={"price": 5, "date": d})
    client.post(f"/api/v1/market/sales/{mine}", json={"price": 32, "date": d})
    v = client.get(f"/api/v1/valuations/cards/{mine}", params={"grade": "raw"}).json()
    assert v["estimated_price"] == 32.0 and v["exact_comp_count"] == 1
    assert v["confidence_score"] <= 0.5


def test_removed_sale_can_be_added_back_by_hand_but_not_by_sync(client):
    from datetime import date, timedelta

    base = {"sport": "Football", "year": 2024, "brand": "Panini", "set_name": "Prizm", "player": "Restore Test"}
    a = client.post("/api/v1/catalog/cards", json={**base, "card_number": "1"}).json()["card_id"]
    b = client.post("/api/v1/catalog/cards", json={**base, "card_number": "2"}).json()["card_id"]
    d = (date.today() - timedelta(days=1)).isoformat()
    sale = {"price": 40, "date": d, "url": "https://www.ebay.com/itm/555666777888"}
    comp = client.post(f"/api/v1/market/sales/{a}", json=sale).json()["sale_comp_id"]
    other = client.post(f"/api/v1/market/sales/{b}", json=sale)
    assert other.status_code == 409 and "another card" in other.json()["detail"]
    assert client.delete(f"/api/v1/cards/{a}/comps/{comp}").json() == {"deleted": True}
    back = client.post(f"/api/v1/market/sales/{a}", json=sale)
    assert back.status_code == 201
    again = client.post(f"/api/v1/market/sales/{a}", json=sale)
    assert again.status_code == 409 and "already" in again.json()["detail"]


def test_search_preview_never_mixes_grades(client):
    from datetime import date, timedelta

    card = client.post("/api/v1/catalog/cards", json={"sport": "Football", "year": 2024, "brand": "Panini",
                                                      "set_name": "Prizm", "player": "Preview Grade", "card_number": "5"}).json()["card_id"]
    d = (date.today() - timedelta(days=1)).isoformat()
    for p in (20, 22, 21):
        client.post(f"/api/v1/market/sales/{card}", json={"price": p, "date": d})
    for p in (200, 210):
        client.post(f"/api/v1/market/sales/{card}", json={"price": p, "date": d, "grade": "PSA 10"})
    hit = lambda q: next(r for r in client.get("/api/v1/cards/search", params={"q": q}).json() if r["id"] == card)
    assert hit("preview grade")["valuation_preview"] == 21.0  # most-traded grade (raw)
    assert hit("preview grade psa10")["valuation_preview"] == 205.0
    assert hit("preview grade raw")["valuation_preview"] == 21.0


def test_each_parallel_is_its_own_card(client):
    base = {"sport": "Football", "year": 2024, "brand": "Panini", "set_name": "Prizm", "player": "Parallel Test", "card_number": "329"}
    b = client.post("/api/v1/catalog/cards", json=base).json()["card_id"]
    lz = client.post("/api/v1/catalog/cards", json={**base, "parallel": "Lazer Prizm"}).json()["card_id"]
    sv = client.post("/api/v1/catalog/cards", json={**base, "parallel": "Silver Prizm"}).json()["card_id"]
    assert len({b, lz, sv}) == 3
    # asking again finds the same card
    assert client.post("/api/v1/catalog/cards", json={**base, "parallel": "lazer prizm"}).json()["card_id"] == lz
    assert client.post("/api/v1/catalog/cards", json=base).json()["card_id"] == b


def test_legacy_card_without_parallel_in_slug_is_reused():
    import os

    if not os.environ.get("TEST_DATABASE_URL"):
        import pytest

        pytest.skip("needs DB")
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app.db.session import engine
    from app.main import app

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    with TestClient(app) as c:
        base = {"sport": "Football", "year": 2024, "brand": "Panini", "set_name": "Prizm", "player": "Legacy Test", "card_number": "7"}
        lz = c.post("/api/v1/catalog/cards", json={**base, "parallel": "Lazer"}).json()["card_id"]
        with engine.begin() as conn:  # pretend it was created by the old code (slug without parallel)
            conn.execute(text("UPDATE card SET slug = '2024-panini-prizm-legacy-test-7' WHERE id = :i"), {"i": lz})
        assert c.post("/api/v1/catalog/cards", json={**base, "parallel": "Lazer"}).json()["card_id"] == lz
        assert c.post("/api/v1/catalog/cards", json=base).json()["card_id"] != lz  # base is a different card


def test_listing_key_is_one_id_per_ebay_sale():
    from app.services.comps import listing_key

    assert listing_key("https://www.ebay.com/itm/2024-prizm-maye/123456789012?hash=x", "ai-1-0") == "ebay-123456789012"
    assert listing_key("https://www.ebay.com/itm/123456789012", "x") == "ebay-123456789012"
    assert listing_key("https://130point.com/sales/abc", "ai-1-0") == "ai-1-0"


def test_stuck_ai_job_is_expired(client):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    from app.db.session import engine

    with engine.begin() as conn:
        jid = conn.execute(text("INSERT INTO ai_price_research (query, status, created_at) VALUES ('x', 'running', :t) RETURNING id"),
                           {"t": datetime.now(UTC) - timedelta(hours=1)}).scalar()
    j = client.get(f"/api/v1/ai/price-research/{jid}").json()
    assert j["status"] == "failed" and "restarted" in j["error_message"]


def test_reingest_does_not_resurrect_a_removed_sale(client):
    from sqlalchemy import text

    from app.db.session import engine

    client.post("/api/v1/internal/ingestion/run")
    with engine.connect() as conn:
        comp_id, card_id, norm_id = conn.execute(text(
            "SELECT sc.id, sc.card_id, sc.normalized_sale_id FROM sale_comp sc JOIN listing_card_match m "
            "ON m.normalized_sale_id = sc.normalized_sale_id WHERE m.match_method = 'rule_based_v2' LIMIT 1")).one()
    assert client.delete(f"/api/v1/cards/{card_id}/comps/{comp_id}").json() == {"deleted": True}
    client.post("/api/v1/internal/ingestion/run")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM sale_comp WHERE normalized_sale_id = :n"), {"n": norm_id}).scalar() == 0


def test_grade_tabs_split_by_company_and_always_offer_common_grades(client):
    from datetime import date, timedelta

    card = client.post("/api/v1/catalog/cards", json={"sport": "Football", "year": 2024, "brand": "Panini",
                                                      "set_name": "Prizm", "player": "Grade Tabs", "card_number": "3"}).json()["card_id"]
    d = (date.today() - timedelta(days=1)).isoformat()
    client.post(f"/api/v1/market/sales/{card}", json={"price": 300, "date": d, "grade": "PSA 10"})
    client.post(f"/api/v1/market/sales/{card}", json={"price": 250, "date": d, "grade": "PSA 10"})
    client.post(f"/api/v1/market/sales/{card}", json={"price": 900, "date": d, "grade": "BGS 10"})
    det = client.get(f"/api/v1/cards/{card}").json()
    tabs = {g["key"]: (g["label"], g["comp_count"]) for g in det["grades"]}
    assert [g["key"] for g in det["grades"]][:3] == ["raw", "psa10", "psa9"]
    assert tabs["raw"] == ("Raw", 0) and tabs["psa9"] == ("PSA 9", 0)
    assert tabs["psa10"] == ("PSA 10", 2) and tabs["bgs10"] == ("BGS 10", 1)
    assert det["valuation"]["grade"] == "PSA 10"  # most-traded by default
    # each tab only counts its own company
    ms = lambda g: client.get(f"/api/v1/cards/{card}/market-summary", params={"grade": g}).json()
    assert ms("psa10")["count"] == 2 and ms("psa10")["median"] == 275.0
    assert ms("bgs10")["count"] == 1 and ms("bgs10")["median"] == 900.0
    assert client.get(f"/api/v1/valuations/cards/{card}", params={"grade": "bgs10"}).json()["estimated_price"] == 900.0


def test_f1_is_one_sport_whatever_it_is_called(client):
    from app.api.v1.catalog import normalize_sport

    assert normalize_sport("Formula 1 Racing") == "F1" and normalize_sport("formula one") == "F1" and normalize_sport("f1") == "F1"
    assert normalize_sport("basketball") == "Basketball"
    base = {"year": 2024, "brand": "Topps", "set_name": "Chrome Formula 1", "player": "Max Verstappen", "card_number": "1"}
    a = client.post("/api/v1/catalog/cards", json={**base, "sport": "F1"}).json()["card_id"]
    b = client.post("/api/v1/catalog/cards", json={**base, "sport": "Formula 1"}).json()["card_id"]
    assert a == b  # same card, same sport
    item = client.post("/api/v1/collection/items", json={"card_id": a, "purchase_price": 50, "purchase_date": "2026-10-01"}).json()
    assert item["sport"] == "F1"


def test_edit_card_sport(client):
    card = client.post("/api/v1/catalog/cards", json={"sport": "Football", "year": 2025, "brand": "Topps", "set_name": "Chrome F1",
                                                      "player": "Kimi Antonelli", "card_number": "12"}).json()["card_id"]
    r = client.patch(f"/api/v1/catalog/cards/{card}", json={"sport": "Formula 1"})
    assert r.status_code == 200
    assert client.get(f"/api/v1/cards/{card}").json()["metadata"]["sport"] == "F1"
    # other fields untouched
    assert client.get(f"/api/v1/cards/{card}").json()["metadata"]["player"] == "Kimi Antonelli"
