#!/usr/bin/env python3
"""
Citation Verifier — Web Application.

A Flask-based web interface for the Automated Citation Verification System.
Provides a visual, interactive UI with side-by-side comparison of
cited text vs ground truth.
"""

import json
import logging
from datetime import datetime

from flask import Flask, jsonify, render_template, request

from citation_verifier.config import Verdict, VerificationResult
from citation_verifier.verifier import CitationVerifier

app = Flask(__name__, template_folder="templates", static_folder="static")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@app.route("/")
def index():
    """Serve the main web interface."""
    return render_template("index.html")


@app.route("/api/verify", methods=["POST"])
def verify():
    """
    API endpoint for citation verification.

    Expects JSON body: { "text": "reference text..." }
    Returns JSON with verification results.
    """
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field in request body."}), 400

    text = data["text"].strip()
    if not text:
        return jsonify({"error": "Empty reference text."}), 400

    cross_validate = data.get("cross_validate", True)

    try:
        verifier = CitationVerifier(cross_validate=cross_validate)
        results = verifier.verify_text(text)
        return jsonify(_serialize_results(results))
    except Exception as e:
        logger.error("Verification error: %s", e, exc_info=True)
        return jsonify({"error": f"Verification failed: {str(e)}"}), 500


def _serialize_results(results: list) -> dict:
    """Serialize verification results for the web API."""
    # Summary counts
    counts = {}
    for v in Verdict:
        count = sum(1 for r in results if r.verdict == v)
        if count > 0:
            counts[v.value] = count

    serialized = []
    for r in results:
        entry = {
            "ref_number": r.reference.ref_number,
            "verdict": r.verdict.value,
            "doi": r.reference.doi,
            "cited_title": r.reference.candidate_title,
            "cited_year": r.reference.year,
            "cited_authors": r.reference.authors_raw,
            "raw_text": r.reference.raw_text,
        }

        if r.ground_truth:
            entry["ground_truth"] = {
                "title": r.ground_truth.title,
                "authors": r.ground_truth.authors[:8],
                "year": r.ground_truth.year,
                "source_journal": r.ground_truth.source_journal,
                "doi": r.ground_truth.doi,
                "api_source": r.ground_truth.api_source,
            }

        if r.comparison:
            entry["scores"] = {
                "ratio": round(r.comparison.ratio_score, 1),
                "token_sort": round(r.comparison.token_sort_score, 1),
                "token_set": round(r.comparison.token_set_score, 1),
                "final": round(r.comparison.final_score, 1),
                "year_match": r.comparison.year_match,
            }

        entry["cross_validated"] = r.cross_validated
        if r.error_message:
            entry["error"] = r.error_message

        serialized.append(entry)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(results),
        "summary": counts,
        "has_critical": any(
            r.verdict in (Verdict.MISMATCH, Verdict.DEAD_DOI)
            for r in results
        ),
        "results": serialized,
    }


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
