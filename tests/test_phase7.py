"""OpenAlex daily-budget circuit breaker and API-key handling."""

from unittest.mock import MagicMock

import pytest

from citation_verifier import api_clients
from citation_verifier.api_clients import ApiUnavailable, OpenAlexClient


@pytest.fixture(autouse=True)
def _reset_breaker(monkeypatch):
    monkeypatch.setattr(api_clients, "_openalex_blocked_until", 0.0)


def _resp(status, retry_after=None, body=None):
    r = MagicMock()
    r.status_code = status
    r.headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    r.json.return_value = body or {}
    r.raise_for_status.side_effect = (
        None if status < 400 else __import__("requests").exceptions.HTTPError(f"{status}")
    )
    return r


def _client(resp):
    c = OpenAlexClient()
    c.session = MagicMock()
    c.session.get.return_value = resp
    return c


class TestBudgetBreaker:
    def test_long_retry_after_trips_breaker_and_stops_network_calls(self):
        c = _client(_resp(429, retry_after=66313))
        with pytest.raises(ApiUnavailable):
            c.search_candidates("some title")
        assert c.session.get.call_count == 1
        with pytest.raises(ApiUnavailable, match="budget"):
            c.search_candidates("another title")
        with pytest.raises(ApiUnavailable, match="budget"):
            c.fetch_by_doi("10.1/x")
        assert c.session.get.call_count == 1          # no further requests

    def test_short_retry_after_is_ordinary_throttling(self):
        c = _client(_resp(429, retry_after=2))
        with pytest.raises(ApiUnavailable):
            c.search_candidates("t")
        c.session.get.return_value = _resp(200, body={"results": []})
        assert c.search_candidates("t") == []         # not blocked

    def test_breaker_expires_and_probes_again(self, monkeypatch):
        c = _client(_resp(429, retry_after=66313))
        with pytest.raises(ApiUnavailable):
            c.search_candidates("t")
        monkeypatch.setattr(api_clients, "_openalex_blocked_until", 0.0)  # recheck time reached
        c.session.get.return_value = _resp(200, body={"results": []})
        assert c.search_candidates("t") == []

    def test_blocked_doi_lookup_degrades_cross_validation_gracefully(self):
        from citation_verifier.config import GroundTruth, ParsedReference, Verdict
        from citation_verifier.verifier import CitationVerifier
        api_clients._openalex_blocked_until = __import__("time").time() + 3600
        v = CitationVerifier(cross_validate=True)
        v.crossref = MagicMock()
        v.datacite = MagicMock()
        v.crossref.fetch_by_doi.return_value = GroundTruth(
            doi="10.1/x", title="Some real title", year=2020, api_source="Crossref")
        ref = ParsedReference(raw_text="x", doi="10.1/x", candidate_title="Some real title", year=2020)
        assert v._verify_single(ref).verdict == Verdict.VERIFIED


class TestApiKey:
    def test_key_sent_as_bearer_header_not_in_url(self, monkeypatch):
        monkeypatch.setattr(api_clients, "OPENALEX_API_KEY", "sekret123")
        c = OpenAlexClient()
        assert c.session.headers["Authorization"] == "Bearer sekret123"
        c.session = MagicMock()
        c.session.get.return_value = _resp(200, body={"results": []})
        c.search_candidates("t")
        _, kwargs = c.session.get.call_args
        assert "sekret123" not in str(kwargs.get("params"))

    def test_no_key_no_header(self, monkeypatch):
        monkeypatch.setattr(api_clients, "OPENALEX_API_KEY", None)
        assert "Authorization" not in OpenAlexClient().session.headers
