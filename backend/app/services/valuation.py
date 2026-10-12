"""Deterministic, explainable card valuation.

Rules (in order):
1. EXACT comps: same card, same grade (PSA 10 is never priced off PSA 9 or raw),
   same parallel when both sides know it. Use the requested window; if it has fewer
   than MIN_EXACT comps, widen to 1y and then all-time, lowering confidence.
2. SIMILAR fallback: same player + brand + year + grade on other cards, blended in
   when exact comps are thin.
3. Estimate = median; range = interquartile range (or min/max for < 4 comps).
4. With 5+ comps, sales below 1/3 or above 3x the median are treated as outliers
   (usually a mismatched listing: wrong parallel, a lot, a slab) and left out.
   The default window is the last 30 days, widening when there are < 3 sales.

Everything is computed from comps loaded in one or two queries, so pricing a whole
collection or a page of search results is O(1) queries, not O(n).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import median, quantiles

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.models.entities import Card, SaleComp

WINDOW_TO_DAYS: dict[str, int | None] = {"30d": 30, "90d": 90, "1y": 365, "all": None}
FALLBACK_CHAIN = ["30d", "90d", "1y", "all"]
MIN_EXACT = 3
OUTLIER_RATIO = 3.0  # keep sales within [median / 3, median * 3]
OUTLIER_MIN_SALES = 5  # with fewer sales there isn't enough to tell what's normal
SIMILAR_TARGET = 6


def normalize_window(window: str | None) -> str:
    w = (window or "30d").lower()
    return w if w in WINDOW_TO_DAYS else "30d"


def window_cutoff(window: str) -> datetime | None:
    days = WINDOW_TO_DAYS[normalize_window(window)]
    return None if days is None else datetime.now(UTC) - timedelta(days=days)


@dataclass(frozen=True)
class GradeKey:
    """None/None means raw. grade_company_id None + grade_value set is treated as that grade."""

    grade_company_id: int | None = None
    grade_value: str | None = None
    any_grade: bool = False

    @classmethod
    def any(cls) -> "GradeKey":
        return cls(any_grade=True)

    @property
    def is_raw(self) -> bool:
        return not self.any_grade and self.grade_value is None

    def matches(self, comp: "CompRow") -> bool:
        if self.any_grade:
            return True
        if self.is_raw:
            return comp.grade_value is None
        if comp.grade_value != self.grade_value:
            return False
        # Unknown company on either side is tolerated (older rows only stored the number).
        return self.grade_company_id is None or comp.grade_company_id in (None, self.grade_company_id)

    def label(self, company_names: dict[int, str] | None = None) -> str:
        if self.any_grade:
            return "All grades"
        if self.is_raw:
            return "Raw"
        company = (company_names or {}).get(self.grade_company_id or -1, "PSA" if self.grade_company_id == 1 else "")
        return f"{company} {self.grade_value}".strip()


@dataclass(frozen=True)
class CompRow:
    card_id: int
    card_parallel_id: int | None
    grade_company_id: int | None
    grade_value: str | None
    sold_at: datetime
    total_price: float


@dataclass(frozen=True)
class ValuationKey:
    card_id: int
    grade: GradeKey = GradeKey.any()
    card_parallel_id: int | None = None


def split_outliers(prices: list[float]) -> tuple[list[float], list[float]]:
    """(kept, outliers). Median-based, so one wild sale can't move the yardstick."""
    if len(prices) < OUTLIER_MIN_SALES:
        return list(prices), []
    med = median(prices)
    if med <= 0:
        return list(prices), []
    kept = [p for p in prices if med / OUTLIER_RATIO <= p <= med * OUTLIER_RATIO]
    out = [p for p in prices if not (med / OUTLIER_RATIO <= p <= med * OUTLIER_RATIO)]
    return kept, out


def _price_range(prices: list[float]) -> tuple[float, float]:
    s = sorted(prices)
    if len(s) < 4:
        return float(s[0]), float(s[-1])
    q1, _, q3 = quantiles(s, n=4, method="inclusive")
    return round(float(q1), 2), round(float(q3), 2)


def _empty(reason: str, explanation: str, exact: int = 0, similar: int = 0) -> dict:
    return {
        "estimated_price": None,
        "low_estimate": None,
        "high_estimate": None,
        "confidence_score": 0.0,
        "exact_comp_count": exact,
        "similar_comp_count": similar,
        "reason_codes": [reason],
        "explanation": explanation,
        "methodology": "no_data" if reason != "CARD_NOT_FOUND" else "not_found",
        "window_used": None,
        "last_sale_at": None,
    }


class ValuationEngine:
    """Loads comps for a set of cards once, then values any number of (card, grade) keys."""

    def __init__(self, db: Session, card_ids: set[int] | list[int]):
        self.db = db
        ids = set(card_ids)
        self.cards: dict[int, Card] = {c.id: c for c in db.scalars(select(Card).where(Card.id.in_(ids)))} if ids else {}

        identities = {(c.player_id, c.brand_id, c.year) for c in self.cards.values()}
        self.peer_ids: dict[tuple[int, int, int], set[int]] = {}
        all_ids = set(ids)
        if identities:
            rows = db.execute(
                select(Card.id, Card.player_id, Card.brand_id, Card.year).where(
                    tuple_(Card.player_id, Card.brand_id, Card.year).in_(list(identities))
                )
            ).all()
            for cid, pid, bid, yr in rows:
                self.peer_ids.setdefault((pid, bid, yr), set()).add(cid)
                all_ids.add(cid)

        self.comps: dict[int, list[CompRow]] = {}
        if all_ids:
            for r in db.execute(
                select(
                    SaleComp.card_id,
                    SaleComp.card_parallel_id,
                    SaleComp.grade_company_id,
                    SaleComp.grade_value,
                    SaleComp.sold_at,
                    SaleComp.total_price,
                )
                .where(SaleComp.card_id.in_(all_ids))
                .order_by(SaleComp.sold_at.desc())
            ).all():
                self.comps.setdefault(r.card_id, []).append(
                    CompRow(r.card_id, r.card_parallel_id, r.grade_company_id, r.grade_value, r.sold_at, float(r.total_price))
                )

    def comps_for(self, key: ValuationKey, window: str = "all") -> list[CompRow]:
        cutoff = window_cutoff(window)
        out = []
        for c in self.comps.get(key.card_id, []):
            if not key.grade.matches(c):
                continue
            if key.card_parallel_id and c.card_parallel_id and c.card_parallel_id != key.card_parallel_id:
                continue
            if cutoff and c.sold_at < cutoff:
                continue
            out.append(c)
        return out

    def value(self, key: ValuationKey, window: str = "30d") -> dict:
        window = normalize_window(window)
        card = self.cards.get(key.card_id)
        if card is None:
            return _empty("CARD_NOT_FOUND", "Card not found")

        reason_codes: list[str] = []
        start = FALLBACK_CHAIN.index(window)
        exact: list[CompRow] = []
        window_used = window
        for w in FALLBACK_CHAIN[start:]:
            exact = self.comps_for(key, w)
            window_used = w
            if len(exact) >= MIN_EXACT:
                break
        if window_used != window and exact:
            reason_codes.append(f"WIDENED_TO_{window_used.upper()}")

        grade_label = key.grade.label()
        last_sale = exact[0].sold_at if exact else None
        exact_prices, outliers = split_outliers([c.total_price for c in exact])
        if outliers:
            reason_codes.append(f"OUTLIERS_EXCLUDED_{len(outliers)}")

        if len(exact_prices) >= MIN_EXACT:
            low, high = _price_range(exact_prices)
            confidence = min(0.95, 0.5 + 0.05 * len(exact_prices))
            if window_used != window:
                confidence -= 0.15 if window_used == "1y" else 0.25
            return {
                "estimated_price": round(float(median(exact_prices)), 2),
                "low_estimate": low,
                "high_estimate": high,
                "confidence_score": round(max(confidence, 0.2), 2),
                "exact_comp_count": len(exact_prices),
                "similar_comp_count": 0,
                "reason_codes": ["EXACT_COMPS", f"GRADE_{grade_label.upper().replace(' ', '_')}", f"WINDOW_{window_used.upper()}"]
                + reason_codes,
                "explanation": f"Median of {len(exact_prices)} {grade_label} sales of this exact card ({window_used} window)"
                + (f"; {len(outliers)} outlier sale(s) left out." if outliers else "."),
                "methodology": "exact_recent_comps_median",
                "window_used": window_used,
                "last_sale_at": last_sale,
            }

        # No sale of THIS card at this grade: don't invent a price from other cards
        # (a Lazer parallel is not worth what a base or an insert of the same player sells for).
        if not exact_prices:
            return _empty(
                "NO_COMPS",
                f"No {grade_label} sales recorded for this card yet. Add a sale to price it.",
            )

        # Similar comps: same player/brand/year/grade, other cards, only to support thin exact comps.
        peers = self.peer_ids.get((card.player_id, card.brand_id, card.year), set()) - {card.id}
        similar: list[CompRow] = []
        for pid in peers:
            similar.extend(self.comps_for(ValuationKey(pid, key.grade), window_used))
        similar.sort(key=lambda c: c.sold_at, reverse=True)
        similar_prices = [c.total_price for c in similar]

        blended = exact_prices + similar_prices[: max(0, SIMILAR_TARGET - len(exact_prices))]
        if not blended:
            return _empty(
                "NO_COMPS",
                f"No {grade_label} sales found for this card or close peers.",
                exact=len(exact_prices),
                similar=len(similar_prices),
            )

        low, high = _price_range(blended)
        confidence = 0.25 + 0.1 * len(exact_prices)
        if window_used in ("1y", "all") and window not in ("1y", "all"):
            confidence -= 0.1
        codes = ["THIN_EXACT_COMPS" if exact_prices else "NO_EXACT_COMPS", f"GRADE_{grade_label.upper().replace(' ', '_')}"]
        if similar_prices:
            codes.append("SIMILAR_CARDS_BLENDED")
        expl = (
            f"Only {len(exact_prices)} {grade_label} sale(s) of this card"
            + (f"; blended with {len(blended) - len(exact_prices)} similar-card sales." if similar_prices else ".")
        )
        return {
            "estimated_price": round(float(median(blended)), 2),
            "low_estimate": low,
            "high_estimate": high,
            "confidence_score": round(max(min(confidence, 0.5), 0.15), 2),
            "exact_comp_count": len(exact_prices),
            "similar_comp_count": len(similar_prices),
            "reason_codes": codes + [f"WINDOW_{window_used.upper()}"] + reason_codes,
            "explanation": expl,
            "methodology": "low_liquidity_fallback",
            "window_used": window_used,
            "last_sale_at": last_sale or (similar[0].sold_at if similar else None),
        }


def compute_card_valuation(
    db: Session,
    card_id: int,
    window: str = "30d",
    grade: GradeKey | None = None,
    card_parallel_id: int | None = None,
) -> dict:
    engine = ValuationEngine(db, {card_id})
    return engine.value(ValuationKey(card_id, grade or GradeKey.any(), card_parallel_id), window)


def grade_key_for_item(grade_company_id: int | None, grade_value: str | None, is_graded: bool) -> GradeKey:
    if not is_graded and grade_value is None:
        return GradeKey()  # raw
    return GradeKey(grade_company_id=grade_company_id, grade_value=grade_value)


def parse_grade_param(grade: str | None) -> GradeKey:
    """'raw' | 'psa10' | 'PSA 10' | '10' | None/'all'."""
    if not grade or grade.lower() in ("all", "any"):
        return GradeKey.any()
    g = grade.strip().lower().replace(" ", "")
    if g == "raw":
        return GradeKey()
    company_id = None
    for prefix, cid in (("psa", 1),):
        if g.startswith(prefix):
            company_id = cid
            g = g[len(prefix) :]
    return GradeKey(grade_company_id=company_id, grade_value=g or None)
