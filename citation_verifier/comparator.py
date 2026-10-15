"""
Multi-scorer fuzzy matching engine for citation comparison.

Compares a cited reference against ground-truth metadata using three
complementary RapidFuzz scorers, producing a composite score and
deterministic verdict classification.

Enhanced with author surname comparison for higher accuracy.
"""

import logging
import re
from typing import Optional

from rapidfuzz import fuzz

from .config import (
    ComparisonResult,
    GroundTruth,
    ParsedReference,
    THRESHOLD_SUSPICIOUS,
    THRESHOLD_VERIFIED,
    Verdict,
)
from .normalizer import extract_surnames, normalize_author_name, normalize_title

logger = logging.getLogger(__name__)

# Author comparison parameters
_AUTHOR_BONUS = 5          # Score bonus when authors match
_AUTHOR_PENALTY_ZONE = 85  # Only apply author mismatch penalty below this score


def compare(
    reference: ParsedReference,
    ground_truth: GroundTruth,
) -> ComparisonResult:
    """
    Compare a parsed reference against ground-truth metadata.

    Uses three RapidFuzz scorers on the normalized title, then classifies
    the result using conservative thresholds designed for zero false-positive
    tolerance.

    Author comparison is used as a secondary signal:
        - If ≥50% of surnames match → bonus +5 to final score
        - If 0% match and title score is 70-85% → no bonus (stays SUSPICIOUS)

    Scoring strategy:
        - ratio:           Full edit-distance similarity
        - token_sort_ratio: Word-order-independent match
        - token_set_ratio:  Handles subset/superset titles

    The final score is the MAXIMUM of all three scorers, plus any
    author-based bonus.

    Args:
        reference:    Parsed reference from user input.
        ground_truth: Authoritative metadata from API.

    Returns:
        ComparisonResult with individual scores, final score, and verdict.
    """
    result = ComparisonResult()

    # ── Title Comparison ──────────────────────────────────────────────
    cited_title = _get_best_cited_title(reference)
    gt_title = ground_truth.title or ""

    if not cited_title or not gt_title:
        logger.warning(
            "Cannot compare: cited_title=%r, gt_title=%r",
            bool(cited_title), bool(gt_title),
        )
        result.verdict = Verdict.SUSPICIOUS
        return result

    # Normalize both titles
    norm_cited = normalize_title(cited_title)
    norm_gt = normalize_title(gt_title)

    if not norm_cited or not norm_gt:
        result.verdict = Verdict.SUSPICIOUS
        return result

    # Compute three scores
    result.ratio_score = fuzz.ratio(norm_cited, norm_gt)
    result.token_sort_score = fuzz.token_sort_ratio(norm_cited, norm_gt)
    result.token_set_score = fuzz.token_set_ratio(norm_cited, norm_gt)

    # Final score = max of all three
    result.final_score = max(
        result.ratio_score,
        result.token_sort_score,
        result.token_set_score,
    )

    # ── Author Comparison (secondary signal) ──────────────────────────
    author_match_ratio = _compare_authors(reference, ground_truth)
    if author_match_ratio is not None:
        if author_match_ratio >= 0.5:
            # Authors confirm the match — boost score
            result.final_score = min(100.0, result.final_score + _AUTHOR_BONUS)
            logger.debug(
                "Author bonus applied (+%d): %.0f%% surnames match",
                _AUTHOR_BONUS, author_match_ratio * 100,
            )

    # ── Year Comparison ───────────────────────────────────────────────
    if reference.year and ground_truth.year:
        result.year_match = reference.year == ground_truth.year

    # ── Verdict Classification ────────────────────────────────────────
    result.verdict = classify_score(result.final_score)

    logger.info(
        "Comparison: ratio=%.1f, token_sort=%.1f, token_set=%.1f, "
        "final=%.1f → %s",
        result.ratio_score,
        result.token_sort_score,
        result.token_set_score,
        result.final_score,
        result.verdict.value,
    )

    return result


def classify_score(score: float) -> Verdict:
    """
    Classify a fuzzy match score into a Verdict.

    Thresholds (conservative, zero false-positive bias):
        ≥ 90 → VERIFIED
        70–89 → SUSPICIOUS
        < 70 → MISMATCH

    Args:
        score: Composite fuzzy match score (0-100).

    Returns:
        Verdict enum value.
    """
    if score >= THRESHOLD_VERIFIED:
        return Verdict.VERIFIED
    elif score >= THRESHOLD_SUSPICIOUS:
        return Verdict.SUSPICIOUS
    else:
        return Verdict.MISMATCH


def _compare_authors(
    reference: ParsedReference,
    ground_truth: GroundTruth,
) -> Optional[float]:
    """
    Compare author surnames between cited reference and ground truth.

    Uses surname extraction and set intersection to compute match ratio.

    Args:
        reference:    Parsed reference with authors_raw.
        ground_truth: Ground truth with authors list.

    Returns:
        Match ratio (0.0 to 1.0), or None if comparison is not possible.
    """
    if not reference.authors_raw or not ground_truth.authors:
        return None

    # Extract surnames from ground truth (structured list)
    gt_surnames = extract_surnames(ground_truth.authors)
    if not gt_surnames:
        return None

    # Parse cited authors — split by common delimiters
    import re
    cited_author_parts = re.split(r"[,;&]|\band\b", reference.authors_raw)
    cited_names = [p.strip() for p in cited_author_parts if p.strip()]

    if not cited_names:
        return None

    cited_surnames = extract_surnames(cited_names)
    if not cited_surnames:
        return None

    # Compute intersection ratio
    matched = gt_surnames & cited_surnames
    total = min(len(gt_surnames), len(cited_surnames))

    if total == 0:
        return None

    return len(matched) / total


# Title-only matching (no DOI) has no identifier to anchor on, so a similar
# title alone is not proof. These bounds keep the zero false-accept bias.
TITLE_ONLY_MIN_SCORE = 85          # overall similarity needed at all
TITLE_ONLY_MIN_STRICT_SCORE = 80   # ratio / token_sort (not inflated by subsets)
TITLE_ONLY_MIN_SCORE_NO_AUTHORS = 95         # when the citation lists no authors
TITLE_ONLY_MIN_STRICT_SCORE_NO_AUTHORS = 90  # ...also for the strict scorers
TITLE_ONLY_MAX_YEAR_GAP = 1        # preprint vs. published year
TITLE_ONLY_MAX_YEAR_GAP_AUTHORS = 3  # online-first vs. print year, if authors agree
TITLE_ONLY_MIN_WORDS_SUBSET = 4    # shorter title must have this many words to
                                   # be trusted as a truncated/subtitle-less citation


_INITIALS = re.compile(r"^(?:[A-ZÀ-ÖØ-Ý]\.?\s?){1,3}$")


def _cited_first_surname(authors_raw: str) -> Optional[str]:
    """
    Surname of the first cited author, whatever the name order.

    "Hobbs, N. T., Hooten" → hobbs; "N. Thompson Hobbs and M. Hooten" → hobbs;
    "Hobbs NT, Hooten MB" → hobbs. Returns None if it cannot be determined.
    """
    segments = [s.strip() for s in re.split(r",|;|&|\band\b", authors_raw) if s.strip()]
    if not segments:
        return None
    first = segments[0]
    if len(segments) > 1 and _INITIALS.match(segments[1]):
        name = first                       # "Surname, I."
    else:
        words = first.split()
        if len(words) >= 2 and _INITIALS.match(words[-1]):
            name = words[0]                # "Surname IN"
        else:
            name = words[-1] if words else ""   # "Given Surname"
    tokens = normalize_author_name(name).split()
    return tokens[-1] if tokens and len(tokens[-1]) >= 2 else None


def authors_overlap(
    reference: ParsedReference,
    ground_truth: GroundTruth,
) -> Optional[bool]:
    """
    Is the cited FIRST author one of the ground-truth authors?

    Requiring the first author (rather than any surname) stops common
    surnames ("Chen", "Smith") that happen to appear later in a real
    author list from validating an invented citation. If the first author
    cannot be parsed, falls back to whole-word presence of any surname.

    Robust to initials and name order ("Hobbs, N. T.", "N. Thompson Hobbs",
    "Hobbs NT").

    Returns:
        True/False, or None if either side has no author information.
    """
    if not reference.authors_raw or not ground_truth.authors:
        return None
    gt_surnames = {s for s in extract_surnames(ground_truth.authors) if len(s) >= 2}
    if not gt_surnames:
        return None
    first = _cited_first_surname(reference.authors_raw)
    if first:
        return first in gt_surnames
    cited_words = set(normalize_author_name(reference.authors_raw).split())
    return bool(gt_surnames & cited_words)


def confirm_title_only_match(
    reference: ParsedReference,
    ground_truth: GroundTruth,
    comparison: ComparisonResult,
) -> tuple:
    """
    Decide whether a DOI-less title search result is really the cited paper.

    A match is confirmed only if ALL hold:
        1. overall score ≥ TITLE_ONLY_MIN_SCORE
        2. max(ratio, token_sort) ≥ TITLE_ONLY_MIN_STRICT_SCORE — token_set
           alone is inflated whenever one title's words are a subset of the
           other's (e.g. "Hierarchical Bayesian Models")
        3. the cited first author is among the record's authors (a record
           with no author data cannot confirm a citation that names authors);
           if the citation lists no authors, the title must be near-exact
           (score ≥ 95, strict ≥ 90)
        4. years (when both known) differ by at most TITLE_ONLY_MAX_YEAR_GAP
           (a wider gap is tolerated when authors agree: online-first vs print)

    Rule 2 is waived for a title that merely contains / is contained in the
    other (dropped subtitle) if authors AND year also agree.

    Returns:
        (confirmed: bool, reason: str) — reason explains a rejection.
    """
    score = comparison.final_score
    if score < TITLE_ONLY_MIN_SCORE:
        return False, f"match score ({score:.1f}%) is too low for confirmation"

    strict = max(comparison.ratio_score, comparison.token_sort_score)
    overlap = authors_overlap(reference, ground_truth)
    year_gap = (
        abs(reference.year - ground_truth.year)
        if reference.year and ground_truth.year else None
    )

    if strict < TITLE_ONLY_MIN_STRICT_SCORE:
        # One title containing the other is legitimate when a citation drops
        # the subtitle — but only with independent agreement on authors AND
        # year, and a title long enough not to be a generic phrase.
        min_words = min(
            len(normalize_title(_get_best_cited_title(reference) or "").split()),
            len(normalize_title(ground_truth.title or "").split()),
        )
        subtitle_ok = (
            overlap is True
            and year_gap is not None and year_gap <= TITLE_ONLY_MAX_YEAR_GAP
            and comparison.token_set_score >= TITLE_ONLY_MIN_SCORE_NO_AUTHORS
            and min_words >= TITLE_ONLY_MIN_WORDS_SUBSET
        )
        if not subtitle_ok:
            return False, (
                f"titles only share a subset of words (strict similarity {strict:.1f}%)"
            )
    if overlap is False:
        return False, "a similar title exists but none of the cited authors match"
    if overlap is None:
        if reference.authors_raw:
            # The citation names authors but the found record has none to
            # check them against — an exact title alone must not vouch for them.
            return False, "the matching record has no author data to confirm the cited authors"
        if (
            score < TITLE_ONLY_MIN_SCORE_NO_AUTHORS
            or strict < TITLE_ONLY_MIN_STRICT_SCORE_NO_AUTHORS
        ):
            return False, (
                f"no authors to confirm the match; title similarity "
                f"{score:.1f}% (strict {strict:.1f}%) is not near-exact"
            )

    max_gap = TITLE_ONLY_MAX_YEAR_GAP_AUTHORS if overlap is True else TITLE_ONLY_MAX_YEAR_GAP
    if year_gap is not None and year_gap > max_gap:
        return False, (
            f"year differs (cited {reference.year}, found {ground_truth.year})"
        )

    return True, ""


def _get_best_cited_title(reference: ParsedReference) -> Optional[str]:
    """
    Get the best available title from the parsed reference.

    Prefers the extracted candidate_title. Falls back to using a
    cleaned version of the raw text (removing authors, year, URLs).

    Args:
        reference: Parsed reference object.

    Returns:
        Title string, or None.
    """
    if reference.candidate_title:
        return reference.candidate_title

    # Fallback: use raw text (less accurate but better than nothing)
    import re
    raw = reference.raw_text
    # Remove URLs
    raw = re.sub(r"https?://[^\s]+", "", raw)
    # Remove DOI patterns
    raw = re.sub(r"10\.\d{4,9}/[^\s]+", "", raw)
    # Remove reference numbers
    raw = re.sub(r"^\[\d+\]\.?\s*", "", raw)
    raw = raw.strip()

    if len(raw) > 15:
        return raw

    return None
