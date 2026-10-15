"""Rebuild benchmark/summary.json from raw run results.

Usage:
    python benchmark/run_benchmark.py --json /tmp/res_original.json
    python benchmark/run_benchmark.py --cases benchmark/cases_seed101.jsonl --json /tmp/res_fresh.json
    python benchmark/run_benchmark.py --cases benchmark/cases_hard.jsonl --json /tmp/res_hard.json
    python benchmark/make_summary.py original=/tmp/res_original.json fresh=/tmp/res_fresh.json hard=/tmp/res_hard.json

Labels and caveats are kept from the existing summary.json; counts, date and code
version are recomputed. API_ERROR outcomes count as "not correct" and are recorded
in `api_errors`, so an incomplete run can never look better than it is.
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
BAD_KINDS = {"wrong_title", "fake_doi", "retracted", "fake_title", "fake_authors", "fake_mixed"}
ACCEPT = {"VERIFIED", "TITLE_MATCHED"}
REJECT = {"DEAD_DOI", "MISMATCH", "RETRACTED"}


def main(argv):
    summary_path = HERE / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    results = dict(a.split("=", 1) for a in argv)
    sets = {s["id"]: s for s in summary["sets"]}
    if set(results) != set(sets):
        sys.exit(f"need results for exactly {sorted(sets)}")

    for sid, path in results.items():
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        s = sets[sid]
        s["false_accepts"] = sum(r["kind"] in BAD_KINDS and r["got"] in ACCEPT for r in rows)
        s["false_rejects"] = sum(r["kind"] not in BAD_KINDS and r["got"] in REJECT for r in rows)
        s["api_errors"] = sum(r["got"] == "API_ERROR" for r in rows)
        for c in s["classes"]:
            of_kind = [r for r in rows if r["kind"] == c["kind"]]
            c["total"] = len(of_kind)
            c["correct"] = sum(r["got"] in r["expected"] for r in of_kind)

    summary["measured_on"] = date.today().isoformat()
    summary["code_version"] = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=HERE, text=True).strip()
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for s in summary["sets"]:
        ok = sum(c["correct"] for c in s["classes"])
        n = sum(c["total"] for c in s["classes"])
        print(f"{s['id']:<9} {ok}/{n}  false_accepts={s['false_accepts']} "
              f"false_rejects={s['false_rejects']} api_errors={s['api_errors']}")


if __name__ == "__main__":
    main(sys.argv[1:])
