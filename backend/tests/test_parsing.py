from datetime import UTC, datetime

from app.services.ingestion.parsing import contains_phrase, parse_money, parse_sold_at, parse_title


def test_card_number_is_not_prefix_matched():
    # Old parser tagged "#136" as "#1" because it checked `"#1" in title`.
    assert parse_title("2023 Panini Prizm Victor Wembanyama #136 Silver PSA 10").card_number == "136"
    assert parse_title("2023 Topps Chrome Shohei Ohtani #1 PSA 10").card_number == "1"


def test_grades():
    assert parse_title("Wembanyama Prizm Silver PSA 9").grade_value == "9"
    assert parse_title("Ohtani BGS 9.5").grader == "BGS"
    assert parse_title("Ohtani BGS 9.5").grade_value == "9.5"
    p = parse_title("2023 Topps Chrome Ohtani Raw")
    assert p.is_raw and p.grade_value is None


def test_money_and_dates():
    assert parse_money("$1,250.00") == 1250.0
    assert parse_money("US $95") == 95.0
    assert parse_money(None) is None
    assert parse_sold_at("2026-03-29") == datetime(2026, 3, 29, tzinfo=UTC)
    assert parse_sold_at("03/29/2026") == datetime(2026, 3, 29, tzinfo=UTC)
    assert parse_sold_at("garbage") is None


def test_phrase_boundaries():
    assert contains_phrase("2023 topps chrome ohtani", "Topps")
    assert not contains_phrase("toppsy", "Topps")


def test_search_tokens_handle_seasons_and_numbers():
    from app.api.v1.cards import search_tokens

    assert search_tokens("2024-25 prizm black Damian Lillard") == ["2024", "prizm", "black", "damian", "lillard"]
    assert search_tokens("topps chrome #1") == ["topps", "chrome", "1"]
    assert search_tokens("1996/97 topps") == ["1996", "topps"]
