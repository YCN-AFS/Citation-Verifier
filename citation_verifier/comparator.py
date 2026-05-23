"""
Multi-scorer fuzzy matching engine for citation comparison.

Compares a cited reference against ground-truth metadata using three
complementary RapidFuzz scorers, producing a composite score and
deterministic verdict classification.
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


def compare(
    reference: ParsedReference,
    ground_truth: GroundTruth,
) -> ComparisonResult:
    """
    Compare a parsed reference against ground-truth metadata.

    Uses three RapidFuzz scorers on the normalized title, then classifies
    the result using conservative thresholds designed for zero false-positive
    tolerance.

    Scoring strategy:
        - ratio:           Full edit-distance similarity
        - token_sort_ratio: Word-order-independent match
        - token_set_ratio:  Handles subset/superset titles

    The final score is the MAXIMUM of all three scorers, ensuring the
    most generous interpretation wins.

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
