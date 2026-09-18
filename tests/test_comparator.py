"""
Tests for the fuzzy matching comparator module.

Covers scoring thresholds, verdict classification,
edge cases with empty/null inputs, and year matching.
"""

import pytest

from citation_verifier.comparator import (
    _get_best_cited_title,
    classify_score,
    compare,
)
from citation_verifier.config import (
    GroundTruth,
    ParsedReference,
    Verdict,
)


# ═══════════════════════════════════════════════════════════════
# Score Classification
# ═══════════════════════════════════════════════════════════════

class TestClassifyScore:
    """Tests for classify_score() threshold boundaries."""

    def test_verified_at_90(self):
        assert classify_score(90.0) == Verdict.VERIFIED

    def test_verified_at_100(self):
        assert classify_score(100.0) == Verdict.VERIFIED

    def test_verified_at_95(self):
        assert classify_score(95.0) == Verdict.VERIFIED

    def test_suspicious_at_89(self):
        assert classify_score(89.9) == Verdict.SUSPICIOUS

    def test_suspicious_at_70(self):
        assert classify_score(70.0) == Verdict.SUSPICIOUS

    def test_suspicious_at_75(self):
        assert classify_score(75.0) == Verdict.SUSPICIOUS

    def test_mismatch_at_69(self):
        assert classify_score(69.9) == Verdict.MISMATCH

    def test_mismatch_at_0(self):
        assert classify_score(0.0) == Verdict.MISMATCH

    def test_mismatch_at_50(self):
        assert classify_score(50.0) == Verdict.MISMATCH

    def test_boundary_exactly_90(self):
        """Exactly 90 should be VERIFIED (>=)."""
        assert classify_score(90.0) == Verdict.VERIFIED

    def test_boundary_exactly_70(self):
        """Exactly 70 should be SUSPICIOUS (>=)."""
        assert classify_score(70.0) == Verdict.SUSPICIOUS


# ═══════════════════════════════════════════════════════════════
# Full Comparison
# ═══════════════════════════════════════════════════════════════

class TestCompare:
    """Tests for the compare() function."""

    def test_exact_match(self, parsed_ref_with_doi, ground_truth_attention):
        """Exact title match should produce VERIFIED."""
        result = compare(parsed_ref_with_doi, ground_truth_attention)
        assert result.verdict == Verdict.VERIFIED
        assert result.final_score >= 90

    def test_scores_populated(self, parsed_ref_with_doi, ground_truth_attention):
        """All three scores should be populated."""
        result = compare(parsed_ref_with_doi, ground_truth_attention)
        assert result.ratio_score > 0
        assert result.token_sort_score > 0
        assert result.token_set_score > 0

    def test_year_match_true(self, parsed_ref_with_doi, ground_truth_attention):
        """Matching years should set year_match=True."""
        result = compare(parsed_ref_with_doi, ground_truth_attention)
        assert result.year_match is True

    def test_year_match_false(self, ground_truth_attention):
        """Different years should set year_match=False."""
        ref = ParsedReference(
            raw_text="test",
            candidate_title="Attention is all you need",
            year=2020,  # Wrong year
        )
        result = compare(ref, ground_truth_attention)
        assert result.year_match is False

    def test_year_match_none_when_missing(self, ground_truth_attention):
        """Missing year should leave year_match=None."""
        ref = ParsedReference(
            raw_text="test",
            candidate_title="Attention is all you need",
            year=None,
        )
        result = compare(ref, ground_truth_attention)
        assert result.year_match is None

    def test_completely_different_title(self, ground_truth_attention):
        """Totally different title should be MISMATCH."""
        ref = ParsedReference(
            raw_text="test",
            candidate_title="A completely unrelated paper about marine biology",
            year=2017,
        )
        result = compare(ref, ground_truth_attention)
        assert result.verdict == Verdict.MISMATCH
        assert result.final_score < 70

    def test_similar_but_not_exact(self, ground_truth_attention):
        """Minor title variation should be VERIFIED or SUSPICIOUS."""
        ref = ParsedReference(
            raw_text="test",
            candidate_title="Attention Is All You Need: Self-Attention Mechanisms",
            year=2017,
        )
        result = compare(ref, ground_truth_attention)
        assert result.verdict in (Verdict.VERIFIED, Verdict.SUSPICIOUS)

    def test_empty_cited_title(self, ground_truth_attention):
        """Empty cited title should return SUSPICIOUS."""
        ref = ParsedReference(raw_text="x" * 5, candidate_title=None)
        result = compare(ref, ground_truth_attention)
        assert result.verdict == Verdict.SUSPICIOUS

    def test_empty_ground_truth_title(self, parsed_ref_with_doi):
        """Empty ground truth title should return SUSPICIOUS."""
        gt = GroundTruth(title=None, api_source="test")
        result = compare(parsed_ref_with_doi, gt)
        assert result.verdict == Verdict.SUSPICIOUS

    def test_final_score_is_max(self, parsed_ref_with_doi, ground_truth_attention):
        """Final score should be the max of all three individual scores."""
        result = compare(parsed_ref_with_doi, ground_truth_attention)
        assert result.final_score == max(
            result.ratio_score,
            result.token_sort_score,
            result.token_set_score,
        )


# ═══════════════════════════════════════════════════════════════
# Title Extraction Fallback
# ═══════════════════════════════════════════════════════════════

class TestGetBestCitedTitle:
    """Tests for _get_best_cited_title() fallback logic."""

    def test_uses_candidate_title(self):
        ref = ParsedReference(
            raw_text="Some raw text here",
            candidate_title="My Paper Title",
        )
        assert _get_best_cited_title(ref) == "My Paper Title"

    def test_falls_back_to_raw(self):
        """When no candidate_title, should clean and return raw text."""
        ref = ParsedReference(
            raw_text="This is a long enough raw text to be used as title",
            candidate_title=None,
        )
        result = _get_best_cited_title(ref)
        assert result is not None
        assert len(result) > 15

    def test_short_raw_returns_none(self):
        """Very short raw text should return None."""
        ref = ParsedReference(raw_text="short", candidate_title=None)
        assert _get_best_cited_title(ref) is None

    def test_raw_urls_removed(self):
        """URLs in raw text fallback should be stripped."""
        ref = ParsedReference(
            raw_text="Title of paper here https://example.com/something with more text",
            candidate_title=None,
        )
        result = _get_best_cited_title(ref)
        assert "https://" not in result
