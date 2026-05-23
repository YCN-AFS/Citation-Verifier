<div align="center">

# 📚 Citation Verifier

### Automated Academic Citation Verification System

**Cross-reference citations against Crossref, DataCite & OpenAlex — detect fake DOIs, title mismatches, and metadata errors with zero false-positive tolerance.**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)
[![RapidFuzz](https://img.shields.io/badge/Fuzzy_Match-RapidFuzz-ff6b6b?style=for-the-badge)](https://github.com/rapidfuzz/RapidFuzz)
[![Flask](https://img.shields.io/badge/Web_UI-Flask-000000?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com)

</div>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔗 **Multi-API Cross-Referencing** | Queries Crossref → DataCite → OpenAlex with automatic routing & fallback |
| 🎯 **Zero False-Positive Architecture** | Conservative 90% threshold — never marks incorrect citations as correct |
| 🧠 **Multi-Scorer Fuzzy Matching** | Uses `ratio`, `token_sort_ratio`, and `token_set_ratio` from RapidFuzz (C++ backend) |
| 🔍 **Title-Based Search** | Handles references without DOIs via OpenAlex & Crossref title search |
| ✅ **Cross-Validation** | OpenAlex independently confirms results from Crossref/DataCite |
| 🌐 **Web UI** | Beautiful dark-theme interface with side-by-side comparison view |
| 📋 **Copy Corrected** | One-click copy of all corrected references or individual ones |
| 📊 **Rich CLI** | Color-coded terminal output with emoji verdicts and summary dashboard |
| 📄 **JSON Export** | Machine-readable report for CI/CD integration |
| 🔄 **Resilient Networking** | Exponential backoff retry, rate-limit handling (HTTP 429), connection pooling |

## 🖥️ Web Interface

<div align="center">

### Side-by-Side Comparison View

Compare your original citations against verified API data — mismatches highlighted in red, corrections in green.

> **Copy individual corrections** with per-card copy buttons, or **copy all corrected references** at once.

</div>

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Citation Verifier                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────────────┐ │
│  │  Parser   │───▶│  API Router  │───▶│  Crossref / DataCite /    │ │
│  │ (Regex)   │    │  (DOI-based) │    │  OpenAlex (REST APIs)     │ │
│  └──────────┘    └──────────────┘    └────────────────────────────┘ │
│       │                                          │                  │
│       ▼                                          ▼                  │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────────────┐ │
│  │Normalizer│───▶│  Comparator  │───▶│  Verdict Engine            │ │
│  │ (Unicode) │    │ (RapidFuzz)  │    │  (≥90% → ✅ VERIFIED)     │ │
│  └──────────┘    └──────────────┘    └────────────────────────────┘ │
│                                                  │                  │
│                                          ┌───────┴───────┐         │
│                                          ▼               ▼         │
│                                    ┌──────────┐   ┌───────────┐    │
│                                    │ Rich CLI │   │  Web UI   │    │
│                                    │ (stdout) │   │  (Flask)  │    │
│                                    └──────────┘   └───────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/YCN-AFS/Citation-Verifier.git
cd Citation-Verifier

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Web Interface (Recommended)

```bash
python webapp.py
# Open http://localhost:5000
```

### 3. Command Line

```bash
# From file
python main.py --file references.txt

# Direct text
python main.py --text "[1]. Author (2020). Title. https://doi.org/10.xxxx"

# With JSON export
python main.py --file references.txt --json report.json

# Disable cross-validation (faster)
python main.py --file references.txt --no-cross-validate
```

## 📊 Verdict System

| Verdict | Icon | Threshold | Meaning |
|---------|------|-----------|---------|
| **VERIFIED** | ✅ | ≥ 90% | Citation matches API data with high confidence |
| **SUSPICIOUS** | ⚠️ | 70-89% | Partial match — manual review recommended |
| **MISMATCH** | ❌ | < 70% | DOI resolves to a **different paper** |
| **DEAD DOI** | 💀 | N/A | DOI not found in any API |
| **TITLE MATCHED** | 📗 | ≥ 90% | No DOI, but title found via search |
| **NO DOI** | 🔍 | N/A | No DOI and title search inconclusive |

## 📁 Project Structure

```
Citation-Verifier/
├── citation_verifier/       # Core verification engine
│   ├── __init__.py
│   ├── config.py            # Thresholds, API endpoints, data classes
│   ├── parser.py            # Reference text parser (DOI, title, year extraction)
│   ├── normalizer.py        # Unicode & LaTeX normalization pipeline
│   ├── api_clients.py       # Crossref, DataCite, OpenAlex REST clients
│   ├── comparator.py        # Multi-scorer fuzzy matching engine
│   ├── verifier.py          # Core orchestrator
│   └── reporter.py          # Rich CLI output & JSON generator
├── templates/
│   └── index.html           # Web UI template
├── static/
│   ├── style.css            # Dark theme styles
│   └── app.js               # Frontend logic
├── main.py                  # CLI entry point
├── webapp.py                # Flask web server
├── requirements.txt         # Python dependencies
├── test_references.txt      # Sample test data (40 references)
└── README.md
```

## 🔧 Dependencies

| Package | Purpose |
|---------|---------|
| `requests` | HTTP client for API calls |
| `rapidfuzz` | High-performance fuzzy string matching (C++ backend) |
| `rich` | Beautiful terminal output |
| `flask` | Web UI server |

## 🔌 APIs Used

| API | Purpose | Rate Limit |
|-----|---------|------------|
| [Crossref](https://api.crossref.org) | Journal/conference DOI resolution | Polite pool (with mailto) |
| [DataCite](https://api.datacite.org) | arXiv/preprint DOI resolution | Public |
| [OpenAlex](https://api.openalex.org) | Cross-validation & title search | Polite pool (with mailto) |

> **Note:** No API keys required. The system uses the polite pools of Crossref and OpenAlex for better performance.

## 📝 Example Output

```
══════════════════════════════════════════════════════════════════════

  ✅ Ref [2] — VERIFIED
     DOI: 10.48550/arXiv.2005.11401
     Cited Title: Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks
     API Title:   Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks (DataCite)
     Scores: ratio=100.0 | token_sort=100.0 | token_set=100.0 → final=100.0%
     Year: ✓ (cited=2020, actual=2020)
     Cross-validated: ✓ Confirmed by OpenAlex

  ❌ Ref [12] — MISMATCH
     DOI: 10.1109/IRASET57153.2023.10153005
     Cited Title: AI-based anomaly detection: Challenges and solutions...
     API Title:   Building Intelligent Chatbots: Tools, Technologies... (Crossref)
     Scores: ratio=30.2 | token_sort=35.1 | token_set=44.0 → final=44.0%
     Year: ✓ (cited=2023, actual=2023)
     ⚠ DOI points to a DIFFERENT paper!

══════════════════════════════════════════════════════════════════════

            📊 Verification Summary
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃  Verdict           ┃  Count  ┃  Percentage  ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━┩
│  ✅ VERIFIED       │     27  │       67.5%  │
│  ⚠️ SUSPICIOUS     │      3  │        7.5%  │
│  ❌ MISMATCH       │      1  │        2.5%  │
│  🔍 NO DOI         │      6  │       15.0%  │
│  📗 TITLE MATCHED  │      3  │        7.5%  │
└────────────────────┴─────────┴──────────────┘
```

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with ❤️ for academic integrity**

*If this tool helped you, consider giving it a ⭐*

</div>
