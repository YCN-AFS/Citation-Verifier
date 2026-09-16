"""
Reference text parser.

Splits raw unstructured text containing academic references into
individual ParsedReference objects, extracting DOIs, candidate titles,
years, and author blocks using robust regex heuristics.

Supported formats:
    - [N] / [N].  numbered references (IEEE-like)
    - N.           numbered dot references (Vancouver)
    - Newline-delimited (APA, MLA, Chicago)
    - @article{...} BibTeX entries
    - TY  - ...    RIS entries
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
    r"(10\.\d{4,9}/[^\s,;\]\"\'']+)",       # Core DOI (allows parens)
    re.IGNORECASE
)

# Reference number patterns
_REF_BRACKET_NUM = re.compile(r"^\[(\d+)\]\.?\s*")       # [1]. or [1]
_REF_DOT_NUM = re.compile(r"^(\d{1,3})\.\s+(?=[A-Z])")   # 1. Author...

# Year in parentheses: (2020), (2023, January 30), (n.d.)
_YEAR_PATTERN = re.compile(r"\((\d{4})(?:[,\s].*?)?\)")

# Bare year for Vancouver: ...2020;12(3):45-67 or ...2020.
_YEAR_BARE = re.compile(r"(?:^|[\s.])(\d{4})(?:[;.,\s]|$)")

# URL pattern (non-DOI)
_URL_PATTERN = re.compile(r"https?://[^\s,;)\]]+")

# BibTeX entry: @article{key, ...}
_BIBTEX_ENTRY = re.compile(
    r"@(\w+)\s*\{([^,]*),\s*(.*?)\}\s*$",
    re.DOTALL | re.MULTILINE
)
_BIBTEX_FIELD = re.compile(
    r"(\w+)\s*=\s*[{\"](.+?)[}\"]",
    re.DOTALL
)

# RIS tag: TY  - JOUR
_RIS_TAG = re.compile(r"^([A-Z][A-Z0-9])\s\s-\s(.*)$", re.MULTILINE)

# Splitters
_SPLIT_BRACKET = re.compile(r"(?=\[\d+\]\.?\s)")
_SPLIT_DOT_NUM = re.compile(r"(?=^\d{1,3}\.\s+[A-Z])", re.MULTILINE)


# ─────────────────────────────────────────────────────────────────────
# Format detection
# ─────────────────────────────────────────────────────────────────────

def _detect_format(text: str) -> str:
    """
    Auto-detect the reference format from raw text.

    Returns one of: 'bibtex', 'ris', 'bracket_num', 'dot_num', 'lines'.
    """
    if re.search(r"@\w+\s*\{", text):
        return "bibtex"
    if re.search(r"^TY\s\s-\s", text, re.MULTILINE):
        return "ris"

    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]

    bracket_count = sum(1 for l in lines if _REF_BRACKET_NUM.match(l))
    if bracket_count >= 2 or (bracket_count == 1 and len(lines) <= 3):
        return "bracket_num"

    dot_count = sum(1 for l in lines if _REF_DOT_NUM.match(l))
    if dot_count >= 2 or (dot_count == 1 and len(lines) <= 3):
        return "dot_num"

    return "lines"


# ─────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────

def parse_references(text: str) -> List[ParsedReference]:
    """
    Parse raw text containing academic references into structured objects.

    Auto-detects format and delegates to the appropriate parser:
        - BibTeX (@article{...})
        - RIS (TY  - JOUR)
        - [N]. numbered references (IEEE)
        - N. numbered references (Vancouver)
        - Newline-delimited (APA, MLA, Chicago — fallback)

    Args:
        text: Raw multiline text containing references.

    Returns:
        List of ParsedReference objects with extracted fields.
    """
    text = text.strip()
    if not text:
        return []

    fmt = _detect_format(text)

    if fmt == "bibtex":
        return _parse_bibtex(text)
    if fmt == "ris":
        return _parse_ris(text)
    if fmt == "bracket_num":
        return _parse_numbered(text, _SPLIT_BRACKET, _REF_BRACKET_NUM)
    if fmt == "dot_num":
        return _parse_numbered(text, _SPLIT_DOT_NUM, _REF_DOT_NUM)

    # Default: line-delimited (APA, MLA, etc.)
    return _parse_lines(text)


# ─────────────────────────────────────────────────────────────────────
# Format-specific parsers
# ─────────────────────────────────────────────────────────────────────

def _parse_numbered(
    text: str,
    splitter: re.Pattern,
    num_pattern: re.Pattern,
) -> List[ParsedReference]:
    """Parse references split by a numbered pattern."""
    segments = splitter.split(text)
    segments = [s.strip() for s in segments if s.strip()]

    if len(segments) <= 1:
        segments = [l.strip() for l in text.split("\n") if l.strip()]

    refs = []
    for seg in segments:
        ref = _parse_single_reference(seg, num_pattern)
        if ref:
            refs.append(ref)
    return refs


def _parse_lines(text: str) -> List[ParsedReference]:
    """
    Parse newline-delimited references (APA, MLA, Chicago, etc.).

    Handles multi-line entries by joining continuation lines
    (lines that don't start with an author-like pattern).
    """
    raw_lines = text.split("\n")
    entries = []
    current = ""

    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            if current:
                entries.append(current)
                current = ""
            continue

        # A new entry typically starts with an author surname or number
        is_new = (
            re.match(r"^[A-Z\u00C0-\u024F][a-z\u00C0-\u024F]+,?\s", stripped) or
            re.match(r"^\d{1,3}\.\s", stripped) or
            re.match(r"^\[", stripped) or
            not current
        )

        if is_new and current:
            entries.append(current)
            current = stripped
        elif current:
            current += " " + stripped
        else:
            current = stripped

    if current:
        entries.append(current)

    refs = []
    for i, entry in enumerate(entries):
        ref = _parse_single_reference(entry, _REF_BRACKET_NUM)
        if ref:
            if ref.ref_number is None:
                ref.ref_number = i + 1
            refs.append(ref)
    return refs


def _parse_bibtex(text: str) -> List[ParsedReference]:
    """
    Parse BibTeX entries into ParsedReference objects.

    Handles @article, @inproceedings, @book, @misc, etc.
    """
    # Split into individual entries
    entries = re.findall(
        r"@\w+\s*\{[^@]*?\n\s*\}",
        text,
        re.DOTALL,
    )
    if not entries:
        # Try simpler pattern
        entries = re.findall(r"@\w+\s*\{.*?\}\s*$", text, re.DOTALL | re.MULTILINE)

    refs = []
    for i, entry in enumerate(entries):
        fields = {}
        for match in _BIBTEX_FIELD.finditer(entry):
            key = match.group(1).lower()
            val = match.group(2).strip().rstrip(",")
            fields[key] = val

        title = fields.get("title", "")
        author = fields.get("author", "")
        year_str = fields.get("year", "")
        doi = fields.get("doi", "")
        journal = fields.get("journal", fields.get("booktitle", ""))

        # Clean BibTeX formatting
        title = re.sub(r"[{}]", "", title).strip()
        author = re.sub(r"[{}]", "", author).strip()

        year = None
        if year_str:
            try:
                year = int(re.sub(r"[{}]", "", year_str))
            except ValueError:
                pass

        ref = ParsedReference(
            raw_text=entry.strip(),
            ref_number=i + 1,
            doi=_clean_doi(doi) if doi else None,
            candidate_title=title if title else None,
            year=year,
            authors_raw=author if author else None,
        )
        refs.append(ref)

    return refs


def _parse_ris(text: str) -> List[ParsedReference]:
    """
    Parse RIS format entries into ParsedReference objects.

    RIS uses two-letter tags like TY, AU, TI, DO, PY, ER.
    """
    # Split by TY  - markers (start of each entry)
    blocks = re.split(r"(?=^TY\s\s-\s)", text, flags=re.MULTILINE)
    blocks = [b.strip() for b in blocks if b.strip()]

    refs = []
    for i, block in enumerate(blocks):
        tags = _RIS_TAG.findall(block)
        fields = {}
        authors = []
        for tag, val in tags:
            val = val.strip()
            if tag == "AU":
                authors.append(val)
            else:
                fields[tag] = val

        title = fields.get("TI", fields.get("T1", ""))
        doi = fields.get("DO", "")
        year_str = fields.get("PY", fields.get("Y1", ""))
        journal = fields.get("JO", fields.get("T2", ""))

        year = None
        if year_str:
            m = re.search(r"(\d{4})", year_str)
            if m:
                year = int(m.group(1))

        ref = ParsedReference(
            raw_text=block.strip(),
            ref_number=i + 1,
            doi=_clean_doi(doi) if doi else None,
            candidate_title=title if title else None,
            year=year,
            authors_raw=", ".join(authors) if authors else None,
        )
        refs.append(ref)

    return refs


# ─────────────────────────────────────────────────────────────────────
# Single reference parser
# ─────────────────────────────────────────────────────────────────────

def _parse_single_reference(
    text: str,
    num_pattern: re.Pattern = _REF_BRACKET_NUM,
) -> Optional[ParsedReference]:
    """
    Parse a single reference string into a ParsedReference object.

    Extraction order:
        1. Reference number ([N] or N.)
        2. DOI
        3. Year
        4. Candidate title (heuristic extraction)
        5. Author block

    Args:
        text: A single reference string.
        num_pattern: Compiled regex for extracting ref number.

    Returns:
        ParsedReference object, or None if the text is too short to be valid.
    """
    if len(text) < 15:  # Too short to be a real reference
        return None

    ref = ParsedReference(raw_text=text)

    # 1. Extract reference number
    num_match = num_pattern.search(text)
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
    elif not ref.year:
        # Fallback: bare year (Vancouver-style)
        bare = _YEAR_BARE.search(text)
        if bare:
            y = int(bare.group(1))
            if 1900 <= y <= 2030:
                ref.year = y

    # 4. Extract candidate title
    ref.candidate_title = _extract_title(text, num_pattern)

    # 5. Extract authors (text before the year)
    ref.authors_raw = _extract_authors(text, num_pattern)

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
    doi = doi.rstrip(".,;:'\"]}\\'")

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


def _extract_title(
    text: str,
    num_pattern: re.Pattern = _REF_BRACKET_NUM,
) -> Optional[str]:
    """
    Heuristically extract the paper title from a reference string.

    Strategy: The title typically appears after the year and before
    the journal name, DOI, or URL. We look for text between common
    delimiters.

    Args:
        text: Single reference string.
        num_pattern: Pattern used for removing ref number prefix.

    Returns:
        Extracted title candidate, or None.
    """
    # Remove the reference number prefix
    clean = num_pattern.sub("", text)

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

    # Strategy 3: Quoted title — "Title" or 'Title'
    quoted = re.search(r'["\u201c](.{15,}?)["\u201d]', clean)
    if quoted:
        return quoted.group(1).strip().rstrip(".")

    return None


def _extract_authors(
    text: str,
    num_pattern: re.Pattern = _REF_BRACKET_NUM,
) -> Optional[str]:
    """
    Extract the author block from a reference string.

    Heuristic: authors appear before the first year in parentheses.

    Args:
        text: Single reference string.
        num_pattern: Pattern used for removing ref number prefix.

    Returns:
        Author block string, or None.
    """
    clean = num_pattern.sub("", text)
    year_match = _YEAR_PATTERN.search(clean)
    if year_match:
        authors = clean[:year_match.start()].strip().rstrip(",. ")
        if len(authors) > 2:
            return authors
    return None
