# Benchmark results

210 labeled references (30 per class), built from live Crossref records by
`build_benchmark.py` and scored by `run_benchmark.py`. Re-run with
`python benchmark/run_benchmark.py`; the exit code is 1 if any bad reference is accepted.

| Class | Expected | Before fixes | After fixes |
|---|---|---|---|
| good | VERIFIED | 30/30 | 30/30 |
| noisy (case/punctuation) | VERIFIED | 30/30 | 30/30 |
| wrong_title (real DOI, another paper's title) | MISMATCH | 28/30 (2 → DEAD_DOI) | 29/29 |
| fake_doi | DEAD_DOI | 30/30 | 30/30 |
| retracted | RETRACTED | 30/30 | 30/30 |
| title_only (no DOI) | TITLE_MATCHED | 28/30 (2 → NO_DOI) | 30/30 |
| fake_title (no DOI) | NO_DOI | 30/30 | 29/30 (1 false accept) |
| **Overall** | | **206/210 = 98.1%** | **208/209 = 99.5%** |

One `wrong_title` case (a DOI that itself ends in ".") was removed from the set:
it is indistinguishable from sentence punctuation.

## Bugs found and fixed by the benchmark

1. DOIs containing `;` or `[...]` (SICI-style, e.g. BioOne/Wiley) were truncated → false DEAD_DOI.
2. Publisher markup in titles (`<i>`, `<sub>`, `<scp>`) broke fuzzy matching and caused OpenAlex HTTP 400.
3. urllib3 honoured an unbounded `Retry-After` on HTTP 429 and could block a worker for hours.
4. Crossref `date-parts: [[null]]` raised `TypeError`; for batches of ≤ 3 references it failed the whole request.

## Open weakness (not fixed here)

`fake_title-012`: the invented reference "Bayesian gradients and hierarchical regimes in
distributed tensors" (Nowak & Ivanova, 2015) was accepted as TITLE_MATCHED (85.7%) against
"Hierarchical Bayesian Models" (Hobbs & Hooten, 2015). Title-only matching ignores authors,
and `token_set_ratio` inflates scores when one title's words are a subset of the other.
Suggested fix: require author-surname overlap (or a higher score plus a year match) for TITLE_MATCHED.
