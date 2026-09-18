"""
Multi-scorer fuzzy matching engine for citation comparison.

Compares a cited reference against ground-truth metadata using three
complementary RapidFuzz scorers, producing a composite score and
deterministic verdict classification.

Enhanced with author surname comparison for higher accuracy.
"""

import logging
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
from .normalizer import extract_surnames, normalize_title

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
