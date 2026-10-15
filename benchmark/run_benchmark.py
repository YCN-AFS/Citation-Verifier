#!/usr/bin/env python3
"""
Run CiteGuard against benchmark/cases.jsonl and report accuracy.

Each case is verified on its own (so reference parsing is part of what is
measured). Uses an isolated temp cache, never the production databases.

Key safety metric: FALSE ACCEPTS — a case whose reference is wrong
(wrong_title / fake_doi / retracted / fake_title / fake_authors / fake_mixed) that came back VERIFIED
or TITLE_MATCHED. The README promises this is zero.

Usage:  python benchmark/run_benchmark.py [--limit N] [--json out.json]
"""

import argparse
import json
import sys
import tempfile
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from citation_verifier import cache  # noqa: E402
from citation_verifier.verifier import CitationVerifier  # noqa: E402

CASES = Path(__file__).parent / "cases.jsonl"
BAD_KINDS = {"wrong_title", "fake_doi", "retracted", "fake_title", "fake_authors", "fake_mixed"}
ACCEPT = {"VERIFIED", "TITLE_MATCHED"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, default=CASES)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--json")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="citeguard-bench-"))
    cache._DB_PATH = tmp / "cache.db"
    cache._local = threading.local()

    cases = [json.loads(line) for line in args.cases.open(encoding="utf-8")]
    if args.limit:
        cases = cases[: args.limit]

    def run(case):
        res = CitationVerifier(cross_validate=True).verify_text(case["text"])
        if len(res) != 1:
            return case, "PARSE_ERROR", None, f"parsed {len(res)} refs"
        r = res[0]
        score = r.comparison.final_score if r.comparison else None
        return case, r.verdict.value, score, r.error_message

    with ThreadPoolExecutor(max_workers=4) as ex:
        out = list(ex.map(run, cases))

    by_kind = defaultdict(Counter)
    wrong, false_accepts, false_rejects, api_errors = [], [], [], 0
    for case, got, score, msg in out:
        by_kind[case["kind"]][got] += 1
        if got == "API_ERROR":
            api_errors += 1
            continue
        if got in case["expected"]:
            continue
        wrong.append((case, got, score, msg))
        if case["kind"] in BAD_KINDS and got in ACCEPT:
            false_accepts.append((case, got, score))
        if case["kind"] not in BAD_KINDS and got in {"DEAD_DOI", "MISMATCH", "RETRACTED"}:
            false_rejects.append((case, got, score))

    decided = len(out) - api_errors
    correct = decided - len(wrong)
    print(f"\n{len(out)} cases | {api_errors} API_ERROR (excluded) | accuracy {correct}/{decided}"
          f" = {100 * correct / max(decided, 1):.1f}%\n")
    print(f"{'kind':<12} {'expected':<14} outcomes")
    for kind in dict.fromkeys(c["kind"] for c in cases):
        exp = next(c["expected"][0] for c in cases if c["kind"] == kind)
        print(f"{kind:<12} {exp:<14} {dict(by_kind[kind])}")
    print(f"\nFALSE ACCEPTS (bad reference passed):   {len(false_accepts)}")
    print(f"FALSE REJECTS (good reference flagged): {len(false_rejects)}")
    for case, got, score, msg in wrong[:25]:
        print(f"  - {case['id']:<16} expected {case['expected'][0]:<13} got {got:<13}"
              f" score={score if score is None else round(score, 1)}  {case['text'][:90]}")
    if args.json:
        Path(args.json).write_text(json.dumps(
            [{"id": c["id"], "kind": c["kind"], "expected": c["expected"], "got": g, "score": s}
             for c, g, s, _ in out], indent=1))
    return 1 if false_accepts else 0


if __name__ == "__main__":
    sys.exit(main())
