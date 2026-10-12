"""CompsAPI sold-history sync, against a fake CompsAPI server (no network)."""

import httpx
import pytest

from app.core.config import settings
from app.services import compsapi

# Shaped like https://compsapi.com/docs (/v1/sold item fields).
SOLD = {
    "ok": True,
    "count": 5,
    "next_page": None,
    "items": [
        {"item_id": "111", "title": "2024 Panini Prizm Drake Maye #329 Lazer Prizm Rookie RC Patriots",
         "last_sold": "2026-10-05T22:46:00Z", "price": 30.0, "shipping_cost": 4.5, "format": "AUCTION",
         "url": "https://www.ebay.com/itm/111"},
        {"item_id": "222", "title": "Drake Maye 2024 Prizm Lazer #329 RC", "last_sold": "2026-10-01T10:00:00Z",
         "price": 28.0, "shipping_cost": None, "best_offer": True, "format": "FIXED_PRICE",
         "url": "https://www.ebay.com/itm/222"},
        # different parallel / product / graded / lot -> must be skipped
        {"item_id": "333", "title": "2024 Prizm Drake Maye #329 Silver Prizm RC", "last_sold": "2026-10-03T10:00:00Z",
         "price": 20.0, "url": "https://www.ebay.com/itm/333"},
        {"item_id": "444", "title": "2024 Prizm Drake Maye #329 Lazer Prizm PSA 10", "last_sold": "2026-10-02T10:00:00Z",
         "price": 140.0, "url": "https://www.ebay.com/itm/444"},
        {"item_id": "555", "title": "(5) 2024 Prizm Drake Maye #329 Lazer lot", "last_sold": "2026-10-02T10:00:00Z",
         "price": 90.0, "url": "https://www.ebay.com/itm/555"},
    ],
}


@pytest.fixture()
def fake_api(monkeypatch):
    calls: list[httpx.Request] = []
    state = {"mode": "ok"}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.headers["authorization"] == "Bearer sk_test_123"
        assert request.headers.get("user-agent")
        if request.url.path == "/v1/usage":
            return httpx.Response(200, json={"plan": "free", "monthly_used": len(calls), "monthly_quota": 100, "rpm_limit": 10})
        if state["mode"] == "quota":
            return httpx.Response(429, json={"ok": False, "error": "monthly quota reached"})
        return httpx.Response(200, json=SOLD)

    monkeypatch.setattr(settings, "compsapi_key", "sk_test_123")
    monkeypatch.setattr(
        compsapi,
        "_client",
        lambda: httpx.Client(
            base_url="https://api.compsapi.test",
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "Bearer sk_test_123", "User-Agent": compsapi.USER_AGENT},
        ),
    )
    return calls, state


def _lazer_holding(client):
    card = client.post(
        "/api/v1/catalog/cards",
        json={"sport": "Football", "year": 2024, "brand": "Panini", "set_name": "Prizm", "player": "Drake Maye",
              "card_number": "329", "parallel": "Lazer Prizm"},
    ).json()["card_id"]
    item = client.post(
        "/api/v1/collection/items",
        json={"card_id": card, "purchase_price": 61, "purchase_date": "2026-10-12", "is_graded": False},
    ).json()
    return card, item["id"]


def test_sync_saves_only_exact_sales_and_fills_the_row(client, fake_api):
    calls, _ = fake_api
    card, item_id = _lazer_holding(client)

    r = client.post(f"/api/v1/market/sync/{card}", params={"grade": "raw"}).json()
    assert r["status"] == "synced" and r["source"] == "compsapi"
    assert r["found"] == 5 and r["added"] == 2
    assert {tuple(s["why"]) for s in r["skipped"]} >= {("parallel",), ("grade",), ("not a single card",)}

    sent = calls[-1].url.params
    assert sent["graded"] == "false" and sent["site"] == "US" and sent["best_offer"] == "1"
    assert "329" in sent["q"] and "Lazer" in sent["q"] and "Raw" not in sent["q"]

    row = next(h for h in client.get("/api/v1/collection/items").json() if h["id"] == item_id)
    assert row["last_sale_price"] == 34.5 and row["last_sale_date"] == "2026-10-05"  # price + shipping
    assert [s["price"] for s in row["recent_sales"]] == [34.5, 28.0]
    assert row["sales_fetched_at"] is not None
    assert row["estimated_unit_price"] is not None


def test_sync_is_rate_guarded_and_idempotent(client, fake_api):
    calls, _ = fake_api
    card, _ = _lazer_holding(client)
    client.post(f"/api/v1/market/sync/{card}", params={"grade": "raw"})
    n = len(calls)
    again = client.post(f"/api/v1/market/sync/{card}", params={"grade": "raw"}).json()
    assert again["status"] == "recent" and len(calls) == n  # no request spent
    forced = client.post(f"/api/v1/market/sync/{card}", params={"grade": "raw", "force": True}).json()
    assert forced["status"] == "synced" and forced["added"] == 0 and len(calls) == n + 1  # no duplicates


def test_quota_reached_is_reported_not_crashed(client, fake_api):
    _, state = fake_api
    state["mode"] = "quota"
    card, _ = _lazer_holding(client)
    r = client.post(f"/api/v1/market/sync/{card}", params={"grade": "raw"})
    assert r.status_code == 200 and r.json()["status"] == "quota"
    status = client.get("/api/v1/market/compsapi/status").json()
    assert status["configured"] and status["monthly_quota"] == 100 and "key" not in str(status).lower()


def test_grade_params():
    assert compsapi.grade_params("Raw") == {"graded": "false"}
    assert compsapi.grade_params("PSA 10") == {"graded": "true", "grader": "PSA", "grade": "10"}
    assert compsapi.grade_params(None) == {}


def test_insert_auto_with_hyphenated_number_matches():
    from app.services.ebay import match_listing

    t = {"player": "Dylan Harper", "year": 2025, "product": "Topps Chrome", "card_number": "TAIR-DH", "parallel": None, "grade": "Raw"}
    for title in (
        "2025-26 Topps Chrome Dylan Harper Rookie Auto #TAIR-DH Spurs RC",
        "2025 Topps Chrome Basketball Dylan Harper TAIR DH Rookie Autograph",
        "Dylan Harper 2025-26 Topps Chrome RC Auto TAIRDH San Antonio",
    ):
        assert match_listing(title, t, strict_base=True) == (True, []), title
    assert match_listing("2025-26 Topps Chrome Dylan Harper Auto TAIR-DH Gold Refractor /50", t, True)[1] == ["parallel"]
    assert match_listing("2025-26 Topps Chrome Dylan Harper Auto TAIR-DH PSA 10", t, True)[1] == ["grade"]
    assert match_listing("2025-26 Topps Chrome Dylan Harper #TAIR-DHX Auto", t, True)[1] == ["card #"]
    # numeric base cards keep the strict rules
    b = {"player": "Drake Maye", "year": 2024, "product": "Prizm", "card_number": "329", "parallel": None, "grade": "Raw"}
    assert match_listing("2024 Prizm Drake Maye #3299 RC", b, True)[1] == ["card #"]
    assert match_listing("2024 Prizm Drake Maye #329 Auto", b, True)[1] == ["parallel"]
