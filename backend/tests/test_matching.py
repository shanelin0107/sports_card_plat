"""Collection-sync title matching against titles sellers actually write.

Each row: (title, card, strict_base, should_match). Guards the rules that keep wrong sales
out of a holding's estimate: namesakes, other card codes, numbered parallels of an
unnumbered card, lots/breaks, and the spellings that must still match (Jr., accents,
'25-26', 'Case Hit', middle names, nicknames)."""

import pytest

from app.services.ebay import match_listing

T = lambda pl, yr, prod, num, par=None, run=None, grade=None: dict(player=pl, year=yr, product=prod, card_number=num, parallel=par, print_run=run, grade=grade)
WEMBY = T("Victor Wembanyama", 2023, "Panini Prizm", "136", "Silver")
OHTANI = T("Shohei Ohtani", 2023, "Topps Chrome", "17", None)
LILL = T("Damian Lillard", 2024, "Panini Prizm Black", "91", "Orange Wave")
BEAR = T("Oliver Bearman", 2025, "Topps Chrome F1", "CAC-BEA", "Orange RayWave Refractor", 25)
KIMI = T("Andrea Kimi Antonelli", 2025, "Topps Chrome F1", "1", None)
FLAGG_FAN = T("Cooper Flagg", 2025, "Topps Chrome", "FAN-21", "Fanatical")
FLAGG_BASE = T("Cooper Flagg", 2025, "Topps Chrome", "251", None)
HARPER = T("Dylan Harper", 2025, "Topps Chrome", "TAIR-DH", None, grade="Raw")
MAYE = T("Drake Maye", 2024, "Prizm", "329", "Lazer")
CLAYTON = T("Walter Clayton Jr.", 2025, "Topps Chrome", "210", None)
JOKIC = T("Nikola Jokić", 2025, "Topps Chrome", "50", None)
RAY = T("Ray Allen", 2025, "Topps Chrome", "FAN-18", "Fanatical")
DHARPER1 = T("Dylan Harper", 2025, "Topps Chrome", "1", None)
CASES = [
 ("2023 Panini Prizm Victor Wembanyama #136 Silver Prizm RC", WEMBY, False, True),
 ("2023-24 Prizm Wembanyama Silver #136 Rookie", WEMBY, False, True),
 ("2023 Panini Prizm Victor Wembanyama #136 Silver RC PSA 10", WEMBY, False, True),
 ("2023-24 Panini Prizm Wembanyama Spurs Silver #136 RC", WEMBY, False, True),
 ("2023 Topps Chrome Shohei Ohtani #17 Angels", OHTANI, True, True),
 ("2023 Topps Chrome Ohtani #17 Refractor", OHTANI, True, False),
 ("2023 Topps Chrome Shohei Ohtani #17 PSA 10 Gem Mint", OHTANI, True, True),
 ("2024-25 Panini Prizm Black Damian Lillard #91 Orange Wave /60 Bucks", LILL, False, True),
 ("2024-25 Prizm Black Lillard #91 Orange Wave", LILL, False, True),
 ("2025 Topps Chrome Formula 1 Oliver Bearman Orange Ray Wave Auto 3/25 Haas", BEAR, True, True),
 ("2025 Topps Chrome F1 Oliver Bearman Orange RayWave /99", BEAR, True, False),
 ("2025 Topps Chrome F1 Bearman CAC-BEA Orange Raywave Refractor Auto /25 RC", BEAR, True, True),
 ("2025 Topps Chrome F1 Kimi Antonelli #1 RC Mercedes", KIMI, True, True),
 ("2025 Topps Chrome Formula 1 Andrea Kimi Antonelli #1 Rookie", KIMI, True, True),
 ("2025 Topps Chrome F1 Antonelli #1 RC", KIMI, True, True),
 ("2025-26 Topps Chrome Cooper Flagg Fanatical SSP Case Hit RC FAN-21", FLAGG_FAN, True, True),
 ("2025-26 Topps Chrome Cooper Flagg Fanatical RC", FLAGG_FAN, True, True),
 ("2025-26 Topps Chrome Cooper Flagg Fanatical Gold Refractor /50 FAN-21", FLAGG_FAN, True, False),
 ("2025-26 Topps Chrome Cooper Flagg Fanatical Superfractor 1/1", FLAGG_FAN, True, False),
 ("25-26 Topps Chrome Cooper Flagg Fanatical RC", FLAGG_FAN, True, True),
 ("2025/26 Topps Chrome Cooper Flagg Fanatical RC", FLAGG_FAN, True, True),
 ("2025-26 Topps Chrome Cooper Flagg RC #251", FLAGG_BASE, True, True),
 ("25-26 Topps Chrome Cooper Flagg RC #251", FLAGG_BASE, True, True),
 ("2025-26 Topps Chrome Cooper Flagg RC #251 Gold /50", FLAGG_BASE, True, False),
 ("2025-26 Topps Chrome Cooper Flagg RC #251 Mega Box Exclusive", FLAGG_BASE, True, False),
 ("2025-26 Topps Chrome Hobby Box Sealed Cooper Flagg", FLAGG_BASE, True, False),
 ("2025-26 Topps Chrome Cooper Flagg #251 Lot of 3", FLAGG_BASE, True, False),
 ("2025 Topps Chrome Dylan Harper TAIR-DH Auto RC", HARPER, True, True),
 ("2025 Topps Chrome Bryce Harper #1 Phillies", DHARPER1, True, False),
 ("2025-26 Topps Chrome Dylan Harper #1 RC Spurs", DHARPER1, True, True),
 ("2024 Panini Prizm Drake Maye #329 Lazer Prizm Rookie RC Patriots", MAYE, True, True),
 ("2024 Prizm Drake Maye #329 Silver Prizm RC", MAYE, True, False),
 ("2025-26 Topps Chrome Walter Clayton Jr. RC #210", CLAYTON, True, True),
 ("2025-26 Topps Chrome Walter Clayton Jr RC #210 Jazz", CLAYTON, True, True),
 ("2025-26 Topps Chrome Nikola Jokic #50 Nuggets", JOKIC, True, True),
 ("2025-26 Topps Chrome Allen Iverson Fanatical FAN-20", RAY, True, False),
 ("2025-26 Topps Chrome Ray Allen Fanatical FAN-18", RAY, True, True),
 ("2025-26 Topps Chrome Ray Allen Fanatical SSP", RAY, True, True),
    ("2023 Prizm Wemby Wembanyama Silver #136", WEMBY, False, True),
]


@pytest.mark.parametrize("title,target,strict,expected", CASES)
def test_title_matching(title, target, strict, expected):
    ok, miss = match_listing(title, target, strict_base=strict)
    assert ok is expected, (title, miss)


def test_case_hit_is_a_single_card_but_a_case_is_not():
    from app.services.ebay import _norm, is_junk

    assert not is_junk(f" {_norm('2025-26 Topps Chrome Flagg Fanatical SSP Case Hit')} ")
    assert not is_junk(f" {_norm('Flagg Fanatical pack fresh')} ")
    assert is_junk(f" {_norm('2025-26 Topps Chrome Hobby Case 12 boxes')} ")
    assert is_junk(f" {_norm('2025-26 Topps Chrome Fanatical lot of 3')} ")


def test_sale_audit_lists_auto_saved_sales_that_no_longer_match(client):
    from app.db.session import SessionLocal
    from app.services.comps import create_confirmed_comp

    body = {
        "card": {"sport": "Basketball", "year": 2025, "brand": "Topps", "set_name": "Topps Chrome", "player": "Cooper Flagg",
                 "card_number": "FAN-21", "parallel": "Fanatical", "print_run": None, "rookie": True, "autograph": False},
        "purchase_price": 250, "purchase_date": "2026-10-10", "grader": None, "grade_value": None,
    }
    h = client.post("/api/v1/collection/items/quick-add", json=body).json()
    with SessionLocal() as db:
        for i, (title, method) in enumerate([
            ("2025-26 Topps Chrome Cooper Flagg Fanatical SSP Case Hit RC FAN-21", "compsapi_auto"),  # right card
            ("2025-26 Topps Chrome Cooper Flagg Fanatical Gold Refractor /50 FAN-21", "compsapi_auto"),  # wrong: Gold /50
            ("2025-26 Topps Chrome Cooper Flagg Fanatical Gold Refractor /50 FAN-21 #2", "manual_entry"),  # owner added it: leave alone
        ]):
            create_confirmed_comp(db, card_id=h["card_id"], listing_id=f"ebay-90{i}", title=title, url=f"https://www.ebay.com/itm/90{i}",
                                  price=300 + i, date="2026-10-0%d" % (i + 1), grade="Raw", source="eBay", match_method=method,
                                  payload={}, card_parallel_id=h["card_parallel_id"])
        db.commit()
    r = client.get("/api/v1/market/sale-audit").json()
    mine = [s for s in r["suspects"] if s["card_id"] == h["card_id"]]
    assert [s["title"] for s in mine] == ["2025-26 Topps Chrome Cooper Flagg Fanatical Gold Refractor /50 FAN-21"]
    assert mine[0]["why"] == ["parallel"]
    # nothing was removed by looking
    assert client.get(f"/api/v1/cards/{h['card_id']}/market-summary").status_code == 200


def test_dockerfile_playwright_matches_requirements():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    docker = re.search(r"PLAYWRIGHT_VERSION=([\d.]+)", (root / "Dockerfile").read_text()).group(1)
    req = re.search(r"^playwright==([\d.]+)", (root / "requirements.txt").read_text(), re.M).group(1)
    assert docker == req
