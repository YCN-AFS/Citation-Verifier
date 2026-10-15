"""Title-search failures must surface as API_ERROR; successful searches are cached."""

from unittest.mock import MagicMock

import pytest
import requests

from citation_verifier import cache
from citation_verifier.api_clients import ApiUnavailable, CrossrefClient, OpenAlexClient
from citation_verifier.config import GroundTruth, Verdict
from citation_verifier.verifier import CitationVerifier

TEXT = "Pollaris, E., Staszyk, C. (2020). Occlusal fissures in equine cheek teeth. J Vet Dent."
GOOD = GroundTruth(doi="10.1/y", title="Occlusal fissures in equine cheek teeth",
                   authors=["E. Pollaris", "C. Staszyk"], year=2020, api_source="OpenAlex")
OTHER = GroundTruth(doi="10.1/z", title="Occlusal fissures in horses",
                    authors=["A. Other"], year=2011, api_source="Crossref")


def _verifier(openalex, crossref):
    v = CitationVerifier(cross_validate=False)
    v.openalex, v.crossref = MagicMock(), MagicMock()
    for client, result in ((v.openalex, openalex), (v.crossref, crossref)):
        if isinstance(result, Exception):
            client.search_candidates.side_effect = result
        else:
            client.search_candidates.return_value = result
    return v


class TestSearchErrorsAreNotNoDoi:
    def test_both_sources_down(self):
        v = _verifier(ApiUnavailable("429"), ApiUnavailable("429"))
        out = v.verify_text(TEXT)[0]
        assert out.verdict == Verdict.API_ERROR and "retry" in out.error_message.lower()

    def test_one_source_down_and_other_finds_nothing(self):
        v = _verifier(ApiUnavailable("429"), [])
        assert v.verify_text(TEXT)[0].verdict == Verdict.API_ERROR

    def test_one_source_down_but_other_confirms(self):
        v = _verifier(ApiUnavailable("429"), [GOOD])
        assert v.verify_text(TEXT)[0].verdict == Verdict.TITLE_MATCHED

    def test_one_source_down_with_only_rejected_candidate_is_api_error(self):
        # the unreachable source might have held the real paper
        v = _verifier(ApiUnavailable("429"), [OTHER])
        assert v.verify_text(TEXT)[0].verdict == Verdict.API_ERROR

    def test_healthy_empty_search_is_still_no_doi(self):
        assert _verifier([], []).verify_text(TEXT)[0].verdict == Verdict.NO_DOI

    def test_failed_search_is_not_cached(self):
        v = _verifier(ApiUnavailable("429"), ApiUnavailable("429"))
        v.verify_text(TEXT)
        v2 = _verifier([GOOD], [])
        assert v2.verify_text(TEXT)[0].verdict == Verdict.TITLE_MATCHED
        v2.openalex.search_candidates.assert_called_once()


class TestTitleSearchCache:
    def test_second_lookup_skips_the_apis(self):
        v = _verifier([GOOD], [])
        assert v.verify_text(TEXT)[0].verdict == Verdict.TITLE_MATCHED
        v2 = _verifier([], [])
        out = v2.verify_text(TEXT)[0]
        assert out.verdict == Verdict.TITLE_MATCHED
        v2.openalex.search_candidates.assert_not_called()

    def test_empty_result_is_cached_too(self):
        _verifier([], []).verify_text(TEXT)
        v2 = _verifier([GOOD], [GOOD])
        assert v2.verify_text(TEXT)[0].verdict == Verdict.NO_DOI
        v2.openalex.search_candidates.assert_not_called()
        v2.crossref.search_candidates.assert_not_called()

    def test_roundtrip_preserves_fields(self):
        cache.set_title_candidates("OpenAlex", "some title", [GOOD, OTHER])
        got = cache.get_title_candidates("OpenAlex", "some title")
        assert got == [GOOD, OTHER]
        assert cache.get_title_candidates("Crossref", "some title") is None

    def test_expiry(self):
        from unittest.mock import patch
        import time
        cache.set_title_candidates("OpenAlex", "t", [GOOD])
        with patch("citation_verifier.cache.time.time", return_value=time.time() + 90000):
            assert cache.get_title_candidates("OpenAlex", "t") is None


class TestClientsRaise:
    @pytest.mark.parametrize("cls", [CrossrefClient, OpenAlexClient])
    def test_search_candidates_raises_on_network_error(self, cls):
        c = cls()
        c.session = MagicMock()
        c.session.get.side_effect = requests.exceptions.ConnectionError("down")
        with pytest.raises(ApiUnavailable):
            c.search_candidates("some title")

    @pytest.mark.parametrize("cls", [CrossrefClient, OpenAlexClient])
    def test_legacy_search_by_title_still_returns_none(self, cls):
        c = cls()
        c.session = MagicMock()
        c.session.get.side_effect = requests.exceptions.ConnectionError("down")
        assert c.search_by_title("some title") is None
