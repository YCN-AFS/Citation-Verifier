"""
Reference text parser.

Splits raw unstructured text containing academic references into
individual ParsedReference objects, extracting DOIs, candidate titles,
years, and author blocks using robust regex heuristics.
"""

import re
from typing import List, Optional

from .config import ParsedReference


# ─────────────────────────────────────────────────────────────────────
# Compiled Regex Patterns
# ─────────────────────────────────────────────────────────────────────

# DOI pattern — captures standard DOIs including complex suffixes
# NOTE: Allows parentheses within DOIs (e.g., 10.1016/S0167-9236(02)00114-8)
_DOI_PATTERN = re.compile(
    r"(?:https?://(?:dx\.)?doi\.org/)?"     # Optional DOI URL prefix
    r"(10\.\d{4,9}/[^\s,;\]\"']+)",         # Core DOI (allows parens)
    re.IGNORECASE
)

# Reference number: [1], [2]., [10]. etc.
_REF_NUMBER_PATTERN = re.compile(r"^\[(\d+)\]\.?\s*")

# Year in parentheses: (2020), (2023, January 30), (n.d.)
_YEAR_PATTERN = re.compile(r"\((\d{4})(?:[,\s].*?)?\)")

# URL pattern (non-DOI)
_URL_PATTERN = re.compile(r"https?://[^\s,;)\]]+")

# Reference splitter: lines starting with [N] or numbered entries
_REF_SPLIT_PATTERN = re.compile(r"(?=\[\d+\]\.?\s)")


def parse_references(text: str) -> List[ParsedReference]:
    """
    Parse raw text containing academic references into structured objects.

    Supports:
        - [N]. numbered references (most common in academic papers)
        - Newline-delimited references (fallback)

    Args:
        text: Raw multiline text containing references.

    Returns:
        List of ParsedReference objects with extracted fields.
    """
    text = text.strip()
    if not text:
        return []

    # Try splitting by [N] numbered markers first
    segments = _REF_SPLIT_PATTERN.split(text)
    segments = [s.strip() for s in segments if s.strip()]

    # Fallback: if only one segment, split by newlines
    if len(segments) <= 1:
        segments = [line.strip() for line in text.split("\n") if line.strip()]

    references = []
    for segment in segments:
        ref = _parse_single_reference(segment)
        if ref:
            references.append(ref)

    return references


def _parse_single_reference(text: str) -> Optional[ParsedReference]:
    """
    Parse a single reference string into a ParsedReference object.

    Extraction order:
        1. Reference number ([N])
        2. DOI
        3. Year
        4. Candidate title (heuristic extraction)
        5. Author block

    Args:
        text: A single reference string.

    Returns:
        ParsedReference object, or None if the text is too short to be valid.
    """
    if len(text) < 15:  # Too short to be a real reference
        return None

    ref = ParsedReference(raw_text=text)

    # 1. Extract reference number
    num_match = _REF_NUMBER_PATTERN.search(text)
    if num_match:
        ref.ref_number = int(num_match.group(1))

    # 2. Extract DOI
    doi_match = _DOI_PATTERN.search(text)
    if doi_match:
        raw_doi = doi_match.group(1)
        # Clean trailing punctuation that's not part of the DOI
        ref.doi = _clean_doi(raw_doi)

    # 3. Extract year
    year_match = _YEAR_PATTERN.search(text)
    if year_match:
        try:
            ref.year = int(year_match.group(1))
        except ValueError:
            pass

    # 4. Extract candidate title
    ref.candidate_title = _extract_title(text)

    # 5. Extract authors (text before the year)
    ref.authors_raw = _extract_authors(text)

    return ref


def _clean_doi(doi: str) -> str:
    """
    Clean a raw DOI string by removing trailing punctuation artifacts.

    Handles edge cases like DOIs ending with periods, commas, or
    unbalanced closing parentheses. Preserves balanced parentheses
    within DOIs (e.g., 10.1016/S0167-9236(02)00114-8).

    Args:
        doi: Raw DOI string.

    Returns:
        Cleaned DOI string.
    """
    # Strip common trailing punctuation (but not parens yet)
    doi = doi.rstrip(".,;:'\"]}\'")

    # Handle parentheses: strip trailing ')' only if unbalanced
    while doi.endswith(")"):
        open_count = doi.count("(")
        close_count = doi.count(")")
        if close_count > open_count:
            doi = doi[:-1]
        else:
            break  # Balanced — keep the closing paren

    # Final cleanup of any trailing periods after paren handling
    doi = doi.rstrip(".")

    return doi


def _extract_title(text: str) -> Optional[str]:
    """
    Heuristically extract the paper title from a reference string.

    Strategy: The title typically appears after the year and before
    the journal name, DOI, or URL. We look for text between common
    delimiters.

    Args:
        text: Single reference string.

    Returns:
        Extracted title candidate, or None.
    """
    # Remove the reference number prefix
    clean = _REF_NUMBER_PATTERN.sub("", text)

    # Strategy 1: Find text after "(YYYY)." pattern
    # e.g., "Author (2020). Title goes here. Journal..."
    year_title_match = re.search(
        r"\(\d{4}(?:[,\s][^)]*?)?\)\.\s*(.+?)(?:\.\s*(?:In\b|Proceedings|"
        r"IEEE|ACM|Advances|arXiv|https?://|DOI:|doi:|\d+\(\d+\)|"
        r"[A-Z][a-z]+\s+(?:of|on|in|for)\b))",
        clean,
        re.IGNORECASE
    )
    if year_title_match:
        title = year_title_match.group(1).strip().rstrip(".")
        if len(title) > 10:
            return title

    # Strategy 2: Find text between year block and first URL/DOI
    year_match = _YEAR_PATTERN.search(clean)
    if year_match:
        after_year = clean[year_match.end():].strip()
        if after_year.startswith(". "):
            after_year = after_year[2:]
        elif after_year.startswith("."):
            after_year = after_year[1:].strip()

        # Take text up to the first URL, DOI reference, or period followed
        # by a capitalized journal-like word
        end_match = re.search(
            r"(?:https?://|(?:doi|DOI):\s*10\.|"
            r"\.\s*(?:In\s|Proceedings|IEEE|ACM|Advances|arXiv|"
            r"[A-Z][a-z]+\s+(?:of|on|in|for|and)\s))",
            after_year
        )
        if end_match:
            title = after_year[:end_match.start()].strip().rstrip(".")
        else:
            # Fallback: take the first sentence after the year
            period_match = re.search(r"\.\s", after_year)
            if period_match and period_match.start() > 10:
                title = after_year[:period_match.start()].strip()
            else:
                title = after_year.strip().rstrip(".")

        # Remove trailing URL if accidentally captured
        title = _URL_PATTERN.sub("", title).strip().rstrip(".")

        if len(title) > 10:
            return title

    return None


def _extract_authors(text: str) -> Optional[str]:
    """
    Extract the author block from a reference string.

    Heuristic: authors appear before the first year in parentheses.

    Args:
        text: Single reference string.

    Returns:
        Author block string, or None.
    """
    clean = _REF_NUMBER_PATTERN.sub("", text)
    year_match = _YEAR_PATTERN.search(clean)
    if year_match:
        authors = clean[:year_match.start()].strip().rstrip(",. ")
        if len(authors) > 2:
            return authors
    return None
