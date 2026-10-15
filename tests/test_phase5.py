"""First-author rule, records without author data, and multi-candidate title search."""

from unittest.mock import MagicMock

import pytest

from citation_verifier.comparator import (
    _cited_first_surname,
    authors_overlap,
    compare,
    confirm_title_only_match,
)
from citation_verifier.config import GroundTruth, ParsedReference, Verdict
from citation_verifier.verifier import CitationVerifier

TITLE = "Transcriptomic profiling reveals mechanism and prognostic value in carcinoma"


def _ref(authors, title=TITLE, year=2025):
    return ParsedReference(raw_text="x", candidate_title=title, authors_raw=authors, year=year)


def _gt(authors, title=TITLE, year=2025):
    return GroundTruth(doi="10.1/x", title=title, authors=authors, year=year, api_source="Crossref")


def _confirm(ref, gt):
    return confirm_title_only_match(ref, gt, compare(ref, gt))


class TestCitedFirstSurname:
    @pytest.mark.parametrize("raw,expected", [
        ("Hobbs, N. T., Hooten, M. B.", "hobbs"),
        ("Hobbs, N", "hobbs"),
        ("N. Thompson Hobbs and Mevin B. Hooten", "hobbs"),
        ("Hobbs NT, Hooten MB", "hobbs"),
        ("HOBBS, N.T.", "hobbs"),
        ("Kaiming He, Xiangyu Zhang", "he"),
        ("Villalva, M.G., Gazoli, J.R., Filho, E.R", "villalva"),
        ("", None),
    ])
    def test_formats(self, raw, expected):
        assert _cited_first_surname(raw) == expected


class TestFirstAuthorRule:
    def test_common_surname_later_in_real_list_does_not_validate(self):
        """Benchmark false accept: invented first author, 'Chen' coincides with a real one."""
        gt = _gt(["Jin-Wei Chen", "Run-Nan Shen", "Jiang-Quan Zhu"])
        assert authors_overlap(_ref("Lindqvist, H., Chen, H."), gt) is False
        assert not _confirm(_ref("Lindqvist, H., Chen, H."), gt)[0]

    def test_real_first_author_confirms(self):
        gt = _gt(["Jin-Wei Chen", "Run-Nan Shen"])
        assert _confirm(_ref("Chen, J., Shen, R."), gt)[0]

    def test_first_author_may_be_later_in_record_order(self):
        # record lists authors in a different order than the citation
        gt = _gt(["Run-Nan Shen", "Jin-Wei Chen"])
        assert authors_overlap(_ref("Chen, J., Shen, R."), gt) is True


class TestRecordWithoutAuthorData:
    def test_citation_with_authors_is_not_confirmed_by_title_alone(self):
        """Benchmark false accept: record had no authors, so invented authors went unchecked."""
        ok, reason = _confirm(_ref("Moreau, D., Santos, T."), _gt([]))
        assert not ok and "no author data" in reason

    def test_citation_without_authors_still_needs_near_exact_title(self):
        assert _confirm(_ref(None), _gt([]))[0]


class TestMultipleCandidates:
    TITLE = "Occlusal fissures in equine cheek teeth"

    def _verifier(self, openalex, crossref):
        v = CitationVerifier(cross_validate=False)
        v.openalex, v.crossref = MagicMock(), MagicMock()
        v.openalex.search_candidates.return_value = openalex
        v.crossref.search_candidates.return_value = crossref
        return v

    TEXT = "Pollaris, E., Staszyk, C. (2020). Occlusal fissures in equine cheek teeth. J Vet Dent."

    def _gt(self, title, authors, year):
        return GroundTruth(doi="10.1/y", title=title, authors=authors, year=year, api_source="X")

    def test_confirmed_candidate_beyond_first_is_used(self):
        wrong = self._gt("Occlusal fissures in horses", ["A. Other"], 2011)
        right = self._gt("Occlusal fissures in equine cheek teeth", ["E. Pollaris", "C. Staszyk"], 2020)
        out = self._verifier([wrong, right], []).verify_text(self.TEXT)[0]
        assert out.verdict == Verdict.TITLE_MATCHED
        assert out.ground_truth is right

    def test_crossref_consulted_when_openalex_has_no_confirmed_candidate(self):
        wrong = self._gt("Occlusal fissures in horses", ["A. Other"], 2011)
        right = self._gt("Occlusal fissures in equine cheek teeth", ["E. Pollaris"], 2020)
        v = self._verifier([wrong], [right])
        assert v.verify_text(self.TEXT)[0].verdict == Verdict.TITLE_MATCHED
        v.crossref.search_candidates.assert_called_once()

    def test_nothing_confirmed_reports_best_rejected_candidate(self):
        wrong = self._gt("Occlusal fissures in equine cheek teeth", ["A. Other"], 2020)
        out = self._verifier([wrong], []).verify_text(self.TEXT)[0]
        assert out.verdict == Verdict.NO_DOI
        assert "could not be confirmed" in out.error_message
        assert out.ground_truth is wrong

    def test_no_results_at_all(self):
        out = self._verifier([], []).verify_text(self.TEXT)[0]
        assert out.verdict == Verdict.NO_DOI
        assert "no results" in out.error_message
