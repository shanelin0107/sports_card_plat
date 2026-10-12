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
