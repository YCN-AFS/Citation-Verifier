"""Tests for phase-1 hardening: transient API errors and history isolation."""

from unittest.mock import MagicMock, patch

import pytest

from citation_verifier import history
from citation_verifier.api_clients import ApiUnavailable, CrossrefClient
from citation_verifier.config import GroundTruth, ParsedReference, Verdict
from citation_verifier.verifier import CitationVerifier


def _verifier():
    v = CitationVerifier(cross_validate=False)
    v.crossref = MagicMock()
    v.datacite = MagicMock()
    v.openalex = MagicMock()
    return v


REF = ParsedReference(raw_text="x", doi="10.1000/xyz", candidate_title="Some title")


@patch("citation_verifier.verifier.get_cached", return_value=None)
@patch("citation_verifier.verifier.set_cached")
class TestTransientErrors:
    def test_all_apis_down_is_api_error_not_dead_doi(self, mock_set, mock_get):
        v = _verifier()
        for c in (v.crossref, v.datacite, v.openalex):
            c.fetch_by_doi.side_effect = ApiUnavailable("timeout")
        result = v._verify_single(REF)
        assert result.verdict == Verdict.API_ERROR
        mock_set.assert_not_called()

    def test_primary_down_but_fallback_404_is_api_error(self, mock_set, mock_get):
        v = _verifier()
        v.crossref.fetch_by_doi.side_effect = ApiUnavailable("503")
        v.datacite.fetch_by_doi.return_value = None
        v.openalex.fetch_by_doi.return_value = None
        assert v._verify_single(REF).verdict == Verdict.API_ERROR

    def test_primary_down_fallback_succeeds(self, mock_set, mock_get):
        v = _verifier()
        v.crossref.fetch_by_doi.side_effect = ApiUnavailable("503")
        v.datacite.fetch_by_doi.return_value = GroundTruth(
            doi=REF.doi, title="Some title", year=2020, api_source="DataCite")
        assert v._verify_single(REF).verdict == Verdict.VERIFIED

    def test_all_404_is_still_dead_doi(self, mock_set, mock_get):
        v = _verifier()
        for c in (v.crossref, v.datacite, v.openalex):
            c.fetch_by_doi.return_value = None
        assert v._verify_single(REF).verdict == Verdict.DEAD_DOI


class TestClientRaises:
    def test_network_error_raises(self):
        import requests
        c = CrossrefClient()
        c.session = MagicMock()
        c.session.get.side_effect = requests.exceptions.ConnectionError("down")
        with patch("citation_verifier.api_clients.time.sleep"):
            with pytest.raises(ApiUnavailable):
                c.fetch_by_doi("10.1000/xyz")

    def test_404_returns_none(self):
        c = CrossrefClient()
        c.session = MagicMock()
        c.session.get.return_value = MagicMock(status_code=404)
        with patch("citation_verifier.api_clients.time.sleep"):
            assert c.fetch_by_doi("10.1000/xyz") is None


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "_DB_PATH", tmp_path / "history.db")
    monkeypatch.setattr(history, "_local", __import__("threading").local())
    import webapp
    webapp.app.config["TESTING"] = True
    webapp.limiter.enabled = False
    return webapp.app


def _save(owner, text="ref"):
    return history.save_session(1, {"VERIFIED": 1}, False, text, {"results": []}, owner)


class TestHistoryIsolation:
    def test_owner_scoping(self, client):
        a, b = "a" * 32, "b" * 32
        sid = _save(a)
        assert [s["id"] for s in history.list_sessions(a)] == [sid]
        assert history.list_sessions(b) == []
        assert history.get_session(sid, b) is None
        assert history.get_session(sid, a) is not None

    def test_cannot_delete_or_clear_others(self, client):
        a, b = "a" * 32, "b" * 32
        sid = _save(a)
        history.delete_session(sid, b)
        history.clear_all_sessions(b)
        assert history.get_session(sid, a) is not None
        history.clear_all_sessions(a)
        assert history.list_sessions(a) == []

    def test_legacy_rows_not_served(self, client):
        sid = _save("")
        assert history.list_sessions("a" * 32) == []
        assert history.get_session(sid, "a" * 32) is None

    def test_http_flow_sets_cookie_and_isolates(self, client):
        c1, c2 = client.test_client(), client.test_client()
        r = c1.get("/api/history")
        assert r.status_code == 200 and r.get_json() == []
        cookie = r.headers.get("Set-Cookie", "")
        assert "cg_sid=" in cookie and "HttpOnly" in cookie
        sid = c1.get_cookie("cg_sid").value
        _save(sid)
        assert len(c1.get("/api/history").get_json()) == 1
        assert c2.get("/api/history").get_json() == []
        hid = c1.get("/api/history").get_json()[0]["id"]
        assert c2.get(f"/api/history/{hid}").status_code == 404
        c2.delete("/api/history")
        assert len(c1.get("/api/history").get_json()) == 1

    def test_forged_cookie_rejected(self, client):
        c = client.test_client()
        c.set_cookie("cg_sid", "not-valid")
        r = c.get("/api/history")
        assert "cg_sid=" in r.headers.get("Set-Cookie", "")
