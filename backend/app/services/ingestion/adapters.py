from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class RawListingRecord:
    source_listing_id: str
    sold_at_raw: str | None
    listing_title_raw: str
    listing_url_raw: str | None
    condition_raw: str | None
    price_raw: str | None
    shipping_raw: str | None
    payload_json: dict


class SourceAdapter(Protocol):
    source_name: str

    def fetch_sold_listings(self, *, mode: str, tracked_card_ids: list[int] | None = None) -> list[RawListingRecord]:
        ...


class EbayPublicAdapter:
    """Lawful MVP path: consumes pre-exported public sold/completed data feed.

    This class intentionally avoids direct scraping in code. For phase 1, reviewers can
    place a JSON file produced by lawful manual export/API workflow.
    """

    source_name = "eBay"

    def __init__(self, fixture_path: str = "seed/ebay_sample_feed.json"):
        self.fixture_path = Path(fixture_path)

    def fetch_sold_listings(self, *, mode: str, tracked_card_ids: list[int] | None = None) -> list[RawListingRecord]:
        if not self.fixture_path.exists():
            return []
        data = json.loads(self.fixture_path.read_text())
        records: list[RawListingRecord] = []
        for item in data:
            records.append(
                RawListingRecord(
                    source_listing_id=item["source_listing_id"],
                    sold_at_raw=item.get("sold_at_raw"),
                    listing_title_raw=item["listing_title_raw"],
                    listing_url_raw=item.get("listing_url_raw"),
                    condition_raw=item.get("condition_raw"),
                    price_raw=item.get("price_raw"),
                    shipping_raw=item.get("shipping_raw"),
                    payload_json=item,
                )
            )
        return records
