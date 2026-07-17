"""
Central configuration for the Citation Verification System.

All tunable parameters — API endpoints, timeouts, retry policies,
fuzzy-matching thresholds — are defined here as module-level constants.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────────────────────────────
# Verification Verdicts
# ─────────────────────────────────────────────────────────────────────

class Verdict(Enum):
    """Classification of a citation verification result."""
    VERIFIED = "VERIFIED"           # Title matches ground truth (≥ 90%)
    SUSPICIOUS = "SUSPICIOUS"       # Possible formatting diff (70-89%)
    MISMATCH = "MISMATCH"           # DOI resolves to a different paper (< 70%)
    DEAD_DOI = "DEAD_DOI"           # DOI returns 404 / does not exist
    NO_DOI = "NO_DOI"               # No DOI found in the reference
    API_ERROR = "API_ERROR"         # All API attempts failed
    TITLE_MATCHED = "TITLE_MATCHED" # No DOI, but title search found a match


# ─────────────────────────────────────────────────────────────────────
# Fuzzy Matching Thresholds (Conservative — zero false-positive bias)
# ─────────────────────────────────────────────────────────────────────

THRESHOLD_VERIFIED = 90     # Score ≥ 90 → VERIFIED
THRESHOLD_SUSPICIOUS = 70   # Score 70–89 → SUSPICIOUS (manual review)
                            # Score < 70  → MISMATCH


# ─────────────────────────────────────────────────────────────────────
# API Configuration
# ─────────────────────────────────────────────────────────────────────

# Polite pool email — set CITEGUARD_MAILTO env var for production
_MAILTO = os.getenv("CITEGUARD_MAILTO", "citeguard@giize.com")

# Crossref (primary for journal/conference DOIs)
CROSSREF_API_BASE = "https://api.crossref.org/works"
CROSSREF_MAILTO = _MAILTO

# DataCite (primary for arXiv / preprint DOIs)
DATACITE_API_BASE = "https://api.datacite.org/dois"

# OpenAlex (cross-validator and fallback for title search)
OPENALEX_API_BASE = "https://api.openalex.org/works"
OPENALEX_MAILTO = _MAILTO

# DOI prefix routing: DOIs starting with these prefixes → DataCite
DATACITE_DOI_PREFIXES = ("10.48550",)  # arXiv


# ─────────────────────────────────────────────────────────────────────
# Network Resilience
# ─────────────────────────────────────────────────────────────────────

REQUEST_TIMEOUT = 15            # Seconds per HTTP request
MAX_RETRIES = 3                 # Number of retry attempts
RETRY_BACKOFF_FACTOR = 1.0      # Exponential backoff: 1s, 2s, 4s
RATE_LIMIT_DELAY = 0.35         # Seconds between API calls (per API)
RATE_LIMIT_429_WAIT = 5.0       # Seconds to wait on HTTP 429


# ─────────────────────────────────────────────────────────────────────
# User-Agent
# ─────────────────────────────────────────────────────────────────────

USER_AGENT = (
    f"CitationVerifier/1.0.0 "
    f"(https://github.com/citation-verifier; mailto:{CROSSREF_MAILTO})"
)


# ─────────────────────────────────────────────────────────────────────
# Data Classes for Structured Data Flow
# ─────────────────────────────────────────────────────────────────────

@dataclass
class ParsedReference:
    """A single reference extracted from the input text."""
    raw_text: str
    ref_number: Optional[int] = None
    doi: Optional[str] = None
    candidate_title: Optional[str] = None
    year: Optional[int] = None
    authors_raw: Optional[str] = None


@dataclass
class GroundTruth:
    """Authoritative metadata retrieved from an academic API."""
    doi: Optional[str] = None
    title: Optional[str] = None
    authors: list = field(default_factory=list)
    year: Optional[int] = None
    source_journal: Optional[str] = None
    api_source: str = ""  # "Crossref", "DataCite", "OpenAlex"


@dataclass
class ComparisonResult:
    """Result of comparing a cited reference against ground truth."""
    ratio_score: float = 0.0
    token_sort_score: float = 0.0
    token_set_score: float = 0.0
    final_score: float = 0.0
    year_match: Optional[bool] = None
    verdict: Verdict = Verdict.API_ERROR


@dataclass
class VerificationResult:
    """Complete verification result for a single reference."""
    reference: ParsedReference = field(default_factory=ParsedReference)
    ground_truth: Optional[GroundTruth] = None
    comparison: Optional[ComparisonResult] = None
    verdict: Verdict = Verdict.API_ERROR
    error_message: Optional[str] = None
    cross_validated: bool = False  # True if OpenAlex confirmed the result
