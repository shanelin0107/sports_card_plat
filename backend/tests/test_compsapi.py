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
    assert "Lazer" in sent["q"] and "Raw" not in sent["q"] and "329" not in sent["q"]  # parallel card: number left to the matcher

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
    # still says "quota" next time (not "recent": nothing was fetched), and works again once searches are back
    assert client.post(f"/api/v1/market/sync/{card}", params={"grade": "raw"}).json()["status"] == "quota"
    state["mode"] = "ok"
    assert client.post(f"/api/v1/market/sync/{card}", params={"grade": "raw"}).json()["status"] == "synced"
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


def test_busy_api_steps_down_to_shorter_window(client, fake_api, monkeypatch):
    calls, state = fake_api
    monkeypatch.setattr(compsapi.time, "sleep", lambda s: None)
    real = compsapi._client

    def flaky():
        c = real()
        orig = c.get

        def get(path, params=None):
            calls.append(httpx.Request("GET", "https://x" + path, params=params))
            if path == "/v1/sold" and int(params["days"]) > 90:
                return httpx.Response(503, json={"ok": False, "error": "temporarily unavailable, please retry"})
            return orig(path, params=params)

        c.get = get
        return c

    monkeypatch.setattr(compsapi, "_client", flaky)
    card, _ = _lazer_holding(client)
    r = client.post(f"/api/v1/market/sync/{card}", params={"grade": "raw"}).json()
    assert r["status"] == "synced" and r["added"] == 2
    days = [int(c.url.params["days"]) for c in calls if c.url.path == "/v1/sold"]
    assert days[:2] == [365, 365] and 90 in days  # retried once, then a shorter window


def test_busy_api_everywhere_gives_a_clear_message(client, fake_api, monkeypatch):
    monkeypatch.setattr(compsapi.time, "sleep", lambda s: None)
    real = compsapi._client

    def down():
        c = real()
        c.get = lambda path, params=None: httpx.Response(503, json={"ok": False, "error": "temporarily unavailable"})
        return c

    monkeypatch.setattr(compsapi, "_client", down)
    card, _ = _lazer_holding(client)
    r = client.post(f"/api/v1/market/sync/{card}", params={"grade": "raw"})
    assert r.status_code == 502 and "no search was used" in r.json()["detail"]
    # not marked as fetched, so the next open/↻ tries again
    r2 = client.post(f"/api/v1/market/sync/{card}", params={"grade": "raw"})
    assert r2.status_code == 502


def test_sync_targets_the_holdings_parallel_on_a_mixed_legacy_card(client, fake_api):
    from sqlalchemy import text

    from app.db.session import engine

    calls, _ = fake_api
    base = {"sport": "Football", "year": 2024, "brand": "Panini", "set_name": "Prizm", "player": "Drake Maye", "card_number": "329"}
    card = client.post("/api/v1/catalog/cards", json={**base, "parallel": "Lazer Prizm"}).json()
    # old data: one card carrying two parallels
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO card_parallel (card_id, parallel_name, variation_name) VALUES (:c, 'Silver Prizm', 'Base')"),
                     {"c": card["card_id"]})
    r = client.post(f"/api/v1/market/sync/{card['card_id']}",
                    params={"grade": "raw", "parallel_id": card["card_parallel_id"]}).json()
    assert r["added"] == 2 and "Lazer" in calls[-1].url.params["q"]
    with engine.connect() as conn:
        tagged = conn.execute(text("SELECT count(*) FROM sale_comp WHERE card_id = :c AND card_parallel_id = :p"),
                              {"c": card["card_id"], "p": card["card_parallel_id"]}).scalar()
    assert tagged == 2


def test_bgs_holding_syncs_as_bgs(client, fake_api):
    calls, _ = fake_api
    card, _ = _lazer_holding(client)
    client.post(f"/api/v1/market/sync/{card}", params={"grade": "bgs9.5"})
    sent = calls[-1].url.params
    assert sent["graded"] == "true" and sent["grader"] == "BGS" and sent["grade"] == "9.5"


def test_f1_titles_match_either_spelling():
    from app.services.ebay import match_listing

    t = {"player": "Max Verstappen", "year": 2024, "product": "Topps Chrome F1", "card_number": "1", "parallel": None, "grade": "Raw"}
    for title in ("2024 Topps Chrome F1 Max Verstappen #1", "2024 Topps Chrome Formula 1 Max Verstappen #1 Red Bull",
                  "Max Verstappen 2024 Topps Chrome Formula One #1"):
        assert match_listing(title, t, strict_base=True) == (True, []), title
    t2 = {**t, "product": "Topps Chrome Formula 1"}
    assert match_listing("2024 Topps Chrome F1 Max Verstappen #1", t2, strict_base=True) == (True, [])


def test_sold_search_returns_sold_items_cached(client, fake_api):
    calls, _ = fake_api
    compsapi._search_cache.clear()
    r = client.get("/api/v1/market/sold-search", params={"q": "2024 prizm drake maye 329 lazer"}).json()
    titles = [i["title"] for i in r["items"]]
    assert r["count"] == 3 and not any("lot" in t.lower() for t in titles)  # the lot is left out
    assert not any("Silver" in t for t in titles)  # "lazer" was asked for: the Silver Prizm sale isn't it
    assert r["items"][0]["date"] == "2026-10-05" and r["last_sale"]["total"] == 34.5  # newest first, price + shipping
    assert {i["grade"] for i in r["items"]} >= {"Raw", "PSA 10"}
    assert r["stats"]["count"] == 3 and r["cached"] is False
    n = len(calls)
    again = client.get("/api/v1/market/sold-search", params={"q": "2024  Prizm Drake Maye 329 Lazer"}).json()
    assert again["cached"] is True and len(calls) == n  # same search: no request spent


def test_sold_search_without_key_says_so(client):
    r = client.get("/api/v1/market/sold-search", params={"q": "anything"})
    assert r.status_code == 503 and "compsapi_off" in r.json()["detail"]


BEARMAN = {"player": "Oliver Bearman", "year": 2025, "product": "Topps Chrome F1", "card_number": "CAC-BEA",
           "parallel": "Orange RayWave Refractor", "print_run": 25, "grade": "Raw"}


def test_bearman_orange_raywave_titles_sellers_actually_write():
    from app.services.ebay import match_listing

    for title in (
        "2025 Topps Chrome F1 Oliver Bearman Orange RayWave Refractor Auto /25 RC #CAC-BEA",
        "2025 Topps Chrome Formula 1 Oliver Bearman Orange Raywave Auto 12/25 Rookie Haas",  # no "Refractor", no number
        "Oliver Bearman 2025 Topps Chrome F1 Orange Ray Wave Refractor Autograph /25 RC",  # "Ray Wave"
        "2025 Topps Chrome F1 OLIVER BEARMAN Chrome Autographs Orange RayWave /25 CAC-BEA",
    ):
        assert match_listing(title, BEARMAN, strict_base=True) == (True, []), title
    # still rejected: another parallel, another print run, another card number, a slab
    assert "parallel" in match_listing("2025 Topps Chrome F1 Oliver Bearman Orange Refractor Auto /25", BEARMAN, True)[1]
    assert "print run" in match_listing("2025 Topps Chrome F1 Oliver Bearman Gold RayWave Orange Auto /50", BEARMAN, True)[1]
    assert "card #" in match_listing("2025 Topps Chrome F1 Oliver Bearman #86 Orange RayWave /25", BEARMAN, True)[1]
    assert "grade" in match_listing("2025 Topps Chrome F1 Oliver Bearman Orange RayWave Auto /25 PSA 10", BEARMAN, True)[1]


def test_base_card_still_needs_its_number():
    from app.services.ebay import match_listing

    base = {"player": "Drake Maye", "year": 2024, "product": "Prizm", "card_number": "329", "parallel": None, "grade": "Raw"}
    assert match_listing("2024 Panini Prizm Drake Maye Rookie RC", base, True)[1] == ["card #"]  # base card + no number


def test_search_query_keeps_only_reliable_words():
    from app.services.ebay import search_query

    assert search_query(2025, "Topps Chrome F1", "Oliver Bearman", "CAC-BEA", "Orange RayWave Refractor") == "2025 Topps Chrome Oliver Bearman Orange"
    assert search_query(2024, "Panini Prizm", "Drake Maye", "329", None) == "2024 Panini Prizm Drake Maye 329"


def test_free_text_sold_search_is_simplified_and_filtered(client, fake_api, monkeypatch):
    calls, _ = fake_api
    compsapi._search_cache.clear()
    real = compsapi._client
    rows = {"ok": True, "items": [
        {"item_id": "1", "title": "2025 Topps Chrome Formula 1 Oliver Bearman Orange Ray Wave Auto 3/25 Haas", "last_sold": "2026-10-16T12:00:00Z", "price": 610.0, "url": "https://www.ebay.com/itm/1"},
        {"item_id": "2", "title": "2025 Topps Chrome F1 Oliver Bearman Orange Refractor Auto /25", "last_sold": "2026-10-15T12:00:00Z", "price": 300.0, "url": "https://www.ebay.com/itm/2"},
        {"item_id": "3", "title": "2025 Topps Chrome F1 Oliver Bearman Orange RayWave /99", "last_sold": "2026-10-14T12:00:00Z", "price": 40.0, "url": "https://www.ebay.com/itm/3"},
    ]}

    def stub():
        c = real()
        c.get = lambda path, params=None: (calls.append(httpx.Request("GET", "https://x" + path, params=params)), httpx.Response(200, json=rows))[1]
        return c

    monkeypatch.setattr(compsapi, "_client", stub)
    r = client.get("/api/v1/market/sold-search", params={"q": "2025 Topps Chrome F1 Oliver Bearman Auto Orange RayWave Refractor RC #/25"}).json()
    assert calls[-1].url.params["q"] == "2025 topps chrome oliver bearman orange"
    assert r["must_include"] == ["raywave", "/25"]
    assert [i["item_id"] for i in r["items"]] == ["1"]  # not the plain Orange Refractor, not the /99
