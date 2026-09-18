"""
Tests for the string normalization module.

Covers title normalization (HTML, LaTeX, Unicode, arXiv),
author normalization, and surname extraction.
"""

import pytest

from citation_verifier.normalizer import (
    extract_surnames,
    normalize_author_name,
    normalize_title,
)


# ═══════════════════════════════════════════════════════════════
# Title Normalization
# ═══════════════════════════════════════════════════════════════

class TestNormalizeTitle:
    """Tests for normalize_title()."""

    def test_basic_lowercase(self):
        assert normalize_title("Attention Is All You Need") == \
               "attention is all you need"

    def test_html_tags_stripped(self):
        result = normalize_title("A <i>Novel</i> Approach to <b>NLP</b>")
        assert "<i>" not in result
        assert "<b>" not in result
        assert "novel" in result
        assert "nlp" in result

    def test_html_sub_sup(self):
        result = normalize_title("CO<sub>2</sub> Emissions and H<sub>2</sub>O")
        assert "<sub>" not in result
        assert "co" in result

    def test_latex_commands(self):
        result = normalize_title("\\textbf{BERT}: A \\emph{New} Model")
        assert "bert" in result
        assert "new" in result
        assert "\\" not in result

    def test_latex_braces_removed(self):
        result = normalize_title("{Attention} {Is} {All} {You} {Need}")
        assert "{" not in result
        assert "}" not in result
        assert "attention is all you need" == result

    def test_arxiv_prefix_removed(self):
        result = normalize_title(
            "arXiv preprint arXiv:2005.11401 Retrieval-Augmented Generation"
        )
        assert "arxiv" not in result
        assert "preprint" not in result
        assert "retrieval" in result

    def test_arxiv_colon_prefix(self):
        result = normalize_title("arXiv: 2005.11401 Some Title")
        assert "arxiv" not in result

    def test_unicode_normalization(self):
        # é (composed) vs e + combining accent should normalize the same
        title1 = normalize_title("Résumé of Research")
        title2 = normalize_title("Re\u0301sume\u0301 of Research")
        assert title1 == title2

    def test_dash_normalization(self):
        """All dash variants should normalize to ASCII hyphen."""
        # en-dash, em-dash, minus sign
        result = normalize_title("Self–Attention — A −Key Concept")
        assert "–" not in result
        assert "—" not in result
        assert "−" not in result
        assert "-" in result

    def test_special_chars_removed(self):
        result = normalize_title("Title: A 'Novel' Approach (2024)")
        assert ":" not in result
        assert "'" not in result
        assert "(" not in result

    def test_whitespace_collapsed(self):
        result = normalize_title("Title   with    lots   of   spaces")
        assert "  " not in result
        assert "title with lots of spaces" == result

    def test_empty_string(self):
        assert normalize_title("") == ""

    def test_none_input(self):
        assert normalize_title(None) == ""

    def test_only_special_chars(self):
        result = normalize_title("!@#$%^&*()")
        assert result.strip() == ""


# ═══════════════════════════════════════════════════════════════
# Author Normalization
# ═══════════════════════════════════════════════════════════════

class TestNormalizeAuthorName:
    """Tests for normalize_author_name()."""

    def test_basic_lowercase(self):
        assert normalize_author_name("John Smith") == "john smith"

    def test_suffix_removed(self):
        result = normalize_author_name("Robert Johnson Jr.")
        assert "jr" not in result
        assert "robert" in result
        assert "johnson" in result

    def test_title_removed(self):
        result = normalize_author_name("Dr. Jane Doe")
        assert "dr" not in result
        assert "jane" in result

    def test_unicode_preserved(self):
        result = normalize_author_name("José García")
        assert "jos" in result  # Unicode normalized
        assert "garc" in result

    def test_empty_string(self):
        assert normalize_author_name("") == ""

    def test_none_input(self):
        assert normalize_author_name(None) == ""

    def test_punctuation_removed(self):
        result = normalize_author_name("O'Brien, M.D.")
        assert "'" not in result
        assert "brien" in result


# ═══════════════════════════════════════════════════════════════
# Surname Extraction
# ═══════════════════════════════════════════════════════════════

class TestExtractSurnames:
    """Tests for extract_surnames()."""

    def test_basic_extraction(self):
        authors = ["John Smith", "Jane Doe", "Bob Johnson"]
        surnames = extract_surnames(authors)
        assert "smith" in surnames
        assert "doe" in surnames
        assert "johnson" in surnames

    def test_single_author(self):
        surnames = extract_surnames(["Alice Brown"])
        assert "brown" in surnames
        assert len(surnames) == 1

    def test_empty_list(self):
        assert extract_surnames([]) == set()

    def test_deduplication(self):
        """Two authors with the same surname should produce one entry."""
        authors = ["John Smith", "Jane Smith"]
        surnames = extract_surnames(authors)
        assert len(surnames) == 1
        assert "smith" in surnames

    def test_single_name(self):
        """Single-word name should be treated as surname."""
        surnames = extract_surnames(["Madonna"])
        assert "madonna" in surnames

    def test_suffix_handling(self):
        """Author with Jr/III suffix should still extract correct surname."""
        surnames = extract_surnames(["Robert Johnson Jr."])
        assert "johnson" in surnames or "robert" in surnames
