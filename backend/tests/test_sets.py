"""Insert / SSP set guide: seed, odds, Playwright import parsing, click-to-price cache."""

import http.server
import threading
from functools import partial

import pytest

from app.services import set_guide, set_import

CHECKLIST_PAGE = """
<html><head><meta charset="utf-8"><title>2025-26 Topps Chrome Basketball Checklist</title></head><body>
<h2>Insert Sets</h2>
<h3>2025-26 Topps Chrome – Fanatical Set</h3>
<p>25 cards.</p>
<p><b>Parallels:</b> Gold #/50; Orange #/25; Red #/5; SuperFractor 1/1</p>
<p>FAN-1 Victor Wembanyama – San Antonio Spurs<br>FAN-2 Giannis Antetokounmpo – Milwaukee Bucks</p>
<p>Image</p>
<p>FAN-21 Cooper Flagg – Dallas Mavericks RC</p>
<h3>2025-26 Topps Chrome – Ultra Violet All-Stars Set</h3>
<p>15 cards.</p>
<p><b>Parallels:</b> SuperFractor 1/1</p>
<p>UV-1 LeBron James – Los Angeles Lakers<br>UV-11 Cooper Flagg – Dallas Mavericks</p>
<h3>2025-26 Topps Chrome – Activators Set</h3>
<p>AC-1 Ja Morant – Memphis Grizzlies</p>
</body></html>
"""

ODDS_PAGE = """
<html><head><meta charset="utf-8"><title>Case hits and SSP inserts</title></head><body>
<h2>Fanatical</h2><p>Fanatical returns with hanger odds of 1:66 hanger boxes, 1:290 blaster packs, 1:144 mega packs
and 1:71 Fanatics mega packs. The Gold parallel falls 1:5,000 mega packs.</p>
<h2>Ultra Violet</h2><p>Ultra Violet lands 1:1,452 hobby packs, 1:289 jumbo packs, 1:81,494 blaster packs and 1:42,917 mega packs.</p>
</body></html>
"""


def test_seed_loads_basketball_ssps(client):
    sets = client.get("/api/v1/sets").json()
    tc = next(s for s in sets if s["name"] == "2025-26 Topps Chrome Basketball")
    assert tc["inserts"] == 12 and tc["cards"] == 215
    d = client.get(f"/api/v1/sets/{tc['id']}").json()
    assert [b["name"] for b in d["box_types"]] == ["Hobby", "Jumbo", "Value", "Mega"]
    fan = next(i for i in d["inserts"] if i["name"] == "Fanatical")
    base = next(p for p in fan["parallels"] if p["name"] == "Base")
    assert base["odds"] == {"Value": 290, "Mega": 144}  # retail only: not in Hobby/Jumbo
    assert [p["name"] for p in fan["parallels"]] == ["Base", "Gold", "Orange", "Red", "SuperFractor"]
    flagg = next(c for c in fan["cards"] if c["number"] == "FAN-21")
    assert flagg["player"] == "Cooper Flagg" and flagg["rookie"] and flagg["owned"] == 0


def test_title_matching_keeps_parallels_apart():
    kw = dict(insert="Fanatical", player="Victor Wembanyama", other_parallels=["Base", "Gold", "Orange", "Red", "SuperFractor"])
    t_base = "2025-26 Topps Chrome Victor Wembanyama Fanatical SSP Case Hit FAN-1"
    t_gold = "2025-26 Topps Chrome Wembanyama Fanatical Gold Refractor /50 #FAN-1"
    t_1of1 = "2025 Topps Chrome Wembanyama Fanatical Superfractor 1/1"
    assert set_guide.title_matches(t_base, parallel="Base", print_run=None, **kw)
    assert not set_guide.title_matches(t_gold, parallel="Base", print_run=None, **kw)
    assert set_guide.title_matches(t_gold, parallel="Gold", print_run=50, **kw)
    assert not set_guide.title_matches(t_gold.replace("/50", "/25"), parallel="Gold", print_run=50, **kw)
    assert set_guide.title_matches(t_1of1, parallel="SuperFractor", print_run=1, **kw)
    assert not set_guide.title_matches(t_1of1, parallel="Base", print_run=None, **kw)
    assert not set_guide.title_matches("2025 Topps Chrome Fanatical lot of 5 Wembanyama", parallel="Base", print_run=None, **kw)
    assert not set_guide.title_matches("2025 Topps Chrome Wembanyama Paradox", parallel="Base", print_run=None, **kw)
    # names with accents / suffixes and two-word insert names
    assert set_guide.title_matches(
        "2025-26 Topps Chrome Nikola Jokic Ultraviolet All Stars UV-10",
        insert="Ultra Violet All-Stars", player="Nikola Jokić", parallel="Base", print_run=None, other_parallels=["Base", "SuperFractor"],
    )
    assert set_guide.title_matches(
        "Walter Clayton Jr 2025-26 Topps Chrome Lets Go RC",
        insert="Let's Go", player="Walter Clayton Jr.", parallel="Base", print_run=None, other_parallels=["Base"],
    )
    assert set_guide.price_query(2025, "Topps Chrome", "Ultra Violet All-Stars", "Nikola Jokić", "Base") == "2025 Topps Chrome Ultra Violet Nikola Jokic"
    assert set_guide.price_query(2025, "Topps Chrome", "Fanatical", "Ace Bailey", "Gold") == "2025 Topps Chrome Fanatical Ace Bailey Gold"


def _fake_sold(items):
    def fetch(query, target, grade, days=None, size=120):
        fetch.calls.append(query)
        return {"query": query, "count": len(items), "days": 365, "items": items}

    fetch.calls = []
    return fetch


def _row(i, title, total, date, image=None):
    return {"item_id": str(i), "title": title, "price": total, "shipping": 0.0, "total": total, "date": date, "sold_at": date,
            "url": f"https://www.ebay.com/itm/{i}", "image": image, "best_offer": False, "format": "auction", "grade": "Raw",
            "exact_match": False, "mismatches": []}


def test_price_check_filters_caches_and_sets_photo(client, monkeypatch):
    from app.core.config import settings
    from app.services import compsapi

    monkeypatch.setattr(settings, "compsapi_key", "sk_test")
    fake = _fake_sold([
        _row(1, "2025-26 Topps Chrome Cooper Flagg Fanatical SSP RC FAN-21", 300.0, "2026-10-10", "https://i.ebayimg.com/a.jpg"),
        _row(2, "2025-26 Topps Chrome Cooper Flagg Fanatical RC", 260.0, "2026-10-01"),
        _row(3, "2025-26 Topps Chrome Cooper Flagg Fanatical Gold /50", 2000.0, "2026-10-05"),
        _row(4, "2025-26 Topps Chrome Cooper Flagg Base RC", 40.0, "2026-10-06"),
    ])
    monkeypatch.setattr(compsapi, "fetch_sold", fake)
    pid = client.get("/api/v1/sets").json()[0]["id"]
    d = client.get(f"/api/v1/sets/{pid}").json()
    fan = next(i for i in d["inserts"] if i["name"] == "Fanatical")
    card = next(c for c in fan["cards"] if c["number"] == "FAN-21")
    base = next(p for p in fan["parallels"] if p["name"] == "Base")

    r = client.post(f"/api/v1/sets/cards/{card['id']}/price", params={"parallel_id": base["id"]}).json()
    assert fake.calls == ["2025 Topps Chrome Fanatical Cooper Flagg"]
    assert r["count"] == 2 and r["stats"]["median"] == 280.0 and r["last_sale"]["total"] == 300.0 and not r["cached"]

    again = client.post(f"/api/v1/sets/cards/{card['id']}/price", params={"parallel_id": base["id"]}).json()
    assert again["cached"] and len(fake.calls) == 1  # 7-day cache: no second search

    d = client.get(f"/api/v1/sets/{pid}").json()
    card = next(c for i in d["inserts"] if i["name"] == "Fanatical" for c in i["cards"] if c["number"] == "FAN-21")
    assert card["image_url"] == "https://i.ebayimg.com/a.jpg"
    assert card["prices"][str(base["id"])]["median"] == 280.0

    client.post(f"/api/v1/sets/cards/{card['id']}/price", params={"parallel_id": base["id"], "force": True})
    assert len(fake.calls) == 2  # ↻ searches again


def test_price_check_without_key_is_clear(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "compsapi_key", "")
    pid = client.get("/api/v1/sets").json()[0]["id"]
    fan = next(i for i in client.get(f"/api/v1/sets/{pid}").json()["inserts"] if i["name"] == "Fanatical")
    r = client.post(f"/api/v1/sets/cards/{fan['cards'][0]['id']}/price", params={"parallel_id": fan["parallels"][0]["id"]})
    assert r.status_code == 503 and "compsapi_off" in r.json()["detail"]


def test_box_size_is_editable(client):
    pid = client.get("/api/v1/sets").json()[0]["id"]
    mega = next(b for b in client.get(f"/api/v1/sets/{pid}").json()["box_types"] if b["name"] == "Mega")
    assert client.patch(f"/api/v1/sets/{pid}/box-types/{mega['id']}", json={"packs_per_box": 6}).status_code == 200
    mega = next(b for b in client.get(f"/api/v1/sets/{pid}").json()["box_types"] if b["name"] == "Mega")
    assert mega["packs_per_box"] == 6


def _html_to_text(html):
    import re

    t = re.sub(r"(?i)<br\s*/?>|</(p|h[1-6])>", "\n", html)
    return re.sub(r"<[^>]+>", "", t)


def test_parse_checklist_groups_rows_under_headings():
    groups = set_import.parse_checklist(_html_to_text(CHECKLIST_PAGE))
    by = {g["name"]: g for g in groups}
    assert set(by) == {"Fanatical", "Ultra Violet All-Stars", "Activators"}
    fan = by["Fanatical"]
    assert [c["number"] for c in fan["cards"]] == ["FAN-1", "FAN-2", "FAN-21"]  # rows split by a photo stay together
    assert fan["cards"][2] == {"number": "FAN-21", "player": "Cooper Flagg", "team": "Dallas Mavericks", "rookie": True}
    assert fan["parallels"] == [
        {"name": "Gold", "print_run": 50}, {"name": "Orange", "print_run": 25}, {"name": "Red", "print_run": 5}, {"name": "SuperFractor", "print_run": 1}
    ]


def test_parse_odds_by_box_and_parallel():
    names = {"Fanatical": ["Base", "Gold", "SuperFractor"], "Ultra Violet All-Stars": ["Base"]}
    odds = set_import.parse_odds(_html_to_text(ODDS_PAGE), names, ["Hobby", "Jumbo", "Value", "Mega"])
    assert odds["Fanatical"]["Base"] == {"Value": 290, "Mega": 144}  # hanger / Fanatics mega aren't tracked boxes
    assert odds["Fanatical"]["Gold"] == {"Mega": 5000}
    assert odds["Ultra Violet All-Stars"]["Base"] == {"Hobby": 1452, "Jumbo": 289, "Value": 81494, "Mega": 42917}


def test_blocked_pages_are_reported_not_bypassed():
    with pytest.raises(set_import.Blocked):
        set_import._check_blocked(403, "Just a moment...", "Checking your browser")


@pytest.fixture()
def local_site(tmp_path):
    (tmp_path / "checklist.html").write_text(CHECKLIST_PAGE)
    (tmp_path / "odds.html").write_text(ODDS_PAGE)
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_import_with_playwright_updates_the_set(client, local_site):
    pytest.importorskip("playwright")
    pid = client.get("/api/v1/sets").json()[0]["id"]
    r = client.post(
        "/api/v1/sets/import",
        json={"name": "2025-26 Topps Chrome Basketball", "checklist_url": f"{local_site}/checklist.html", "odds_url": f"{local_site}/odds.html"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["product_id"] == pid and not body["warnings"]
    assert {u["name"] for u in body["updated"]} == {"Fanatical", "Ultra Violet All-Stars"}
    assert "Activators" in body["unmatched"]  # not an SSP in this guide
    fan = next(i for i in client.get(f"/api/v1/sets/{pid}").json()["inserts"] if i["name"] == "Fanatical")
    assert [c["number"] for c in fan["cards"]] == ["FAN-1", "FAN-2", "FAN-21"]  # replaced by what the page lists
    gold = next(p for p in fan["parallels"] if p["name"] == "Gold")
    assert gold["odds"] == {"Mega": 5000} and gold["print_run"] == 50


def test_import_new_product_keeps_inserts_with_odds(client, local_site):
    pytest.importorskip("playwright")
    r = client.post(
        "/api/v1/sets/import",
        json={"name": "2024-25 Topps Chrome Basketball", "checklist_url": f"{local_site}/checklist.html", "odds_url": f"{local_site}/odds.html"},
    ).json()
    d = client.get(f"/api/v1/sets/{r['product_id']}").json()
    assert d["year"] == 2024 and d["sport"] == "Basketball" and d["set_name"] == "Topps Chrome"
    assert sorted(i["name"] for i in d["inserts"]) == ["Fanatical", "Ultra Violet All-Stars"]
