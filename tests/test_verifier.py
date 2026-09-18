"""
Tests for the core verification orchestrator.

Uses mocked API clients to test the full verification pipeline
including cache, retraction detection, cross-validation, and
DOI routing logic.
"""

import pytest
from unittest.mock import MagicMock, patch

from citation_verifier.config import (
    GroundTruth,
    ParsedReference,
    Verdict,
    VerificationResult,
)
from citation_verifier.verifier import CitationVerifier


# ═══════════════════════════════════════════════════════════════
# DOI Routing
# ═══════════════════════════════════════════════════════════════

class TestDOIRouting:
    """Tests for route_doi_to_api()."""

    def test_arxiv_routes_to_datacite(self):
        from citation_verifier.api_clients import route_doi_to_api
        assert route_doi_to_api("10.48550/arXiv.1706.03762") == "DataCite"

    def test_regular_doi_routes_to_crossref(self):
        from citation_verifier.api_clients import route_doi_to_api
        assert route_doi_to_api("10.1145/3397271.3401075") == "Crossref"

    def test_case_insensitive_routing(self):
        from citation_verifier.api_clients import route_doi_to_api
        assert route_doi_to_api("10.48550/ARXIV.1706.03762") == "DataCite"


# ═══════════════════════════════════════════════════════════════
# Verifier with Mocked APIs
# ═══════════════════════════════════════════════════════════════

class TestVerifierWithDOI:
    """Tests for _verify_with_doi() using mocked API clients."""

    def _make_verifier(self):
        """Create a verifier with mocked API clients."""
        verifier = CitationVerifier(cross_validate=False)
        verifier.crossref = MagicMock()
        verifier.datacite = MagicMock()
        verifier.openalex = MagicMock()
        return verifier

    @patch("citation_verifier.verifier.get_cached", return_value=None)
    @patch("citation_verifier.verifier.set_cached")
    def test_verified_doi(self, mock_set, mock_get, parsed_ref_with_doi):
        """A matching DOI + title should produce VERIFIED."""
        verifier = self._make_verifier()
        # DOI 10.48550/arXiv.* routes to DataCite as primary
        verifier.datacite.fetch_by_doi.return_value = GroundTruth(
            doi="10.48550/arXiv.1706.03762",
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            year=2017,
            api_source="DataCite",
        )

        result = verifier._verify_single(parsed_ref_with_doi)
        assert result.verdict == Verdict.VERIFIED
        assert result.ground_truth is not None

    @patch("citation_verifier.verifier.get_cached", return_value=None)
    @patch("citation_verifier.verifier.set_cached")
    def test_dead_doi(self, mock_set, mock_get, parsed_ref_with_doi):
        """DOI not found in any API should produce DEAD_DOI."""
        verifier = self._make_verifier()
        verifier.crossref.fetch_by_doi.return_value = None
        verifier.datacite.fetch_by_doi.return_value = None
        verifier.openalex.fetch_by_doi.return_value = None

        result = verifier._verify_single(parsed_ref_with_doi)
        assert result.verdict == Verdict.DEAD_DOI
        assert "not found" in result.error_message

    @patch("citation_verifier.verifier.get_cached", return_value=None)
    @patch("citation_verifier.verifier.set_cached")
    def test_retracted_paper(self, mock_set, mock_get, parsed_ref_with_doi):
        """Retracted paper should produce RETRACTED verdict."""
        verifier = self._make_verifier()
        # DOI 10.48550/arXiv.* routes to DataCite as primary
        verifier.datacite.fetch_by_doi.return_value = GroundTruth(
            doi="10.48550/arXiv.1706.03762",
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            year=2017,
            api_source="DataCite",
            is_retracted=True,
        )

        result = verifier._verify_single(parsed_ref_with_doi)
        assert result.verdict == Verdict.RETRACTED
        assert "RETRACTED" in result.error_message

    @patch("citation_verifier.verifier.get_cached", return_value=None)
    @patch("citation_verifier.verifier.set_cached")
    def test_mismatch_doi(self, mock_set, mock_get, parsed_ref_with_doi):
        """DOI resolving to a different paper should produce MISMATCH."""
        verifier = self._make_verifier()
        # DOI 10.48550/arXiv.* routes to DataCite as primary
        verifier.datacite.fetch_by_doi.return_value = GroundTruth(
            doi="10.48550/arXiv.1706.03762",
            title="A Completely Different Paper About Marine Biology",
            authors=["Unknown Author"],
            year=2020,
            api_source="DataCite",
        )

        result = verifier._verify_single(parsed_ref_with_doi)
        assert result.verdict == Verdict.MISMATCH

    @patch("citation_verifier.verifier.get_cached")
    def test_cache_hit(self, mock_get, parsed_ref_with_doi):
        """Cache hit should skip API calls entirely."""
        cached_gt = GroundTruth(
            doi="10.48550/arXiv.1706.03762",
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            year=2017,
            api_source="Crossref (cached)",
        )
        mock_get.return_value = cached_gt

        verifier = self._make_verifier()
        result = verifier._verify_single(parsed_ref_with_doi)

        assert result.verdict == Verdict.VERIFIED
        # API clients should NOT have been called
        verifier.crossref.fetch_by_doi.assert_not_called()
        verifier.datacite.fetch_by_doi.assert_not_called()

    @patch("citation_verifier.verifier.get_cached", return_value=None)
    @patch("citation_verifier.verifier.set_cached")
    def test_fallback_to_datacite(self, mock_set, mock_get, parsed_ref_with_doi):
        """When Crossref fails, should fallback to DataCite."""
        verifier = self._make_verifier()
        verifier.crossref.fetch_by_doi.return_value = None
        verifier.datacite.fetch_by_doi.return_value = GroundTruth(
            doi="10.48550/arXiv.1706.03762",
            title="Attention Is All You Need",
            api_source="DataCite",
        )

        result = verifier._verify_single(parsed_ref_with_doi)
        assert result.verdict == Verdict.VERIFIED
        assert result.ground_truth.api_source == "DataCite"

    @patch("citation_verifier.verifier.get_cached", return_value=None)
    @patch("citation_verifier.verifier.set_cached")
    def test_fallback_to_openalex(self, mock_set, mock_get, parsed_ref_with_doi):
        """When Crossref + DataCite fail, should fallback to OpenAlex."""
        verifier = self._make_verifier()
        verifier.crossref.fetch_by_doi.return_value = None
        verifier.datacite.fetch_by_doi.return_value = None
        verifier.openalex.fetch_by_doi.return_value = GroundTruth(
            doi="10.48550/arXiv.1706.03762",
            title="Attention Is All You Need",
            api_source="OpenAlex",
        )

        result = verifier._verify_single(parsed_ref_with_doi)
        assert result.verdict == Verdict.VERIFIED
        assert result.ground_truth.api_source == "OpenAlex"


# ═══════════════════════════════════════════════════════════════
# Verifier Without DOI
# ═══════════════════════════════════════════════════════════════

class TestVerifierWithoutDOI:
    """Tests for _verify_without_doi() title search."""

    def _make_verifier(self):
        verifier = CitationVerifier(cross_validate=False)
        verifier.crossref = MagicMock()
        verifier.datacite = MagicMock()
        verifier.openalex = MagicMock()
        return verifier

    def test_title_found_high_score(self, parsed_ref_no_doi):
        """High-confidence title match should produce TITLE_MATCHED."""
        verifier = self._make_verifier()
        verifier.openalex.search_by_title.return_value = GroundTruth(
            doi="10.48550/arXiv.1706.03762",
            title="Attention Is All You Need",
            api_source="OpenAlex",
        )

        result = verifier._verify_single(parsed_ref_no_doi)
        assert result.verdict == Verdict.TITLE_MATCHED

    def test_title_found_low_score(self, parsed_ref_no_doi):
        """Low-confidence title match should remain NO_DOI."""
        verifier = self._make_verifier()
        verifier.openalex.search_by_title.return_value = GroundTruth(
            doi="10.9999/different",
            title="A Completely Different Marine Biology Paper",
            api_source="OpenAlex",
        )

        result = verifier._verify_single(parsed_ref_no_doi)
        assert result.verdict == Verdict.NO_DOI

    def test_no_title_no_doi(self):
        """Reference without DOI or title should produce NO_DOI."""
        ref = ParsedReference(raw_text="x" * 20, candidate_title=None)
        verifier = self._make_verifier()

        result = verifier._verify_single(ref)
        assert result.verdict == Verdict.NO_DOI

    def test_title_search_fallback_to_crossref(self, parsed_ref_no_doi):
        """When OpenAlex title search fails, should try Crossref."""
        verifier = self._make_verifier()
        verifier.openalex.search_by_title.return_value = None
        verifier.crossref.search_by_title.return_value = GroundTruth(
            doi="10.48550/arXiv.1706.03762",
            title="Attention Is All You Need",
            api_source="Crossref",
        )

        result = verifier._verify_single(parsed_ref_no_doi)
        assert result.verdict == Verdict.TITLE_MATCHED


# ═══════════════════════════════════════════════════════════════
# Cross-Validation
# ═══════════════════════════════════════════════════════════════

class TestCrossValidation:
    """Tests for _cross_validate_with_openalex()."""

    def _make_verifier(self, cross_validate=True):
        verifier = CitationVerifier(cross_validate=cross_validate)
        verifier.crossref = MagicMock()
        verifier.datacite = MagicMock()
        verifier.openalex = MagicMock()
        return verifier

    def test_cross_validation_confirms(self, parsed_ref_with_doi):
        """Matching OpenAlex title should set cross_validated=True."""
        verifier = self._make_verifier()

        result = VerificationResult(
            reference=parsed_ref_with_doi,
            verdict=Verdict.VERIFIED,
            ground_truth=GroundTruth(
                title="Attention Is All You Need",
                api_source="Crossref",
            ),
        )

        verifier.openalex.fetch_by_doi.return_value = GroundTruth(
            title="Attention Is All You Need",
            api_source="OpenAlex",
        )

        result = verifier._cross_validate_with_openalex(parsed_ref_with_doi, result)
        assert result.cross_validated is True

    def test_cross_validation_conflict(self, parsed_ref_with_doi):
        """Conflicting OpenAlex title should downgrade VERIFIED → SUSPICIOUS."""
        verifier = self._make_verifier()

        result = VerificationResult(
            reference=parsed_ref_with_doi,
            verdict=Verdict.VERIFIED,
            ground_truth=GroundTruth(
                title="Attention Is All You Need",
                api_source="Crossref",
            ),
        )

        verifier.openalex.fetch_by_doi.return_value = GroundTruth(
            title="A Totally Different Paper Title Here",
            api_source="OpenAlex",
        )

        result = verifier._cross_validate_with_openalex(parsed_ref_with_doi, result)
        assert result.verdict == Verdict.SUSPICIOUS

    def test_cross_validation_retraction_detected(self, parsed_ref_with_doi):
        """OpenAlex retraction flag should override to RETRACTED."""
        verifier = self._make_verifier()

        result = VerificationResult(
            reference=parsed_ref_with_doi,
            verdict=Verdict.VERIFIED,
            ground_truth=GroundTruth(
                title="Attention Is All You Need",
                api_source="Crossref",
                is_retracted=False,
            ),
        )

        verifier.openalex.fetch_by_doi.return_value = GroundTruth(
            title="Attention Is All You Need",
            api_source="OpenAlex",
            is_retracted=True,
        )

        result = verifier._cross_validate_with_openalex(parsed_ref_with_doi, result)
        assert result.verdict == Verdict.RETRACTED
        assert result.ground_truth.is_retracted is True

    def test_cross_validation_skipped_without_doi(self):
        """References without DOI should skip cross-validation."""
        verifier = self._make_verifier()
        ref = ParsedReference(raw_text="test", doi=None)
        result = VerificationResult(reference=ref, verdict=Verdict.VERIFIED)

        updated = verifier._cross_validate_with_openalex(ref, result)
        assert updated.verdict == Verdict.VERIFIED
        verifier.openalex.fetch_by_doi.assert_not_called()

    def test_cross_validation_openalex_error(self, parsed_ref_with_doi):
        """OpenAlex error should not change the result."""
        verifier = self._make_verifier()
        verifier.openalex.fetch_by_doi.side_effect = Exception("Network error")

        result = VerificationResult(
            reference=parsed_ref_with_doi,
            verdict=Verdict.VERIFIED,
            ground_truth=GroundTruth(
                title="Attention Is All You Need",
                api_source="Crossref",
            ),
        )

        updated = verifier._cross_validate_with_openalex(parsed_ref_with_doi, result)
        assert updated.verdict == Verdict.VERIFIED


# ═══════════════════════════════════════════════════════════════
# Verify Text (integration with parser)
# ═══════════════════════════════════════════════════════════════

class TestVerifyText:
    """Integration tests for verify_text()."""

    def test_empty_text_returns_empty(self):
        verifier = CitationVerifier(cross_validate=False)
        assert verifier.verify_text("") == []

    def test_result_count_matches_references(self):
        """Each parsed reference should produce exactly one result."""
        verifier = CitationVerifier(cross_validate=False)
        verifier.crossref = MagicMock()
        verifier.datacite = MagicMock()
        verifier.openalex = MagicMock()

        # All APIs return None → DEAD_DOI or NO_DOI
        verifier.crossref.fetch_by_doi.return_value = None
        verifier.datacite.fetch_by_doi.return_value = None
        verifier.openalex.fetch_by_doi.return_value = None
        verifier.openalex.search_by_title.return_value = None
        verifier.crossref.search_by_title.return_value = None

        text = "[1]. Author A (2020). Title A. doi:10.1234/a\n[2]. Author B (2021). Title B. doi:10.1234/b"

        with patch("citation_verifier.verifier.get_cached", return_value=None), \
             patch("citation_verifier.verifier.set_cached"):
            results = verifier.verify_text(text)

        assert len(results) == 2
