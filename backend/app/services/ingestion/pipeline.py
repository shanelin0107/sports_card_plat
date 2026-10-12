from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Brand,
    Card,
    CardParallel,
    CardSet,
    GradeCompany,
    IngestionIssue,
    IngestionRun,
    ListingCardMatch,
    NormalizedSale,
    Player,
    RawMarketListing,
    SaleComp,
    SourcePlatform,
)
from app.services.ingestion.adapters import EbayPublicAdapter, RawListingRecord, SourceAdapter
from app.services.ingestion.parsing import contains_phrase, parse_money, parse_sold_at, parse_title

logger = logging.getLogger(__name__)

PROMOTE_THRESHOLD = 0.75


class Catalog:
    """In-memory lookup of brands / sets / players / cards for matching."""

    def __init__(self, db: Session):
        self.brands = db.execute(select(Brand.id, Brand.name)).all()
        self.sets = db.execute(select(CardSet.id, CardSet.name, CardSet.brand_id)).all()
        self.players = db.execute(select(Player.id, Player.full_name)).all()
        self.cards = db.scalars(select(Card)).all()
        self.parallels = db.execute(select(CardParallel.id, CardParallel.card_id, CardParallel.parallel_name)).all()
        self.grade_companies = {name.upper(): gid for gid, name in db.execute(select(GradeCompany.id, GradeCompany.name)).all()}

    def find_brand(self, title: str):
        return next(((i, n) for i, n in self.brands if contains_phrase(title, n)), None)

    def find_set(self, title: str):
        # Longest name first so "Topps Chrome" wins over "Topps".
        for i, n, b in sorted(self.sets, key=lambda s: -len(s[1])):
            short = n.split(" ", 1)[1] if " " in n else n  # "Panini Prizm" -> "Prizm"
            if contains_phrase(title, n) or contains_phrase(title, short):
                return i, n, b
        return None

    def find_player(self, title: str):
        for i, n in self.players:
            last = n.split()[-1]
            if contains_phrase(title, n) or contains_phrase(title, last):
                return i, n
        return None

    def find_parallel(self, card_id: int, title: str):
        named = [(i, n) for i, c, n in self.parallels if c == card_id and n.lower() != "base" and contains_phrase(title, n)]
        if named:
            return named[0]
        base = [(i, n) for i, c, n in self.parallels if c == card_id and n.lower() == "base"]
        return base[0] if base else None


class IngestionService:
    def __init__(self, db: Session, adapter: SourceAdapter | None = None):
        self.db = db
        self.adapter: SourceAdapter = adapter or EbayPublicAdapter()

    def run(self, mode: str = "daily", tracked_card_ids: list[int] | None = None) -> IngestionRun:
        source = self._get_or_create_source(self.adapter.source_name)
        run = IngestionRun(source_platform_id=source.id, mode=mode, status="running")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        run_id = run.id

        try:
            catalog = Catalog(self.db)
            records = self.adapter.fetch_sold_listings(mode=mode, tracked_card_ids=tracked_card_ids)
            run.fetched_count = len(records)
            for rec in records:
                raw = self._upsert_raw(source.id, rec)
                run.raw_upserted_count += 1
                norm, parse_error = self._normalize(raw, source.id, catalog)
                if parse_error:
                    run.parse_error_count += 1
                    self._add_issue(run_id, "parse_error", raw.source_listing_id, None, {"reason": parse_error, "title": raw.listing_title_raw})
                    continue
                run.normalized_count += 1
                card_id, parallel_id, confidence, reasons = self._match(norm, catalog)
                if card_id is None:
                    self._add_issue(run_id, "unmatched", norm.source_listing_id, norm.id, self._issue_details(raw, norm, confidence))
                    continue
                if tracked_card_ids and card_id not in tracked_card_ids:
                    continue
                match = self._upsert_match(norm, card_id, parallel_id, confidence, reasons)
                run.matched_count += 1
                if confidence < PROMOTE_THRESHOLD:
                    run.low_confidence_count += 1
                    details = self._issue_details(raw, norm, confidence) | {"suggested_card_id": card_id}
                    self._add_issue(run_id, "low_confidence", norm.source_listing_id, norm.id, details)
                    continue
                self._promote(norm, match)
                run.promoted_count += 1

            run.status = "completed"
            run.completed_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(run)
            return run
        except Exception as exc:
            logger.exception("Ingestion run failed")
            # The session may be in a failed transaction; roll back before recording the failure.
            self.db.rollback()
            failed = self.db.get(IngestionRun, run_id)
            failed.status = "failed"
            failed.error_message = str(exc)[:2000]
            failed.completed_at = datetime.now(UTC)
            self.db.commit()
            raise

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _issue_details(raw: RawMarketListing, norm: NormalizedSale, confidence: float) -> dict:
        return {
            "title": raw.listing_title_raw,
            "price": norm.total_price,
            "sold_at": norm.sold_at.isoformat() if norm.sold_at else None,
            "grade": f"{norm.grade_value}" if norm.grade_value else "Raw",
            "url": raw.listing_url_raw,
            "confidence": round(confidence, 2),
        }

    def _get_or_create_source(self, name: str) -> SourcePlatform:
        src = self.db.execute(select(SourcePlatform).where(SourcePlatform.name == name)).scalar_one_or_none()
        if src:
            return src
        src = SourcePlatform(name=name, source_type="marketplace")
        self.db.add(src)
        self.db.commit()
        self.db.refresh(src)
        return src

    def _upsert_raw(self, source_platform_id: int, rec: RawListingRecord) -> RawMarketListing:
        existing = self.db.execute(
            select(RawMarketListing).where(
                and_(
                    RawMarketListing.source_platform_id == source_platform_id,
                    RawMarketListing.source_listing_id == rec.source_listing_id,
                )
            )
        ).scalar_one_or_none()
        target = existing or RawMarketListing(source_platform_id=source_platform_id, source_listing_id=rec.source_listing_id)
        target.sold_at_raw = rec.sold_at_raw
        target.listing_title_raw = rec.listing_title_raw
        target.listing_url_raw = rec.listing_url_raw
        target.condition_raw = rec.condition_raw
        target.price_raw = rec.price_raw
        target.shipping_raw = rec.shipping_raw
        target.payload_json = rec.payload_json
        if existing is None:
            self.db.add(target)
        self.db.flush()
        return target

    def _normalize(self, raw: RawMarketListing, source_platform_id: int, catalog: Catalog) -> tuple[NormalizedSale | None, str | None]:
        title = raw.listing_title_raw
        parsed = parse_title(title, raw.condition_raw)
        sale_price = parse_money(raw.price_raw)
        if sale_price is None:
            return None, "missing_price"
        if parsed.year is None:
            return None, "missing_year"
        sold_at = parse_sold_at(raw.sold_at_raw)
        if sold_at is None:
            return None, "unparseable_sold_date"
        shipping = parse_money(raw.shipping_raw) or 0.0

        brand = catalog.find_brand(title)
        card_set = catalog.find_set(title)
        if brand is None and card_set is not None:
            brand = next(((i, n) for i, n in catalog.brands if i == card_set[2]), None)
        player = catalog.find_player(title)

        norm = self.db.execute(select(NormalizedSale).where(NormalizedSale.raw_market_listing_id == raw.id)).scalar_one_or_none()
        if norm is None:
            norm = NormalizedSale(raw_market_listing_id=raw.id, source_platform_id=source_platform_id, source_listing_id=raw.source_listing_id)
            self.db.add(norm)
        norm.sold_at = sold_at
        norm.sale_price = sale_price
        norm.shipping_price = shipping
        norm.total_price = round(sale_price + shipping, 2)
        norm.currency = "USD"
        norm.grade_company_id = catalog.grade_companies.get(parsed.grader) if parsed.grader else None
        norm.grade_value = parsed.grade_value
        norm.parsed_year = parsed.year
        norm.parsed_brand = brand[1] if brand else None
        norm.parsed_set = card_set[1] if card_set else None
        norm.parsed_player = player[1] if player else None
        norm.parsed_card_number = parsed.card_number
        norm.parsed_variation = "Base"
        self.db.flush()
        return norm, None

    def _match(self, norm: NormalizedSale, catalog: Catalog) -> tuple[int | None, int | None, float, list[str]]:
        best: tuple[int | None, float, list[str]] = (None, 0.0, [])
        for card in catalog.cards:
            if norm.parsed_year and card.year != norm.parsed_year:
                continue
            score, reasons = 0.0, []
            if norm.parsed_player and card.player_id == next((i for i, n in catalog.players if n == norm.parsed_player), None):
                score += 0.4
                reasons.append("PLAYER_MATCH")
            else:
                continue  # never match a sale to a different player
            if norm.parsed_brand and card.brand_id == next((i for i, n in catalog.brands if n == norm.parsed_brand), None):
                score += 0.15
                reasons.append("BRAND_MATCH")
            if norm.parsed_set and card.set_id == next((i for i, n, _ in catalog.sets if n == norm.parsed_set), None):
                score += 0.2
                reasons.append("SET_MATCH")
            if norm.parsed_card_number:
                if norm.parsed_card_number.lstrip("0") == card.card_number.upper().lstrip("0"):
                    score += 0.25
                    reasons.append("CARD_NUMBER_MATCH")
                else:
                    score -= 0.3
                    reasons.append("CARD_NUMBER_MISMATCH")
            if score > best[1]:
                best = (card.id, score, reasons)

        card_id, score, reasons = best
        if card_id is None or score <= 0:
            return None, None, max(score, 0.0), []
        title = self.db.get(RawMarketListing, norm.raw_market_listing_id).listing_title_raw
        parallel = catalog.find_parallel(card_id, title)
        if parallel:
            norm.parsed_parallel = parallel[1]
        return card_id, parallel[0] if parallel else None, round(min(score, 1.0), 2), reasons

    def _upsert_match(self, norm, card_id, parallel_id, confidence, reasons) -> ListingCardMatch:
        match = self.db.execute(select(ListingCardMatch).where(ListingCardMatch.normalized_sale_id == norm.id)).scalar_one_or_none()
        if match is None:
            match = ListingCardMatch(normalized_sale_id=norm.id, is_primary=True)
            self.db.add(match)
        match.card_id = card_id
        match.card_parallel_id = parallel_id
        match.match_method = "rule_based_v2"
        match.confidence_score = confidence
        match.reason_codes = reasons
        self.db.flush()
        return match

    def _promote(self, norm: NormalizedSale, match: ListingCardMatch) -> None:
        comp = self.db.execute(select(SaleComp).where(SaleComp.normalized_sale_id == norm.id)).scalar_one_or_none()
        if comp is None:
            comp = SaleComp(normalized_sale_id=norm.id)
            self.db.add(comp)
        comp.card_id = match.card_id
        comp.card_parallel_id = match.card_parallel_id
        comp.grade_company_id = norm.grade_company_id
        comp.grade_value = norm.grade_value
        comp.sold_at = norm.sold_at
        comp.sale_price = norm.sale_price
        comp.shipping_price = norm.shipping_price
        comp.total_price = norm.total_price
        comp.currency = norm.currency
        self.db.flush()

    def _add_issue(self, run_id: int, issue_type: str, source_listing_id: str | None, normalized_sale_id: int | None, details: dict):
        # Don't pile up a duplicate open issue every time the same listing is re-ingested.
        existing = self.db.execute(
            select(IngestionIssue).where(
                IngestionIssue.issue_type == issue_type,
                IngestionIssue.source_listing_id == source_listing_id,
                IngestionIssue.status != "open",
            )
        ).first()
        if existing:
            return  # already resolved or dismissed by the user
        open_issue = self.db.execute(
            select(IngestionIssue).where(
                IngestionIssue.issue_type == issue_type,
                IngestionIssue.source_listing_id == source_listing_id,
                IngestionIssue.status == "open",
            )
        ).scalar_one_or_none()
        if open_issue:
            open_issue.ingestion_run_id = run_id
            open_issue.details_json = details
            open_issue.normalized_sale_id = normalized_sale_id
        else:
            self.db.add(
                IngestionIssue(
                    ingestion_run_id=run_id,
                    issue_type=issue_type,
                    source_listing_id=source_listing_id,
                    normalized_sale_id=normalized_sale_id,
                    details_json=details,
                    status="open",
                )
            )
        self.db.flush()


def resolve_issue_to_card(db: Session, issue: IngestionIssue, card_id: int) -> SaleComp:
    """Manual review: attach an unmatched / low-confidence sale to a card and promote it."""
    norm = db.get(NormalizedSale, issue.normalized_sale_id) if issue.normalized_sale_id else None
    if norm is None:
        raise ValueError("Issue has no normalized sale to promote (parse errors cannot be matched)")
    svc = IngestionService(db)
    match = svc._upsert_match(norm, card_id, None, 1.0, ["MANUAL_REVIEW"])
    match.match_method = "manual"
    svc._promote(norm, match)
    issue.status = "resolved"
    issue.resolution_card_id = card_id
    issue.resolved_at = datetime.now(UTC)
    db.commit()
    return db.execute(select(SaleComp).where(SaleComp.normalized_sale_id == norm.id)).scalar_one()
