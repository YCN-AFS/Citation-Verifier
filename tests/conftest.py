"""
Shared fixtures for Citation Verifier test suite.

Provides reusable sample references, ground truth data,
and mock API responses for consistent testing across modules.
"""

import pytest

from citation_verifier.config import (
    ComparisonResult,
    GroundTruth,
    ParsedReference,
    Verdict,
    VerificationResult,
)


# ─── Sample References (various formats) ──────────────────────

@pytest.fixture
def apa_references():
    """APA-format reference block."""
    return (
        "Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., "
        "Gomez, A. N., Kaiser, Ł., & Polosukhin, I. (2017). Attention is all "
        "you need. Advances in Neural Information Processing Systems, 30. "
        "https://doi.org/10.48550/arXiv.1706.03762\n"
        "Devlin, J., Chang, M.-W., Lee, K., & Toutanova, K. (2019). BERT: "
        "Pre-training of deep bidirectional transformers for language understanding. "
        "Proceedings of NAACL-HLT. https://doi.org/10.18653/v1/N19-1423"
    )


@pytest.fixture
def ieee_references():
    """IEEE-format reference block."""
    return (
        "[1]. Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., "
        "Goyal, N., ... & Kiela, D. (2020). Retrieval-Augmented Generation for "
        "Knowledge-Intensive NLP Tasks. https://doi.org/10.48550/arXiv.2005.11401\n"
        "[2]. Brown, T., Mann, B., Ryder, N. (2020). Language models are few-shot "
        "learners. https://doi.org/10.48550/arXiv.2005.14165"
    )


@pytest.fixture
def bibtex_references():
    """BibTeX-format reference block."""
    return """@article{vaswani2017attention,
    title={Attention Is All You Need},
    author={Vaswani, Ashish and Shazeer, Noam and Parmar, Niki},
    year={2017},
    doi={10.48550/arXiv.1706.03762}
}

@inproceedings{devlin2019bert,
    title={BERT: Pre-training of Deep Bidirectional Transformers},
    author={Devlin, Jacob and Chang, Ming-Wei},
    year={2019},
    booktitle={NAACL-HLT},
    doi={10.18653/v1/N19-1423}
}"""


@pytest.fixture
def ris_references():
    """RIS-format reference block."""
    return """TY  - JOUR
AU  - Vaswani, Ashish
AU  - Shazeer, Noam
TI  - Attention Is All You Need
PY  - 2017
DO  - 10.48550/arXiv.1706.03762
ER  -

TY  - CONF
AU  - Devlin, Jacob
TI  - BERT: Pre-training of Deep Bidirectional Transformers
PY  - 2019
DO  - 10.18653/v1/N19-1423
ER  -"""


@pytest.fixture
def vancouver_references():
    """Vancouver-style numbered references."""
    return (
        "1. Vaswani A, Shazeer N, Parmar N. Attention is all you need. "
        "Advances in Neural Information Processing Systems. 2017;30. "
        "doi: 10.48550/arXiv.1706.03762\n"
        "2. Devlin J, Chang MW, Lee K. BERT: Pre-training of deep bidirectional "
        "transformers. NAACL-HLT. 2019. doi: 10.18653/v1/N19-1423"
    )


@pytest.fixture
def single_ref_text():
    """Single APA reference for simple tests."""
    return (
        "Vaswani, A., Shazeer, N. (2017). Attention is all you need. "
        "https://doi.org/10.48550/arXiv.1706.03762"
    )


# ─── Ground Truth Fixtures ────────────────────────────────────

@pytest.fixture
def ground_truth_attention():
    """Ground truth for 'Attention Is All You Need'."""
    return GroundTruth(
        doi="10.48550/arXiv.1706.03762",
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
        year=2017,
        source_journal="Advances in Neural Information Processing Systems",
        api_source="Crossref",
        is_retracted=False,
    )


@pytest.fixture
def ground_truth_retracted():
    """Ground truth for a retracted paper."""
    return GroundTruth(
        doi="10.1234/fake.retracted",
        title="A Study That Was Retracted",
        authors=["John Doe"],
        year=2015,
        source_journal="Fake Journal",
        api_source="Crossref",
        is_retracted=True,
    )


@pytest.fixture
def ground_truth_no_title():
    """Ground truth with missing title."""
    return GroundTruth(
        doi="10.1234/no-title",
        title=None,
        authors=["Jane Smith"],
        year=2020,
        api_source="DataCite",
    )


@pytest.fixture
def parsed_ref_with_doi():
    """ParsedReference with DOI."""
    return ParsedReference(
        raw_text="[1]. Vaswani, A. (2017). Attention is all you need. "
                 "https://doi.org/10.48550/arXiv.1706.03762",
        ref_number=1,
        doi="10.48550/arXiv.1706.03762",
        candidate_title="Attention is all you need",
        year=2017,
        authors_raw="Vaswani, A.",
    )


@pytest.fixture
def parsed_ref_no_doi():
    """ParsedReference without DOI."""
    return ParsedReference(
        raw_text="Vaswani, A. (2017). Attention is all you need.",
        ref_number=1,
        doi=None,
        candidate_title="Attention is all you need",
        year=2017,
        authors_raw="Vaswani, A.",
    )


# ─── Mock API Response Fixtures ───────────────────────────────

@pytest.fixture
def crossref_response_attention():
    """Mock Crossref API response for Attention paper."""
    return {
        "message": {
            "DOI": "10.48550/arXiv.1706.03762",
            "title": ["Attention Is All You Need"],
            "author": [
                {"given": "Ashish", "family": "Vaswani"},
                {"given": "Noam", "family": "Shazeer"},
                {"given": "Niki", "family": "Parmar"},
            ],
            "published-print": {"date-parts": [[2017]]},
            "container-title": ["Advances in Neural Information Processing Systems"],
        }
    }


@pytest.fixture
def crossref_response_retracted():
    """Mock Crossref API response for a retracted paper."""
    return {
        "message": {
            "DOI": "10.1234/retracted.paper",
            "title": ["RETRACTED: A Fraudulent Study"],
            "author": [{"given": "John", "family": "Doe"}],
            "issued": {"date-parts": [[2015]]},
            "update-to": [{"type": "retraction"}],
        }
    }


@pytest.fixture
def openalex_response_attention():
    """Mock OpenAlex API response for Attention paper."""
    return {
        "doi": "https://doi.org/10.48550/arXiv.1706.03762",
        "title": "Attention Is All You Need",
        "authorships": [
            {"author": {"display_name": "Ashish Vaswani"}},
            {"author": {"display_name": "Noam Shazeer"}},
        ],
        "publication_year": 2017,
        "primary_location": {
            "source": {"display_name": "Advances in Neural Information Processing Systems"}
        },
        "is_retracted": False,
    }
