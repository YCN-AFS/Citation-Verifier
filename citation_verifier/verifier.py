"""
Core verification orchestrator.

Coordinates the full verification pipeline for each reference:
    1. Check DOI cache for existing results
    2. Route DOI to the correct primary API
    3. Fetch ground truth from the primary source
    4. Compare cited text against ground truth
    5. Optionally cross-validate with OpenAlex
    6. Handle references without DOIs via title search

Performance features:
    - Parallel verification via ThreadPoolExecutor (5 workers)
    - DOI cache layer (7-day TTL) to avoid redundant API calls
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

from .api_clients import (
    CrossrefClient,
    DataCiteClient,
    OpenAlexClient,
    route_doi_to_api,
)
from .cache import get_cached, set_cached
from .comparator import compare
from .config import (
    GroundTruth,
    ParsedReference,
    Verdict,
    VerificationResult,
)
from .normalizer import normalize_title
from .parser import parse_references

logger = logging.getLogger(__name__)

# Max parallel workers — balances speed vs. API rate limits
_MAX_WORKERS = 5


class CitationVerifier:
    """
    Main verification engine.

    Manages API client lifecycle and orchestrates the verification
    pipeline for all references in an input text.

    Usage:
        verifier = CitationVerifier()
        results = verifier.verify_text(raw_text)
    """

    def __init__(self, cross_validate: bool = True):
        """
        Initialize the verifier with API clients.

        Args:
            cross_validate: If True, use OpenAlex as a secondary check
                            for results from Crossref/DataCite.
        """
        self.crossref = CrossrefClient()
        self.datacite = DataCiteClient()
        self.openalex = OpenAlexClient()
        self.cross_validate = cross_validate

    def verify_text(self, text: str) -> List[VerificationResult]:
        """
        Verify all references found in raw text.

        Uses parallel execution for references with DOIs to maximize
        throughput. Results are returned in original reference order.

        Args:
            text: Raw multiline text containing academic references.

        Returns:
            List of VerificationResult objects, one per reference.
        """
        references = parse_references(text)
        logger.info("Parsed %d references from input text.", len(references))

        if not references:
            return []

        # For small batches (<=3), process sequentially to reduce overhead
        if len(references) <= 3:
            return [self._verify_single(ref) for ref in references]

        # Parallel verification for larger batches
        results = [None] * len(references)

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            future_to_idx = {
                executor.submit(self._verify_single, ref): i
                for i, ref in enumerate(references)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error("Verification failed for ref %d: %s", idx + 1, e)
                    results[idx] = VerificationResult(
                        reference=references[idx],
                        verdict=Verdict.API_ERROR,
                        error_message=f"Verification error: {str(e)}",
                    )

        return results

    def _verify_single(self, ref: ParsedReference) -> VerificationResult:
        """
        Verify a single parsed reference.

        Workflow:
            1. If DOI present → check cache → fetch from API → compare
            2. If primary fails → try other APIs
            3. If no DOI → search by title via OpenAlex
            4. Optionally cross-validate with OpenAlex

        Args:
            ref: A parsed reference.

        Returns:
            VerificationResult with verdict and comparison details.
        """
        result = VerificationResult(reference=ref)

        if ref.doi:
            result = self._verify_with_doi(ref, result)
        else:
            result = self._verify_without_doi(ref, result)

        return result

    def _verify_with_doi(
        self,
        ref: ParsedReference,
        result: VerificationResult,
    ) -> VerificationResult:
        """
        Verify a reference that has a DOI.

        Strategy:
            0. Check cache first
            1. Route to primary API (Crossref or DataCite)
            2. If primary fails, try the other API
            3. If both fail, try OpenAlex
            4. Cache the result
            5. Compare title from API against cited text
            6. Cross-validate with OpenAlex if enabled

        Args:
            ref: Parsed reference with a DOI.
            result: Pre-initialized VerificationResult.

        Returns:
            Updated VerificationResult.
        """
        doi = ref.doi
        ground_truth = None

        # Step 0: Check cache
        cached = get_cached(doi)
        if cached is not None:
            ground_truth = cached
            logger.info("Cache HIT for DOI: %s (%s)", doi, cached.api_source)

        # Step 1: Try primary API
        if ground_truth is None:
            primary = route_doi_to_api(doi)
            if primary == "Crossref":
                ground_truth = self.crossref.fetch_by_doi(doi)
                fallback_client = self.datacite
                fallback_name = "DataCite"
            else:
                ground_truth = self.datacite.fetch_by_doi(doi)
                fallback_client = self.crossref
                fallback_name = "Crossref"

            # Step 2: If primary fails, try fallback
            if ground_truth is None:
                logger.info("Primary API (%s) returned nothing. Trying %s...", primary, fallback_name)
                ground_truth = fallback_client.fetch_by_doi(doi)

            # Step 3: If both fail, try OpenAlex
            if ground_truth is None:
                logger.info("Crossref + DataCite failed. Trying OpenAlex...")
                ground_truth = self.openalex.fetch_by_doi(doi)

            # Step 4: Cache successful result
            if ground_truth is not None:
                set_cached(doi, ground_truth)

        # Step 5: Evaluate result
        if ground_truth is None:
            # DOI exists in none of the APIs → DEAD_DOI
            result.verdict = Verdict.DEAD_DOI
            result.error_message = f"DOI '{doi}' not found in any API."
            logger.warning("DEAD DOI: %s", doi)
            return result

        result.ground_truth = ground_truth

        # Step 6: Check retraction status (highest priority)
        if ground_truth.is_retracted:
            result.verdict = Verdict.RETRACTED
            result.error_message = (
                "This paper has been RETRACTED. "
                "It should not be cited in academic work."
            )
            logger.warning("RETRACTED paper detected: %s", doi)
            # Still do title comparison for informational purposes
            if ground_truth.title:
                comparison = compare(ref, ground_truth)
                result.comparison = comparison
            return result

        # Step 7: Compare title
        if ground_truth.title:
            comparison = compare(ref, ground_truth)
            result.comparison = comparison
            result.verdict = comparison.verdict
        else:
            # API returned data but no title
            result.verdict = Verdict.SUSPICIOUS
            result.error_message = "API returned metadata but no title."

        # Step 8: Cross-validate with OpenAlex (if enabled and primary wasn't OpenAlex)
        if self.cross_validate and ground_truth.api_source != "OpenAlex":
            result = self._cross_validate_with_openalex(ref, result)

        return result

    def _verify_without_doi(
        self,
        ref: ParsedReference,
        result: VerificationResult,
    ) -> VerificationResult:
        """
        Attempt to verify a reference that has no DOI.

        Uses title-based search via OpenAlex and Crossref as fallback.

        Args:
            ref: Parsed reference without DOI.
            result: Pre-initialized VerificationResult.

        Returns:
            Updated VerificationResult.
        """
        title = ref.candidate_title
        if not title:
            result.verdict = Verdict.NO_DOI
            result.error_message = "No DOI and no extractable title."
            return result

        logger.info("No DOI found. Searching by title: '%s'", title[:80])

        # Try OpenAlex first (larger catalog)
        ground_truth = self.openalex.search_by_title(title)

        # Fallback to Crossref bibliographic search
        if ground_truth is None:
            ground_truth = self.crossref.search_by_title(title)

        if ground_truth is None:
            result.verdict = Verdict.NO_DOI
            result.error_message = "No DOI and title search returned no results."
            return result

        result.ground_truth = ground_truth

        # Compare the search result against the cited text
        if ground_truth.title:
            comparison = compare(ref, ground_truth)
            result.comparison = comparison

            # For title-based search, use stricter threshold
            if comparison.final_score >= 85:
                result.verdict = Verdict.TITLE_MATCHED
            else:
                result.verdict = Verdict.NO_DOI
                result.error_message = (
                    f"Title search found a result but match score "
                    f"({comparison.final_score:.1f}%) is too low for confirmation."
                )
        else:
            result.verdict = Verdict.NO_DOI
            result.error_message = "Title search returned no usable title."

        return result

    def _cross_validate_with_openalex(
        self,
        ref: ParsedReference,
        result: VerificationResult,
    ) -> VerificationResult:
        """
        Cross-validate a verification result using OpenAlex.

        If the primary API said VERIFIED but OpenAlex disagrees (or has
        a different title for the same DOI), downgrade to SUSPICIOUS.

        Args:
            ref: Parsed reference.
            result: Current VerificationResult from primary API.

        Returns:
            Updated VerificationResult with cross_validated flag.
        """
        if not ref.doi:
            return result

        try:
            oa_truth = self.openalex.fetch_by_doi(ref.doi)
        except Exception as e:
            logger.warning("Cross-validation skipped (OpenAlex error): %s", e)
            return result

        if oa_truth is None or not oa_truth.title:
            # OpenAlex doesn't have this DOI — can't cross-validate
            return result

        # Propagate retraction status from OpenAlex
        if oa_truth.is_retracted and not result.ground_truth.is_retracted:
            result.ground_truth.is_retracted = True
            result.verdict = Verdict.RETRACTED
            result.error_message = (
                "This paper has been RETRACTED. "
                "It should not be cited in academic work."
            )
            logger.warning("RETRACTED detected via OpenAlex cross-validation: %s", ref.doi)
            return result

        # Compare OpenAlex title vs primary API title
        primary_title = normalize_title(result.ground_truth.title or "")
        oa_title = normalize_title(oa_truth.title or "")

        if primary_title and oa_title:
            from rapidfuzz import fuzz
            cross_score = fuzz.token_sort_ratio(primary_title, oa_title)

            if cross_score >= 85:
                # OpenAlex confirms the primary API's title → good
                result.cross_validated = True
                logger.info("Cross-validation CONFIRMED (%.1f%%)", cross_score)
            else:
                # Titles differ between APIs — downgrade if currently VERIFIED
                logger.warning(
                    "Cross-validation CONFLICT: primary='%s' vs OpenAlex='%s' (%.1f%%)",
                    primary_title[:60], oa_title[:60], cross_score,
                )
                if result.verdict == Verdict.VERIFIED:
                    result.verdict = Verdict.SUSPICIOUS
                    result.error_message = (
                        f"Cross-validation conflict: Crossref/DataCite and OpenAlex "
                        f"have different titles (similarity: {cross_score:.1f}%)."
                    )

        return result
