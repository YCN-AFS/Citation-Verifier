"""
String normalization for academic title and author comparison.

Applies a pipeline of transformations to standardize strings before
fuzzy matching, eliminating superficial differences that would
produce false mismatches.
"""

import re
import unicodedata


def normalize_title(title: str) -> str:
    """
    Normalize an academic paper title for fuzzy comparison.

    Pipeline:
        1. Unicode NFC normalization
        2. Lowercase
        3. Strip HTML tags
        4. Strip LaTeX commands (e.g., \\textbf{}, \\emph{})
        5. Remove arXiv preprint prefixes
        6. Normalize dashes and hyphens to a single type
        7. Remove non-alphanumeric characters (except spaces and hyphens)
        8. Collapse whitespace
        9. Strip leading/trailing whitespace

    Args:
        title: Raw title string from API or citation text.

    Returns:
        Normalized title string ready for comparison.
    """
    if not title:
        return ""

    # 1. Unicode normalization (e.g., accented chars → composed form)
    text = unicodedata.normalize("NFC", title)

    # 2. Lowercase
    text = text.lower()

    # 3. Strip HTML tags (e.g., <i>, <sub>, <sup>)
    text = re.sub(r"<[^>]+>", " ", text)

    # 4. Strip LaTeX commands but keep content inside braces
    #    e.g., \textbf{BERT} → BERT, \emph{attention} → attention
    text = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)  # stray commands without braces
    text = re.sub(r"[{}]", "", text)           # leftover braces

    # 5. Remove arXiv preprint prefixes
    text = re.sub(r"arxiv\s*preprint\s*arxiv:\s*", "", text)
    text = re.sub(r"arxiv:\s*", "", text)

    # 6. Normalize all dash variants to ASCII hyphen
    text = re.sub(r"[–—−‐‑‒]", "-", text)

    # 7. Remove non-alphanumeric except spaces and hyphens
    text = re.sub(r"[^\w\s-]", " ", text)

    # 8. Collapse whitespace
    text = re.sub(r"\s+", " ", text)

    # 9. Strip
    text = text.strip()

    return text


def normalize_author_name(name: str) -> str:
    """
    Normalize an author name for comparison.

    Strips titles, normalizes Unicode, lowercases, and removes
    punctuation to produce a comparable surname token.

    Args:
        name: Raw author name string.

    Returns:
        Normalized author name.
    """
    if not name:
        return ""

    text = unicodedata.normalize("NFC", name)
    text = text.lower()
    # Remove common suffixes/titles
    text = re.sub(r"\b(jr|sr|iii|iv|dr|prof|mr|mrs|ms)\b\.?", "", text)
    # Keep only word characters and spaces
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def extract_surnames(authors_list: list) -> set:
    """
    Extract a set of normalized surnames from a list of author names.

    Heuristic: the last token of each name is the surname.

    Args:
        authors_list: List of author name strings (e.g., ["John Smith", "Jane Doe"]).

    Returns:
        Set of lowercase surname strings.
    """
    surnames = set()
    for name in authors_list:
        normalized = normalize_author_name(name)
        tokens = normalized.split()
        if tokens:
            surnames.add(tokens[-1])
    return surnames
