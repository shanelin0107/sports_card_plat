from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Brand,
    Card,
    CardSet,
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

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, db: Session):
        self.db = db
        self.adapter: SourceAdapter = EbayPublicAdapter()

    def run(self, mode: str = "daily", tracked_card_ids: list[int] | None = None) -> IngestionRun:
        source = self._get_or_create_source(self.adapter.source_name)
        run = IngestionRun(source_platform_id=source.id, mode=mode, status="running")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        try:
            records = self.adapter.fetch_sold_listings(mode=mode, tracked_card_ids=tracked_card_ids)
            run.fetched_count = len(records)
            for rec in records:
                raw = self._upsert_raw(source.id, rec)
                run.raw_upserted_count += 1
                norm, parse_error = self._normalize(raw, source.id)
                if parse_error:
                    run.parse_error_count += 1
                    self._add_issue(run.id, "parse_error", raw.source_listing_id, None, {"reason": parse_error})
                    continue
                run.normalized_count += 1
                match, confidence = self._match(norm)
                if match is None:
                    self._add_issue(run.id, "unmatched", norm.source_listing_id, norm.id, {"confidence": confidence})
                    continue
                run.matched_count += 1
                if confidence < 0.75:
                    run.low_confidence_count += 1
                    self._add_issue(run.id, "low_confidence", norm.source_listing_id, norm.id, {"confidence": confidence})
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
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.now(UTC)
            self.db.commit()
            raise

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
        if existing:
            existing.payload_json = rec.payload_json
            existing.listing_title_raw = rec.listing_title_raw
            existing.sold_at_raw = rec.sold_at_raw
            self.db.commit()
            self.db.refresh(existing)
            return existing

        raw = RawMarketListing(
            source_platform_id=source_platform_id,
            source_listing_id=rec.source_listing_id,
            sold_at_raw=rec.sold_at_raw,
            listing_title_raw=rec.listing_title_raw,
            listing_url_raw=rec.listing_url_raw,
            condition_raw=rec.condition_raw,
            price_raw=rec.price_raw,
            shipping_raw=rec.shipping_raw,
            payload_json=rec.payload_json,
        )
        self.db.add(raw)
        self.db.commit()
        self.db.refresh(raw)
        return raw

    def _normalize(self, raw: RawMarketListing, source_platform_id: int) -> tuple[NormalizedSale | None, str | None]:
        title = raw.listing_title_raw.lower()
        year_match = re.search(r"(19|20)\d{2}", title)
        price_match = re.search(r"\$?([0-9]+(?:\.[0-9]{1,2})?)", raw.price_raw or "")
        shipping_match = re.search(r"\$?([0-9]+(?:\.[0-9]{1,2})?)", raw.shipping_raw or "")
        if not year_match or not price_match:
            return None, "missing_year_or_price"

        sold_at = datetime.now(UTC)
        parsed_year = int(year_match.group(0))
        sale_price = float(price_match.group(1))
        shipping = float(shipping_match.group(1)) if shipping_match else 0.0
        total = sale_price + shipping

        existing = self.db.execute(
            select(NormalizedSale).where(NormalizedSale.raw_market_listing_id == raw.id)
        ).scalar_one_or_none()
        if existing:
            existing.sale_price = sale_price
            existing.shipping_price = shipping
            existing.total_price = total
            existing.parsed_year = parsed_year
            existing.parsed_brand = "Topps" if "topps" in title else ("Panini" if "panini" in title else None)
            existing.parsed_player = "Shohei Ohtani" if "ohtani" in title else ("Victor Wembanyama" if "wembanyama" in title else None)
            existing.grade_value = "10" if "psa 10" in title else None
            existing.grade_company_id = 1 if "psa" in title else None
            self.db.commit()
            self.db.refresh(existing)
            return existing, None

        norm = NormalizedSale(
            raw_market_listing_id=raw.id,
            source_platform_id=source_platform_id,
            source_listing_id=raw.source_listing_id,
            sold_at=sold_at,
            sale_price=sale_price,
            shipping_price=shipping,
            total_price=total,
            currency="USD",
            grade_company_id=1 if "psa" in title else None,
            grade_value="10" if "psa 10" in title else None,
            parsed_year=parsed_year,
            parsed_brand="Topps" if "topps" in title else ("Panini" if "panini" in title else None),
            parsed_set="Topps Chrome" if "chrome" in title else ("Panini Prizm" if "prizm" in title else None),
            parsed_player="Shohei Ohtani" if "ohtani" in title else ("Victor Wembanyama" if "wembanyama" in title else None),
            parsed_card_number="#1" if "#1" in title else ("#136" if "136" in title else None),
            parsed_parallel="Silver" if "silver" in title else "Base",
            parsed_variation="Base",
        )
        self.db.add(norm)
        self.db.commit()
        self.db.refresh(norm)
        return norm, None

    def _match(self, norm: NormalizedSale) -> tuple[ListingCardMatch | None, float]:
        stmt = select(Card)
        if norm.parsed_year:
            stmt = stmt.where(Card.year == norm.parsed_year)
        cards = self.db.scalars(stmt.limit(100)).all()
        best = None
        best_score = 0.0
        for card in cards:
            score = 0.0
            text = (card.search_text_normalized or "").lower()
            if norm.parsed_brand and norm.parsed_brand.lower() in text:
                score += 0.25
            if norm.parsed_player and norm.parsed_player.lower() in text:
                score += 0.35
            if norm.parsed_set and norm.parsed_set.lower() in text:
                score += 0.2
            if norm.parsed_card_number and norm.parsed_card_number.replace("#", "") in text:
                score += 0.2
            if score > best_score:
                best_score = score
                best = card

        if not best:
            return None, 0.0

        existing = self.db.execute(select(ListingCardMatch).where(ListingCardMatch.normalized_sale_id == norm.id)).scalar_one_or_none()
        if existing:
            existing.card_id = best.id
            existing.confidence_score = best_score
            existing.match_method = "rule_based_v1"
            self.db.commit()
            self.db.refresh(existing)
            return existing, best_score

        match = ListingCardMatch(
            normalized_sale_id=norm.id,
            card_id=best.id,
            card_parallel_id=None,
            match_method="rule_based_v1",
            confidence_score=best_score,
            is_primary=True,
            reason_codes=["TEXT_MATCH_SCORE"],
        )
        self.db.add(match)
        self.db.commit()
        self.db.refresh(match)
        return match, best_score

    def _promote(self, norm: NormalizedSale, match: ListingCardMatch) -> None:
        existing = self.db.execute(select(SaleComp).where(SaleComp.normalized_sale_id == norm.id)).scalar_one_or_none()
        if existing:
            existing.total_price = norm.total_price
            existing.sale_price = norm.sale_price
            existing.shipping_price = norm.shipping_price
            existing.sold_at = norm.sold_at
            self.db.commit()
            return

        comp = SaleComp(
            normalized_sale_id=norm.id,
            card_id=match.card_id,
            card_parallel_id=match.card_parallel_id,
            grade_company_id=norm.grade_company_id,
            grade_value=norm.grade_value,
            sold_at=norm.sold_at,
            sale_price=norm.sale_price,
            shipping_price=norm.shipping_price,
            total_price=norm.total_price,
            currency=norm.currency,
        )
        self.db.add(comp)
        self.db.commit()

    def _add_issue(self, run_id: int, issue_type: str, source_listing_id: str | None, normalized_sale_id: int | None, details: dict):
        issue = IngestionIssue(
            ingestion_run_id=run_id,
            issue_type=issue_type,
            source_listing_id=source_listing_id,
            normalized_sale_id=normalized_sale_id,
            details_json=details,
        )
        self.db.add(issue)
        self.db.commit()
