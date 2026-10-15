#!/usr/bin/env python3
"""
Citation Verifier — Web Application.

A Flask-based web interface for the Automated Citation Verification System.
Provides a visual, interactive UI with side-by-side comparison of
cited text vs ground truth.
"""

import logging
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from flask import Flask, g, jsonify, render_template, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

from citation_verifier import __version__, jobs
from citation_verifier.config import MAX_REFERENCES, Verdict
from citation_verifier.history import (
    clear_all_sessions,
    delete_session,
    get_session,
    list_sessions,
    save_session,
)
from citation_verifier.stats import get_stats, increment_stats
from citation_verifier.verifier import CitationVerifier

app = Flask(__name__, template_folder="templates", static_folder="static")

# Behind Nginx Proxy Manager (the only host that can reach the bind address):
# trust exactly one proxy hop so rate limiting sees the real client IP.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# ─── Security: CORS ──────────────────────────────────────────
CORS(app, resources={
    r"/api/*": {
        "origins": ["https://citeguard.giize.com", "http://localhost:5000"],
        "methods": ["GET", "POST", "DELETE"],
        "max_age": 3600,
    }
})

# ─── Security: Rate Limiting ─────────────────────────────────
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"],
    storage_uri="memory://",
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ─── Anonymous per-browser identity (scopes verification history) ───
_SID_COOKIE = "cg_sid"
_SID_RE = re.compile(r"^[0-9a-f]{32}$")
_SID_MAX_AGE = 365 * 86400


def _owner() -> str:
    """Return this browser's anonymous id, minting one if absent/invalid."""
    sid = request.cookies.get(_SID_COOKIE, "")
    if _SID_RE.match(sid):
        return sid
    if "new_sid" not in g:
        g.new_sid = secrets.token_hex(16)
    return g.new_sid


@app.after_request
def _set_sid_cookie(resp):
    sid = g.get("new_sid")
    if sid:
        resp.set_cookie(_SID_COOKIE, sid, max_age=_SID_MAX_AGE,
                        httponly=True, samesite="Lax")
    return resp


@app.route("/")
@limiter.exempt
def index():
    """Serve the main web interface."""
    return render_template("index.html")


@app.route("/api/stats")
def stats():
    """Return global usage statistics for the hero counter."""
    return jsonify(get_stats())


@app.route("/api/health")
def health():
    """Health check endpoint for monitoring."""
    from citation_verifier.cache import get_cache_stats
    return jsonify({
        "status": "healthy",
        "version": __version__,
        "cache": get_cache_stats(),
        "stats": get_stats(),
    })


def _validate_request():
    """Validate a verification request body.

    Returns ``(text, cross_validate, error_response)``; on failure the
    first two are None and ``error_response`` is a ready Flask response.
    """
    data = request.get_json(silent=True)
    if not data or "text" not in data or not isinstance(data["text"], str):
        return None, None, (jsonify({"error": "Missing 'text' field in request body."}), 400)

    text = data["text"].strip()
    if not text:
        return None, None, (jsonify({"error": "Empty reference text."}), 400)

    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return None, None, (jsonify({"error": "Invalid text encoding. UTF-8 required."}), 400)

    # Limit input size to prevent abuse (max ~100KB or ~200 references)
    if len(text) > 100_000:
        return None, None, (jsonify({"error": "Input too large. Maximum 100,000 characters."}), 400)

    # Estimate reference count (rough: one per non-empty line or DOI)
    line_count = len([ln for ln in text.split("\n") if ln.strip()])
    if line_count > MAX_REFERENCES:
        return None, None, (jsonify({
            "error": f"Too many references (~{line_count}). Maximum {MAX_REFERENCES}."
        }), 400)

    return text, bool(data.get("cross_validate", True)), None


def _run_verification(text, cross_validate, owner, progress_cb=None):
    """Verify, record stats, save to history and return the response dict."""
    verifier = CitationVerifier(cross_validate=cross_validate)
    results = verifier.verify_text(text, progress_cb=progress_cb)
    increment_stats(len(results))
    response = _serialize_results(results)
    save_session(
        total=response["total"],
        summary=response["summary"],
        has_critical=response["has_critical"],
        input_text=text,
        results_data=response,
        owner=owner,
    )
    return response


@app.route("/api/verify", methods=["POST"])
@limiter.limit("10 per minute")
def verify():
    """
    Synchronous verification (kept for scripts / CI).

    Expects JSON body: { "text": "reference text..." }
    Returns JSON with verification results. The web UI uses /api/jobs.
    """
    text, cross_validate, err = _validate_request()
    if err:
        return err
    try:
        return jsonify(_run_verification(text, cross_validate, _owner()))
    except Exception as e:
        logger.error("Verification error: %s", e, exc_info=True)
        return jsonify({"error": f"Verification failed: {str(e)}"}), 500


# ─── Asynchronous jobs (progress + no request-long worker blocking) ───

# Per-process pool: bounds concurrent verifications on this worker.
_job_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="verify-job")
MAX_ACTIVE_JOBS_PER_USER = 2


def _job_worker(job_id, text, cross_validate, owner):
    try:
        response = _run_verification(
            text, cross_validate, owner,
            progress_cb=lambda done, total: jobs.update_progress(job_id, done, total),
        )
        jobs.finish(job_id, response)
    except Exception as e:
        logger.error("Job %s failed: %s", job_id, e, exc_info=True)
        jobs.fail(job_id, f"Verification failed: {e}")


@app.route("/api/jobs", methods=["POST"])
@limiter.limit("10 per minute")
def job_create():
    """Start a verification job. Returns 202 with the job id to poll."""
    text, cross_validate, err = _validate_request()
    if err:
        return err
    owner = _owner()
    if jobs.count_active(owner) >= MAX_ACTIVE_JOBS_PER_USER:
        return jsonify({"error": "Too many verifications in progress. Please wait."}), 429
    job_id = jobs.create_job(owner)
    _job_pool.submit(_job_worker, job_id, text, cross_validate, owner)
    return jsonify({"id": job_id}), 202


@app.route("/api/jobs/<job_id>")
@limiter.exempt
def job_status(job_id):
    """Poll a job: {status: running|done|failed, done, total, result?}."""
    job = jobs.get_job(job_id, _owner())
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


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
                "is_retracted": r.ground_truth.is_retracted,
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
            r.verdict in (Verdict.MISMATCH, Verdict.DEAD_DOI, Verdict.RETRACTED)
            for r in results
        ),
        "results": serialized,
    }


# ─── History API ──────────────────────────────────────────────

@app.route("/api/history")
def history_list():
    """List recent verification sessions."""
    return jsonify(list_sessions(_owner(), limit=20))


@app.route("/api/history/<session_id>")
def history_get(session_id):
    """Get full results for a specific session."""
    result = get_session(session_id, _owner())
    if result is None:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(result)


@app.route("/api/history/<session_id>", methods=["DELETE"])
def history_delete(session_id):
    """Delete a specific session."""
    delete_session(session_id, _owner())
    return jsonify({"ok": True})


@app.route("/api/history", methods=["DELETE"])
def history_clear():
    """Clear all history."""
    clear_all_sessions(_owner())
    return jsonify({"ok": True})


# ─── Maintenance API ─────────────────────────────────────────

@app.route("/api/cache/cleanup", methods=["POST"])
@limiter.limit("2 per hour")
def cache_cleanup():
    """Purge expired cache entries and old history sessions."""
    from citation_verifier.cache import cleanup_expired
    from citation_verifier.history import cleanup_old_sessions

    cache_result = cleanup_expired()
    history_result = cleanup_old_sessions()

    return jsonify({
        "cache": cache_result,
        "history": history_result,
        "jobs": {"removed": jobs.cleanup()},
    })


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=5000)
