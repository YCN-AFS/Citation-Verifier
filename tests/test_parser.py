"""
Tests for the reference parser module.

Covers all supported formats: APA, IEEE, Vancouver, BibTeX, RIS,
and edge cases in DOI extraction, year parsing, and title extraction.
"""

import pytest

from citation_verifier.parser import (
    _clean_doi,
    _detect_format,
    _extract_title,
    _parse_single_reference,
    parse_references,
)


# ═══════════════════════════════════════════════════════════════
# Format Detection
# ═══════════════════════════════════════════════════════════════

class TestFormatDetection:
    """Tests for _detect_format()."""

    def test_detect_bibtex(self, bibtex_references):
        assert _detect_format(bibtex_references) == "bibtex"

    def test_detect_ris(self, ris_references):
        assert _detect_format(ris_references) == "ris"

    def test_detect_bracket_num(self, ieee_references):
        assert _detect_format(ieee_references) == "bracket_num"

    def test_detect_dot_num(self, vancouver_references):
        assert _detect_format(vancouver_references) == "dot_num"

    def test_detect_lines(self, apa_references):
        assert _detect_format(apa_references) == "lines"

    def test_detect_single_bracket(self):
        text = "[1]. Some reference with only one entry."
        # Single bracket entry with few lines → bracket_num
        assert _detect_format(text) == "bracket_num"


# ═══════════════════════════════════════════════════════════════
# APA Format Parsing
# ═══════════════════════════════════════════════════════════════

class TestParseAPA:
    """Tests for APA-style reference parsing."""

    def test_parse_apa_count(self, apa_references):
        refs = parse_references(apa_references)
        assert len(refs) == 2

    def test_parse_apa_doi_extraction(self, apa_references):
        refs = parse_references(apa_references)
        assert refs[0].doi == "10.48550/arXiv.1706.03762"
        assert refs[1].doi == "10.18653/v1/N19-1423"

    def test_parse_apa_year_extraction(self, apa_references):
        refs = parse_references(apa_references)
        assert refs[0].year == 2017
        assert refs[1].year == 2019

    def test_parse_apa_title_extraction(self, apa_references):
        refs = parse_references(apa_references)
        assert refs[0].candidate_title is not None
        assert "attention" in refs[0].candidate_title.lower()


# ═══════════════════════════════════════════════════════════════
# IEEE Format Parsing
# ═══════════════════════════════════════════════════════════════

class TestParseIEEE:
    """Tests for IEEE-style [N]. reference parsing."""

    def test_parse_ieee_count(self, ieee_references):
        refs = parse_references(ieee_references)
        assert len(refs) == 2

    def test_parse_ieee_ref_numbers(self, ieee_references):
        refs = parse_references(ieee_references)
        assert refs[0].ref_number == 1
        assert refs[1].ref_number == 2

    def test_parse_ieee_doi(self, ieee_references):
        refs = parse_references(ieee_references)
        assert refs[0].doi == "10.48550/arXiv.2005.11401"
        assert refs[1].doi == "10.48550/arXiv.2005.14165"


# ═══════════════════════════════════════════════════════════════
# BibTeX Format Parsing
# ═══════════════════════════════════════════════════════════════

class TestParseBibTeX:
    """Tests for BibTeX parsing."""

    def test_parse_bibtex_count(self, bibtex_references):
        refs = parse_references(bibtex_references)
        assert len(refs) == 2

    def test_parse_bibtex_title(self, bibtex_references):
        refs = parse_references(bibtex_references)
        assert "Attention" in refs[0].candidate_title

    def test_parse_bibtex_doi(self, bibtex_references):
        refs = parse_references(bibtex_references)
        assert refs[0].doi == "10.48550/arXiv.1706.03762"

    def test_parse_bibtex_year(self, bibtex_references):
        refs = parse_references(bibtex_references)
        assert refs[0].year == 2017
        assert refs[1].year == 2019

    def test_parse_bibtex_authors(self, bibtex_references):
        refs = parse_references(bibtex_references)
        assert refs[0].authors_raw is not None
        assert "Vaswani" in refs[0].authors_raw


# ═══════════════════════════════════════════════════════════════
# RIS Format Parsing
# ═══════════════════════════════════════════════════════════════

class TestParseRIS:
    """Tests for RIS format parsing."""

    def test_parse_ris_count(self, ris_references):
        refs = parse_references(ris_references)
        assert len(refs) == 2

    def test_parse_ris_title(self, ris_references):
        refs = parse_references(ris_references)
        assert refs[0].candidate_title == "Attention Is All You Need"

    def test_parse_ris_doi(self, ris_references):
        refs = parse_references(ris_references)
        assert refs[0].doi == "10.48550/arXiv.1706.03762"

    def test_parse_ris_year(self, ris_references):
        refs = parse_references(ris_references)
        assert refs[0].year == 2017

    def test_parse_ris_authors(self, ris_references):
        refs = parse_references(ris_references)
        assert "Vaswani" in refs[0].authors_raw
        assert "Shazeer" in refs[0].authors_raw


# ═══════════════════════════════════════════════════════════════
# DOI Cleaning
# ═══════════════════════════════════════════════════════════════

class TestCleanDOI:
    """Tests for _clean_doi() edge cases."""

    def test_clean_trailing_period(self):
        assert _clean_doi("10.1234/test.") == "10.1234/test"

    def test_clean_trailing_comma(self):
        assert _clean_doi("10.1234/test,") == "10.1234/test"

    def test_clean_trailing_semicolon(self):
        assert _clean_doi("10.1234/test;") == "10.1234/test"

    def test_clean_balanced_parens(self):
        """DOI with balanced parentheses should keep them."""
        assert _clean_doi("10.1016/S0167-9236(02)00114-8") == \
               "10.1016/S0167-9236(02)00114-8"

    def test_clean_unbalanced_paren(self):
        """Trailing unbalanced paren should be stripped."""
        assert _clean_doi("10.1234/test)") == "10.1234/test"

    def test_clean_multiple_trailing(self):
        assert _clean_doi("10.1234/test.,;") == "10.1234/test"

    def test_clean_no_change_needed(self):
        assert _clean_doi("10.48550/arXiv.1706.03762") == \
               "10.48550/arXiv.1706.03762"

    def test_clean_trailing_quote(self):
        assert _clean_doi('10.1234/test"') == "10.1234/test"


# ═══════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════

class TestParserEdgeCases:
    """Tests for parser edge cases."""

    def test_empty_input(self):
        assert parse_references("") == []

    def test_whitespace_only(self):
        assert parse_references("   \n\n  ") == []

    def test_too_short_text(self):
        """Text shorter than 15 chars should be skipped."""
        refs = parse_references("short ref")
        assert len(refs) == 0

    def test_no_doi_reference(self):
        text = "Smith, J. (2020). A paper without any DOI. Some Journal, 5(2), 10-20."
        refs = parse_references(text)
        assert len(refs) >= 1
        assert refs[0].doi is None
        assert refs[0].year == 2020

    def test_doi_url_prefix_stripped(self):
        text = "[1]. Author (2020). Title. https://doi.org/10.1234/test.paper"
        refs = parse_references(text)
        assert refs[0].doi == "10.1234/test.paper"

    def test_doi_dx_prefix_stripped(self):
        text = "[1]. Author (2020). Title. https://dx.doi.org/10.1234/test.paper"
        refs = parse_references(text)
        assert refs[0].doi == "10.1234/test.paper"

    def test_multiple_formats_mixed(self):
        """References from a single line should still produce results."""
        text = "Author, A. (2020). Title one. doi:10.1234/one"
        refs = parse_references(text)
        assert len(refs) >= 1

    def test_year_range_validation(self):
        """Years outside valid range should not be extracted (bare year)."""
        text = "[1]. Author. Some reference from 1800 about something important."
        refs = parse_references(text)
        if refs and refs[0].year:
            assert 1900 <= refs[0].year <= 2030
