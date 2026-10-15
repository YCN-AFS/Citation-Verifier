"""Benchmark summary: consistency, API endpoint, and agreement with README."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SUMMARY = ROOT / "benchmark" / "summary.json"


@pytest.fixture(scope="module")
def summary():
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


class TestSummaryFile:
    def test_counts_are_sane(self, summary):
        for s in summary["sets"]:
            assert s["false_accepts"] >= 0 and s["false_rejects"] >= 0
            for c in s["classes"]:
                assert 0 <= c["correct"] <= c["total"], c
                assert c["label_vi"] and c["label_en"] and c["expected"]

    def test_class_totals_match_case_files(self, summary):
        """Totals in summary.json must equal the real number of cases per class."""
        files = {"original": "cases.jsonl", "fresh": "cases_seed101.jsonl", "hard": "cases_hard.jsonl"}
        for s in summary["sets"]:
            rows = [json.loads(line) for line in (ROOT / "benchmark" / files[s["id"]]).open(encoding="utf-8")]
            for c in s["classes"]:
                assert sum(r["kind"] == c["kind"] for r in rows) == c["total"], (s["id"], c["kind"])
            assert len(rows) == sum(c["total"] for c in s["classes"])

    def test_unique_references_matches_data(self, summary):
        texts = set()
        for f in ("cases.jsonl", "cases_seed101.jsonl", "cases_hard.jsonl"):
            texts |= {json.loads(line)["text"] for line in (ROOT / "benchmark" / f).open(encoding="utf-8")}
        assert len(texts) == summary["unique_references"]

    def test_misses_are_never_claimed_as_wrong_acceptances(self, summary):
        # a set with partial classes but 0 false accepts/rejects must be said so explicitly
        assert any(c["correct"] < c["total"] for s in summary["sets"] for c in s["classes"])
        assert all(s["false_accepts"] == 0 for s in summary["sets"])


class TestGeneratedArtifacts:
    """The README benchmark block is generated from summary.json."""

    @pytest.fixture(scope="class")
    def renderer(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("render_readme", ROOT / "benchmark" / "render_readme.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_readme_block_is_up_to_date(self, summary, renderer):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        assert renderer.render_block(summary) in readme, "run: python benchmark/render_readme.py"

    def test_published_run_had_no_api_errors(self, summary):
        # an API_ERROR counts as "not correct"; a published run must not hide behind them
        assert all(s.get("api_errors", 0) == 0 for s in summary["sets"])

    def test_caveats_do_not_claim_stale_measurements(self, summary):
        text = " ".join(summary["caveats_vi"] + summary["caveats_en"]).lower()
        assert "not been re-measured" not in text and "chưa đo lại" not in text


class TestEndpoint:
    @pytest.fixture
    def client(self):
        import webapp
        webapp.app.config["TESTING"] = True
        return webapp.app.test_client()

    def test_returns_derived_totals(self, client, summary):
        r = client.get("/api/benchmark")
        assert r.status_code == 200
        body = r.get_json()
        total = sum(c["total"] for s in summary["sets"] for c in s["classes"])
        ok = sum(c["correct"] for s in summary["sets"] for c in s["classes"])
        assert body["totals"]["cases"] == total
        assert body["totals"]["correct"] == ok
        assert body["totals"]["accuracy"] == round(100 * ok / total, 1)
        assert body["totals"]["false_accepts"] == 0
        assert "max-age" in r.headers["Cache-Control"]

    def test_missing_file_is_404(self, client, monkeypatch, tmp_path):
        import webapp
        monkeypatch.setattr(webapp, "_BENCHMARK_FILE", tmp_path / "nope.json")
        assert client.get("/api/benchmark").status_code == 404


class TestReadmeAgrees:
    def test_headline_numbers_in_readme(self, summary):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        total = sum(c["total"] for s in summary["sets"] for c in s["classes"])
        ok = sum(c["correct"] for s in summary["sets"] for c in s["classes"])
        assert f"**{ok}/{total} = {100 * ok / total:.1f}%**" in readme
        fa = sum(x["false_accepts"] for x in summary["sets"])
        assert f"with {fa} wrong acceptances" in readme
        assert f"{summary['unique_references']} distinct references" in readme
        for s in summary["sets"]:
            for c in s["classes"]:
                assert f"| {c['label_en']} | `{c['expected']}` | {c['correct']}/{c['total']} |" in readme

    def test_ui_has_panel_and_loader(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        assert 'id="benchSection"' in html
        assert "/api/benchmark" in js and "renderBenchmark" in js
        assert re.search(r"textContent", js)   # data is rendered as text, not HTML
        assert 'id="benchRingFg"' in html
