"""Pure, DB-free listing title parsing (unit-testable)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

GRADERS = ("PSA", "BGS", "SGC", "CGC")
_GRADE_RE = re.compile(r"\b(psa|bgs|sgc|cgc)\s*-?\s*(10|[1-9](?:\.5)?)\b", re.I)
_CARD_NO_RE = re.compile(r"#\s*([A-Za-z0-9-]+)")
_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
_MONEY_RE = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)")
_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%m/%d/%Y", "%b %d, %Y", "%d %b %Y")


def parse_money(raw: str | None) -> float | None:
    if not raw:
        return None
    m = _MONEY_RE.search(raw.replace("$", ""))
    return float(m.group(1).replace(",", "")) if m else None


def parse_sold_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


@dataclass
class ParsedTitle:
    year: int | None
    grader: str | None
    grade_value: str | None
    card_number: str | None
    is_raw: bool


def parse_title(title: str, condition: str | None = None) -> ParsedTitle:
    text = f"{title} {condition or ''}"
    year = _YEAR_RE.search(title)
    grade = _GRADE_RE.search(text)
    num = _CARD_NO_RE.search(title)
    return ParsedTitle(
        year=int(year.group(1)) if year else None,
        grader=grade.group(1).upper() if grade else None,
        grade_value=grade.group(2) if grade else None,
        card_number=num.group(1).upper() if num else None,
        is_raw=grade is None,
    )


def contains_phrase(haystack: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])", haystack.lower()) is not None
