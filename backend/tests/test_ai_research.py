"""AI price research, exercised with a fake Anthropic client (no network, no key)."""

from app.services import ai_research

SEEN = "https://www.ebay.com/itm/111"
CHECKLIST = "https://www.checklistinsider.com/2024-25-panini-prizm-black-basketball"
INVENTED = "https://www.ebay.com/itm/999"  # never returned by a search -> must be dropped


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return {
                "stop_reason": "pause_turn",
                "usage": {"input_tokens": 1000, "output_tokens": 50, "server_tool_use": {"web_search_requests": 2}},
                "content": [
                    {"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "lillard prizm black orange wave"}},
                    {
                        "type": "web_search_tool_result",
                        "tool_use_id": "s1",
                        "content": [
                            {"type": "web_search_result", "url": SEEN, "title": "Lillard Orange Wave /60"},
                            {"type": "web_search_result", "url": CHECKLIST, "title": "Checklist"},
                        ],
                    },
                ],
            }
        return {
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 2000, "output_tokens": 400, "server_tool_use": {"web_search_requests": 1}},
            "content": [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "report_prices",
                    "input": {
                        "identified_card": {"description": "2024-25 Panini Prizm Black #91 Damian Lillard Orange Wave /60"},
                        "identification_confidence": "high",
                        "sold": [
                            {"price": 42.0, "date": "2026-09-30", "grade": "Raw", "title": "Lillard Prizm Black Orange Wave 12/60",
                             "url": "https://ebay.de/itm/111", "source": "eBay", "exact_match": True},
                            {"price": 500.0, "date": "2026-09-01", "grade": "PSA 10", "title": "made up",
                             "url": INVENTED, "source": "eBay", "exact_match": True},
                        ],
                        "active": [],
                        "summary": "One verified sale.",
                    },
                }
            ],
        }


class FakeClient:
    def __init__(self):
        self.messages = FakeMessages()


def test_run_research_drops_unretrieved_sources_and_handles_pause():
    fake = FakeClient()
    out = ai_research.run_research("2024-25 prizm black lillard orange /60", client=fake)
    assert len(fake.messages.calls) == 2  # pause_turn was continued
    sold = out["result"]["sold"]
    assert [s["price"] for s in sold] == [42.0]  # ebay.de == ebay.com listing, invented one dropped
    assert out["result"]["unverified"][0]["url"] == INVENTED
    assert out["usage"]["searches"] == 3


def test_endpoint_flow_and_save_comp(client, monkeypatch):
    from app.core.config import settings

    assert client.get("/api/v1/ai/status").json()["enabled"] is False
    assert client.post("/api/v1/ai/price-research", json={"query": "x"}).status_code == 503

    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(ai_research, "_client", lambda: FakeClient())

    card = client.post(
        "/api/v1/catalog/cards",
        json={"sport": "Basketball", "year": 2024, "brand": "Panini", "set_name": "Prizm Black", "player": "Damian Lillard",
              "card_number": "91", "parallel": "Orange Wave"},
    ).json()
    job = client.post("/api/v1/ai/price-research", json={"card_id": card["card_id"]})
    assert job.status_code == 202
    assert "Prizm Black" in job.json()["query"] and "Orange Wave" in job.json()["query"]

    done = client.get(f"/api/v1/ai/price-research/{job.json()['id']}").json()  # background task already ran
    assert done["status"] == "completed"
    assert len(done["result"]["sold"]) == 1 and "_card_context" not in done["result"]

    r = client.post(f"/api/v1/ai/price-research/{done['id']}/save-comp", json={"index": 0})
    assert r.status_code == 200 and not r.json()["already_saved"]
    again = client.post(f"/api/v1/ai/price-research/{done['id']}/save-comp", json={"index": 0}).json()
    assert again["already_saved"]

    comps = client.get(f"/api/v1/cards/{card['card_id']}/comps", params={"window": "all"}).json()
    assert [c["total_price"] for c in comps] == [42.0] and comps[0]["grade_label"] == "Raw"
