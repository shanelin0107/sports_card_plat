from datetime import UTC, datetime, timedelta

from app.services.valuation import CompRow, GradeKey, _price_range, parse_grade_param


def _comp(grade, days_ago=1, price=100.0):
    return CompRow(1, None, 1 if grade else None, grade, datetime.now(UTC) - timedelta(days=days_ago), price)


def test_grade_key_never_mixes_grades():
    psa10 = GradeKey(1, "10")
    assert psa10.matches(_comp("10"))
    assert not psa10.matches(_comp("9"))
    assert not psa10.matches(_comp(None))
    assert GradeKey().matches(_comp(None))
    assert not GradeKey().matches(_comp("10"))
    assert GradeKey.any().matches(_comp("9"))


def test_parse_grade_param():
    assert parse_grade_param("raw").is_raw
    assert parse_grade_param("PSA 10") == GradeKey(1, "10")
    assert parse_grade_param("psa9").grade_value == "9"
    assert parse_grade_param(None).any_grade


def test_price_range():
    assert _price_range([100.0]) == (100.0, 100.0)
    assert _price_range([100.0, 200.0, 300.0]) == (100.0, 300.0)
    low, high = _price_range([100.0, 110.0, 120.0, 130.0, 500.0])
    assert low == 110.0 and high == 130.0  # outlier excluded from IQR


def test_split_outliers_is_median_based():
    from app.services.valuation import split_outliers

    kept, out = split_outliers([25, 27, 30, 22, 140, 5, 26])
    assert sorted(out) == [5, 140] and 140 not in kept
    # normal spread ($14–$46 around $26) is all kept
    assert split_outliers([14.5, 22, 26, 26.5, 30, 46])[1] == []
    # too few sales to judge: keep everything
    assert split_outliers([10, 200, 30])[1] == []
