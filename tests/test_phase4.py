"""Title-only (no DOI) matches must be backed by authors/year, not title alone."""

from unittest.mock import MagicMock

import pytest

from citation_verifier.comparator import (
    authors_overlap,
    compare,
    confirm_title_only_match,
)
from citation_verifier.config import GroundTruth, ParsedReference, Verdict
from citation_verifier.verifier import CitationVerifier


def _ref(title, authors, year):
    return ParsedReference(raw_text="x", candidate_title=title, authors_raw=authors, year=year)


def _gt(title, authors, year):
    return GroundTruth(doi="10.1/x", title=title, authors=authors, year=year, api_source="Crossref")


def _confirm(ref, gt):
    return confirm_title_only_match(ref, gt, compare(ref, gt))


class TestAuthorsOverlap:
    @pytest.mark.parametrize("cited", [
        "Hobbs, N. T., Hooten, M. B.",
        "N. Thompson Hobbs and Mevin B. Hooten",
        "Hobbs NT, Hooten MB",
        "HOBBS, N.T.",
    ])
    def test_formats(self, cited):
        gt = _gt("t", ["N. Thompson Hobbs", "Mevin B. Hooten"], 2015)
        assert authors_overlap(_ref("t", cited, 2015), gt) is True

    def test_disjoint(self):
        gt = _gt("t", ["N. Thompson Hobbs"], 2015)
        assert authors_overlap(_ref("t", "Nowak, K., Ivanova, P.", 2015), gt) is False

    def test_unknown_when_missing(self):
        assert authors_overlap(_ref("t", None, 2015), _gt("t", ["A B"], 2015)) is None
        assert authors_overlap(_ref("t", "Doe, J.", 2015), _gt("t", [], 2015)) is None

    def test_initials_do_not_count_as_surnames(self):
        gt = _gt("t", ["Jane K Smith"], 2015)
        assert authors_overlap(_ref("t", "Doe, K., Lee, P.", 2015), gt) is False


class TestConfirmTitleOnlyMatch:
    TITLE = "Deep residual learning for image recognition"

    def test_exact_title_and_author_confirmed(self):
        ok, _ = _confirm(_ref(self.TITLE, "He, K., Zhang, X.", 2016),
                         _gt(self.TITLE, ["Kaiming He", "Xiangyu Zhang"], 2016))
        assert ok

    def test_regression_subset_title_with_unrelated_authors_rejected(self):
        """The benchmark's false accept: invented title vs 'Hierarchical Bayesian Models'."""
        ref = _ref("Bayesian gradients and hierarchical regimes in distributed tensors",
                   "Nowak, K., Ivanova, P.", 2015)
        gt = _gt("Hierarchical Bayesian Models", ["N. Thompson Hobbs", "Mevin B. Hooten"], 2015)
        ok, reason = _confirm(ref, gt)
        assert not ok and reason

    def test_same_title_different_authors_rejected(self):
        ok, reason = _confirm(_ref(self.TITLE, "Nowak, K.", 2016),
                              _gt(self.TITLE, ["Kaiming He"], 2016))
        assert not ok and "authors" in reason

    def test_year_gap_rejected_but_one_year_tolerated(self):
        gt = _gt(self.TITLE, ["Kaiming He"], 2016)
        assert not _confirm(_ref(self.TITLE, "He, K.", 2010), gt)[0]
        assert _confirm(_ref(self.TITLE, "He, K.", 2015), gt)[0]

    def test_no_authors_needs_near_exact_title(self):
        gt = _gt(self.TITLE, ["Kaiming He"], 2016)
        assert _confirm(_ref(self.TITLE, None, 2016), gt)[0]
        close = "Deep residual learning for image recognition tasks in practice"
        assert not _confirm(_ref(close, None, 2016), gt)[0]


class TestVerifierUsesConfirmation:
    def _verifier(self, gt):
        v = CitationVerifier(cross_validate=False)
        v.openalex, v.crossref = MagicMock(), MagicMock()
        v.openalex.search_candidates.return_value = [gt]
        return v

    def test_unconfirmed_candidate_is_no_doi(self):
        gt = _gt("Hierarchical Bayesian Models", ["N. Thompson Hobbs"], 2015)
        v = self._verifier(gt)
        out = v.verify_text(
            "Nowak, K., Ivanova, P. (2015). Bayesian gradients and hierarchical "
            "regimes in distributed tensors. Journal of Imaginary Results.")
        assert out[0].verdict == Verdict.NO_DOI
        assert "could not be confirmed" in out[0].error_message

    def test_confirmed_candidate_is_title_matched(self):
        t = "Deep residual learning for image recognition"
        v = self._verifier(_gt(t, ["Kaiming He", "Xiangyu Zhang"], 2016))
        out = v.verify_text(f"He, K., Zhang, X. (2016). {t}. CVPR.")
        assert out[0].verdict == Verdict.TITLE_MATCHED


class TestRealWorldVariants:
    TITLE = "Prevalence of post-micturition dribble in Japanese men and its relationship"

    def test_online_first_vs_print_year_tolerated_when_authors_agree(self):
        ref = _ref(self.TITLE, "Kobayashi, K., Fukuta, F.", 2017)
        gt = _gt(self.TITLE, ["Ko Kobayashi", "Fumimasa Fukuta"], 2019)
        assert _confirm(ref, gt)[0]

    def test_big_year_gap_still_rejected_without_author_support(self):
        ref = _ref(self.TITLE, None, 2010)
        assert not _confirm(ref, _gt(self.TITLE, ["Ko Kobayashi"], 2019))[0]
        assert not _confirm(_ref(self.TITLE, "Kobayashi, K.", 2000),
                            _gt(self.TITLE, ["Ko Kobayashi"], 2019))[0]

    def test_dropped_subtitle_accepted_with_author_and_year(self):
        short = "A la conquête du pouvoir"
        long_ = "A la conquête du pouvoir. Comment une tendance devient majoritaire"
        ref = _ref(short, "Boily, F", 2026)
        assert _confirm(ref, _gt(long_, ["Frédéric Boily"], 2026))[0]

    def test_dropped_subtitle_rejected_without_author_agreement(self):
        short = "A la conquête du pouvoir"
        long_ = "A la conquête du pouvoir. Comment une tendance devient majoritaire"
        assert not _confirm(_ref(short, "Nowak, K", 2026), _gt(long_, ["Frédéric Boily"], 2026))[0]
        assert not _confirm(_ref(short, "Boily, F", 2010), _gt(long_, ["Frédéric Boily"], 2026))[0]

    def test_short_generic_title_subset_rejected(self):
        ref = _ref("Bayesian models in distributed tensors regimes", "Hobbs, N.", 2015)
        assert not _confirm(ref, _gt("Bayesian models", ["N. Thompson Hobbs"], 2015))[0]
