"""Regression tests found by the benchmark: DOI truncation and publisher markup."""

import pytest

from citation_verifier.normalizer import normalize_title, strip_markup
from citation_verifier.parser import parse_references


class TestSiciAndBracketDois:
    """DOIs containing ';' and '[...]' must not be truncated."""

    @pytest.mark.parametrize("doi", [
        "10.1675/1524-4695(2007)030[0573:DCSAOB]2.0.CO;2",
        "10.1002/(SICI)1097-4571(199806)49:8<693::AID-ASI4>3.0.CO;2-O",
        "10.1016/S0167-9236(02)00114-8",
    ])
    def test_keeps_full_doi(self, doi):
        ref = parse_references(
            f"Doe, J. (2007). A title here. Journal. https://doi.org/{doi}."
        )[0]
        assert ref.doi.lower() == doi.lower()

    @pytest.mark.parametrize("text", [
        "(doi: 10.1000/abc123)",
        "[see 10.1000/abc123]",
        "10.1000/abc123; next ref",
        "10.1000/abc123.",
        "10.1000/abc123,",
    ])
    def test_strips_surrounding_punctuation(self, text):
        ref = parse_references(f"Doe, J. (2007). A title here. Journal. {text}")[0]
        assert ref.doi == "10.1000/abc123"


class TestMarkup:
    def test_subscripts_collapse_like_typed_text(self):
        a = normalize_title("Flux pinning in YBa<sub>2</sub>Cu<sub>3</sub>O<sub>7</sub> films")
        assert a == normalize_title("Flux pinning in YBa2Cu3O7 films")

    def test_inline_tags_and_entities(self):
        assert normalize_title("Apology on behalf of the <i>CMAJ</i>") == "apology on behalf of the cmaj"
        assert strip_markup("Does <scp>D</scp>-galactosamine &amp; cells?") == "Does D-galactosamine & cells?"

    def test_plain_less_than_is_kept(self):
        assert strip_markup("Effect when p < 0.05 and q > 1") == "Effect when p < 0.05 and q > 1"


class TestRetryPolicyIsBounded:
    def test_no_unbounded_retry_after_sleep(self):
        from citation_verifier.api_clients import _create_session
        retry = _create_session().get_adapter("https://api.openalex.org").max_retries
        assert retry.respect_retry_after_header is False
        assert 429 not in retry.status_forcelist
        assert retry.backoff_max <= 5


class TestUndatedCrossrefRecords:
    @pytest.mark.parametrize("data", [
        {"issued": {"date-parts": [[None]]}},
        {"published-print": None, "issued": {"date-parts": [[None]]}},
        {"published-print": {"date-parts": [[None]]}, "issued": {"date-parts": [[2019, 5]]}},
    ])
    def test_extract_year_never_raises(self, data):
        from citation_verifier.api_clients import CrossrefClient
        year = CrossrefClient._extract_year(data)
        assert year in (None, 2019)


class TestSmallBatchIsolation:
    def test_one_crashing_reference_does_not_fail_the_batch(self):
        from unittest.mock import MagicMock
        from citation_verifier.config import Verdict
        from citation_verifier.verifier import CitationVerifier
        v = CitationVerifier(cross_validate=False)
        v.crossref, v.datacite, v.openalex = MagicMock(), MagicMock(), MagicMock()
        v.crossref.fetch_by_doi.side_effect = TypeError("boom")
        v.datacite.fetch_by_doi.return_value = None
        v.openalex.fetch_by_doi.return_value = None
        out = v.verify_text("Doe, J. (2020). A title. J. https://doi.org/10.1000/a")
        assert len(out) == 1 and out[0].verdict == Verdict.API_ERROR
