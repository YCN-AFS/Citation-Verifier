"""Tests for phase 2: async jobs, progress, throttle, negative cache."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from citation_verifier import cache, jobs
from citation_verifier.api_clients import ApiUnavailable, _Throttle
from citation_verifier.config import GroundTruth, ParsedReference, Verdict
from citation_verifier.verifier import CitationVerifier


# ─── Negative cache ──────────────────────────────────────────

def _verifier():
    v = CitationVerifier(cross_validate=False)
    v.crossref, v.datacite, v.openalex = MagicMock(), MagicMock(), MagicMock()
    return v


REF = ParsedReference(raw_text="x", doi="10.1000/missing", candidate_title="t")


class TestNegativeCache:
    def test_dead_doi_is_remembered(self):
        v = _verifier()
        for c in (v.crossref, v.datacite, v.openalex):
            c.fetch_by_doi.return_value = None
        assert v._verify_single(REF).verdict == Verdict.DEAD_DOI
        assert cache.is_known_missing(REF.doi)

        v2 = _verifier()
        assert v2._verify_single(REF).verdict == Verdict.DEAD_DOI
        v2.crossref.fetch_by_doi.assert_not_called()

    def test_transient_failure_is_not_remembered(self):
        v = _verifier()
        for c in (v.crossref, v.datacite, v.openalex):
            c.fetch_by_doi.side_effect = ApiUnavailable("down")
        assert v._verify_single(REF).verdict == Verdict.API_ERROR
        assert not cache.is_known_missing(REF.doi)

    def test_negative_entry_expires(self):
        cache.set_missing("10.1000/old")
        with patch("citation_verifier.cache.time.time", return_value=time.time() + 7200):
            assert not cache.is_known_missing("10.1000/old")


# ─── Throttle ────────────────────────────────────────────────

class TestThrottle:
    def test_spacing_holds_across_threads(self):
        t = _Throttle(0.05)
        stamps = []

        def hit():
            t.wait()
            stamps.append(time.monotonic())

        threads = [threading.Thread(target=hit) for _ in range(5)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        stamps.sort()
        gaps = [b - a for a, b in zip(stamps, stamps[1:])]
        assert min(gaps) >= 0.04


# ─── Progress callback ───────────────────────────────────────

class TestProgress:
    def _text(self, n):
        return "\n".join(
            f"Author, A. (2020). Title number {i}. Journal. https://doi.org/10.1000/p{i}"
            for i in range(n)
        )

    @pytest.mark.parametrize("n", [2, 8])
    def test_reports_each_reference(self, n):
        v = _verifier()
        for c in (v.crossref, v.datacite, v.openalex):
            c.fetch_by_doi.return_value = None
        calls = []
        v.verify_text(self._text(n), progress_cb=lambda d, t: calls.append((d, t)))
        assert calls[0] == (0, n)
        assert calls[-1] == (n, n)
        assert [d for d, _ in calls] == sorted(d for d, _ in calls)

    def test_broken_callback_does_not_break_verification(self):
        v = _verifier()
        for c in (v.crossref, v.datacite, v.openalex):
            c.fetch_by_doi.return_value = None

        def boom(d, t):
            raise RuntimeError("x")

        assert len(v.verify_text(self._text(2), progress_cb=boom)) == 2


# ─── Job store ───────────────────────────────────────────────

class TestJobStore:
    def test_lifecycle_and_owner_scoping(self):
        jid = jobs.create_job("a" * 32)
        jobs.update_progress(jid, 1, 4)
        j = jobs.get_job(jid, "a" * 32)
        assert (j["status"], j["done"], j["total"]) == ("running", 1, 4)
        assert jobs.get_job(jid, "b" * 32) is None
        jobs.finish(jid, {"total": 4})
        j = jobs.get_job(jid, "a" * 32)
        assert j["status"] == "done" and j["result"] == {"total": 4} and j["done"] == 4

    def test_stale_running_job_is_failed(self):
        jid = jobs.create_job("a" * 32)
        with patch("citation_verifier.jobs.time.time", return_value=time.time() + jobs.STALE_AFTER + 5):
            j = jobs.get_job(jid, "a" * 32)
        assert j["status"] == "failed"

    def test_count_active(self):
        o = "c" * 32
        jobs.create_job(o)
        jobs.create_job(o)
        jid = jobs.create_job(o)
        jobs.fail(jid, "x")
        assert jobs.count_active(o) == 2


# ─── HTTP flow ───────────────────────────────────────────────

@pytest.fixture
def app_client():
    import webapp
    webapp.app.config["TESTING"] = True
    webapp.limiter.enabled = False
    return webapp.app.test_client()


def _wait_done(c, jid, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = c.get(f"/api/jobs/{jid}").get_json()
        if j["status"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


class TestJobsHttp:
    TEXT = "Doe, J. (2020). Some title. Journal. https://doi.org/10.1000/abc"

    def test_end_to_end(self, app_client):
        gt = GroundTruth(doi="10.1000/abc", title="Some title", year=2020, api_source="Crossref")
        with patch("citation_verifier.verifier.CrossrefClient") as cr, \
                patch("citation_verifier.verifier.OpenAlexClient"), \
                patch("citation_verifier.verifier.DataCiteClient"):
            cr.return_value.fetch_by_doi.return_value = gt
            r = app_client.post("/api/jobs", json={"text": self.TEXT, "cross_validate": False})
            assert r.status_code == 202
            jid = r.get_json()["id"]
            j = _wait_done(app_client, jid)
        assert j["status"] == "done"
        assert j["result"]["total"] == 1
        assert j["result"]["results"][0]["verdict"] == "VERIFIED"
        # result also landed in this browser's history
        assert len(app_client.get("/api/history").get_json()) == 1

    def test_job_not_visible_to_other_browser(self, app_client):
        import webapp
        with patch("citation_verifier.verifier.CrossrefClient"), \
                patch("citation_verifier.verifier.OpenAlexClient"), \
                patch("citation_verifier.verifier.DataCiteClient"):
            jid = app_client.post("/api/jobs", json={"text": self.TEXT}).get_json()["id"]
            _wait_done(app_client, jid)  # finish while the mocks are active
        other = webapp.app.test_client()
        assert other.get(f"/api/jobs/{jid}").status_code == 404

    @pytest.mark.parametrize("body", [{}, {"text": "  "}, {"text": 5}])
    def test_validation(self, app_client, body):
        assert app_client.post("/api/jobs", json=body).status_code == 400

    def test_active_job_cap(self, app_client):
        c = app_client
        c.get("/api/history")  # obtain cookie
        owner = c.get_cookie("cg_sid").value
        jobs.create_job(owner)
        jobs.create_job(owner)
        assert c.post("/api/jobs", json={"text": self.TEXT}).status_code == 429
