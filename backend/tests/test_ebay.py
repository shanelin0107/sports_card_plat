"""eBay integration against a mocked eBay API (no network, no real keys)."""

import httpx
import pytest

from app.services import ebay

TARGET = {"player": "Damian Lillard", "year": 2024, "product": "Panini Prizm Black", "card_number": "91", "parallel": "Orange Wave", "grade": None}


def test_match_listing_distinguishes_lookalikes():
    ok, _ = ebay.match_listing("2024-25 Panini Prizm Black Damian Lillard #91 Orange Wave /60 Bucks", TARGET)
    assert ok
    ok, miss = ebay.match_listing("Damian Lillard 2024-25 Panini Prizm Orange Wave #35/60 Milwaukee Bucks #90", TARGET)
    assert not ok and "card #" in miss and "set" in miss
    ok, miss = ebay.match_listing("2024-25 Prizm Black Damian Lillard #91 Snakeskin", TARGET)
    assert not ok and miss == ["parallel"]
    ok, miss = ebay.match_listing("2024-25 Prizm Black Lillard #91 Orange Wave /60 PSA 10", {**TARGET, "grade": "Raw"})
    assert miss == ["grade"]


def _mock(insights: bool):
    calls = []

    def handler(req: httpx.Request):
        calls.append(req)
        if req.url.path == "/identity/v1/oauth2/token":
            assert req.headers["authorization"].startswith("Basic ")
            if "marketplace.insights" in req.content.decode() and not insights:
                return httpx.Response(400, json={"error": "invalid_scope", "error_description": "not granted"})
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        assert req.headers["authorization"] == "Bearer tok"
        assert req.headers["x-ebay-c-marketplace-id"] == "EBAY_US"
        if req.url.path.startswith("/buy/browse"):
            return httpx.Response(200, json={"total": 2, "itemSummaries": [
                {"itemId": "v1|1|0", "title": "2024-25 Panini Prizm Black Damian Lillard #91 Orange Wave /60", "price": {"value": "45.00", "currency": "USD"},
                 "itemWebUrl": "https://www.ebay.com/itm/1", "image": {"imageUrl": "https://i.ebayimg.com/1.jpg"}, "buyingOptions": ["FIXED_PRICE"],
                 "shippingOptions": [{"shippingCost": {"value": "4.99"}}]},
                {"itemId": "v1|2|0", "title": "Damian Lillard 2024-25 Panini Prizm Orange Wave #35/60 #90", "price": {"value": "25.00", "currency": "USD"},
                 "itemWebUrl": "https://www.ebay.com/itm/2", "buyingOptions": ["FIXED_PRICE", "BEST_OFFER"]},
            ]})
        if req.url.path.startswith("/buy/marketplace_insights"):
            return httpx.Response(200, json={"itemSales": [
                {"itemId": "v1|9|0", "title": "2024-25 Prizm Black Damian Lillard #91 Orange Wave 12/60", "lastSoldPrice": {"value": "52.00"},
                 "lastSoldDate": "2026-09-30T18:00:00.000Z", "totalSoldQuantity": 1, "itemWebUrl": "https://www.ebay.com/itm/9"}]})
        return httpx.Response(404)

    return calls, (lambda: httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ebay_client_id", "id")
    monkeypatch.setattr(settings, "ebay_client_secret", "secret")
    ebay._tokens.clear(); ebay._denied_scopes.clear(); ebay._cache.clear()
    yield
    ebay._tokens.clear(); ebay._denied_scopes.clear(); ebay._cache.clear()


def test_listings_without_insights_access(monkeypatch):
    calls, client = _mock(insights=False)
    monkeypatch.setattr(ebay, "_http", client)
    out = ebay.search_listings("2024 Prizm Black Lillard 91 Orange Wave", TARGET)
    assert out["insights_available"] is False and out["sold"] is None
    assert [a["exact_match"] for a in out["active"]] == [True, False]  # exact first
    assert out["active_stats"] == {"count": 1, "low": 45.0, "median": 45.0, "high": 45.0}
    assert out["active"][0]["shipping"] == 4.99 and out["active"][0]["image"].startswith("https://i.ebayimg.com")
    assert ebay.check_access() == {"configured": True, "browse": True, "insights": False, "error": None}


def test_listings_with_insights_and_save(client, monkeypatch):
    calls, http = _mock(insights=True)
    monkeypatch.setattr(ebay, "_http", http)
    card = client.post("/api/v1/catalog/cards", json={"sport": "Basketball", "year": 2024, "brand": "Panini", "set_name": "Prizm Black",
                                                      "player": "Damian Lillard", "card_number": "91", "parallel": "Orange Wave"}).json()
    out = client.get("/api/v1/market/ebay/listings", params={"card_id": card["card_id"], "grade": "raw"}).json()
    assert out["insights_available"] and out["sold"][0]["date"] == "2026-09-30" and out["sold"][0]["exact_match"]
    assert "Prizm Black" in out["query"] and "Orange Wave" in out["query"]
    s = out["sold"][0]
    r = client.post("/api/v1/market/ebay/save-sold", json={"card_id": card["card_id"], "item_id": s["item_id"], "title": s["title"],
                                                         "url": s["url"], "price": s["price"], "date": s["date"], "grade": s["grade"]})
    assert r.status_code == 200 and not r.json()["already_saved"]
    again = client.post("/api/v1/market/ebay/save-sold", json={"card_id": card["card_id"], "item_id": s["item_id"], "title": s["title"],
                                                             "url": s["url"], "price": s["price"], "date": s["date"], "grade": s["grade"]})
    assert again.json()["already_saved"]
    img = client.put(f"/api/v1/catalog/cards/{card['card_id']}/image", json={"image_url": "https://i.ebayimg.com/1.jpg"})
    assert img.json()["default_image_url"] == "https://i.ebayimg.com/1.jpg"
    assert client.get(f"/api/v1/cards/{card['card_id']}").json()["valuation"]["estimated_price"] == 52.0


def test_bad_credentials_message(monkeypatch):
    monkeypatch.setattr(ebay, "_http", lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": "invalid_client"}))))
    assert "rejected the credentials" in ebay.check_access()["error"]
