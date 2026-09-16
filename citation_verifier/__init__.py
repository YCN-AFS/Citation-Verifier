"""
Citation Verifier — Production-Ready Automated Citation Verification System.

A multi-API cross-referencing engine that verifies academic citations by
comparing user-provided references against authoritative metadata from
Crossref, DataCite, and OpenAlex.

Architecture:
    parser.py       → Splits raw text into structured references
    normalizer.py   → Standardizes strings for accurate comparison
    api_clients.py  → Resilient API clients with retry logic
    comparator.py   → Multi-scorer fuzzy matching engine
    verifier.py     → Core verification orchestrator
    reporter.py     → Rich CLI output and JSON report generation
"""

__version__ = "1.2.0"
__author__ = "Citation Verifier Team"
