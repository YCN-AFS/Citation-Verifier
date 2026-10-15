# Benchmark results

210 labeled references (30 per class), built from live Crossref records by
`build_benchmark.py` and scored by `run_benchmark.py`. Re-run with
`python benchmark/run_benchmark.py`; the exit code is 1 if any bad reference is accepted.

| Class | Expected | Before fixes | After parser/API fixes | After TITLE_MATCHED hardening |
|---|---|---|---|---|
| good | VERIFIED | 30/30 | 30/30 | 30/30 |
| noisy (case/punctuation) | VERIFIED | 30/30 | 30/30 | 30/30 |
| wrong_title (real DOI, another paper's title) | MISMATCH | 28/30 (2 → DEAD_DOI) | 29/29 | 29/29 |
| fake_doi | DEAD_DOI | 30/30 | 30/30 | 30/30 |
| retracted | RETRACTED | 30/30 | 30/30 | 30/30 |
| title_only (no DOI) | TITLE_MATCHED | 28/30 (2 → NO_DOI) | 30/30 | 30/30 |
| fake_title (no DOI) | NO_DOI | 30/30 | 29/30 (1 false accept) | 30/30 |
| **Overall** | | **206/210 = 98.1%** | **208/209 = 99.5%** | **209/209 = 100%** |

One `wrong_title` case (a DOI that itself ends in ".") was removed from the set:
it is indistinguishable from sentence punctuation.

## Bugs found and fixed by the benchmark

1. DOIs containing `;` or `[...]` (SICI-style, e.g. BioOne/Wiley) were truncated → false DEAD_DOI.
2. Publisher markup in titles (`<i>`, `<sub>`, `<scp>`) broke fuzzy matching and caused OpenAlex HTTP 400.
3. urllib3 honoured an unbounded `Retry-After` on HTTP 429 and could block a worker for hours.
4. Crossref `date-parts: [[null]]` raised `TypeError`; for batches of ≤ 3 references it failed the whole request.

## TITLE_MATCHED hardening (fixes the false accept)

`fake_title-012` ("Bayesian gradients and hierarchical regimes in distributed tensors",
Nowak & Ivanova) had been accepted against "Hierarchical Bayesian Models" (Hobbs & Hooten)
at 85.7%. A DOI-less match is now confirmed only if all hold (`comparator.confirm_title_only_match`):

1. overall score ≥ 85;
2. max(ratio, token_sort) ≥ 80, because `token_set_ratio` alone is inflated when one title's
   words are a subset of the other's;
3. at least one author surname agrees; if the citation lists no authors, the title must be
   near-exact (score ≥ 95, strict ≥ 90);
4. years differ by ≤ 1 (≤ 3 when authors agree, to allow online-first vs print dates).

Rule 2 is waived for a dropped-subtitle citation only when authors AND year agree and both
titles have ≥ 4 words.

## Caveats on the 100%

* Two of the relaxations (rule 4's wider gap, the dropped-subtitle waiver) were written after
  seeing the two benchmark cases they fix, so the title_only result is partly fitted to this set.
  They were added only where independent evidence (matching authors, year) exists, and each has
  its own unit tests, but a fresh sample (`build_benchmark.py --seed N`) is the real test.
* `fake_title` uses random-word titles with invented authors — a weak adversary. Realistic
  fabrications (a plausible title plus the real authors of a *different* paper) are not covered yet.
* OpenAlex returned HTTP 429 on many title searches during the runs; the system fell back to
  Crossref, so results are unaffected, but search results are not cached yet.

## Fresh sample and harder adversaries

Datasets: `cases.jsonl` (original, seed 7), `cases_seed101.jsonl` (fresh Crossref sample, same classes),
`cases_hard.jsonl` (`--hard`: no-DOI classes aimed at title-only matching). Run any of them with
`run_benchmark.py --cases <file>`.

First run on the new sets exposed what the original set could not:

| Set | Accuracy | False accepts | Notes |
|---|---|---|---|
| seed101 (210) | 209/210 = 99.5% | 0 | the original 100% was partly fitted; a fresh sample holds up |
| hard (120) | 108/120 = 90.0% | **2** (`fake_authors`) | see below |

Causes of the two false accepts, both real design gaps:

* `fake_authors-023`: "Chen" is a common surname that happened to be *later* in the real author list, so
  "any surname matches" validated an invented first author. → the **cited first author** must now be one of
  the record's authors (`comparator._cited_first_surname`, order- and initials-tolerant).
* `fake_authors-029`: the matching Crossref record had no author data, so invented authors went unchecked and
  a near-exact title alone was enough. → a citation that names authors is **no longer confirmed by a record
  without author data**.

Recall: 8 of 10 `truncated_subtitle` misses were not bugs — the search engine ranked a different paper first.
The verifier now evaluates **every candidate** from OpenAlex then Crossref (`search_candidates`) and keeps the
first one that can be confirmed, instead of judging only the top hit.

After these changes:

| Set | Accuracy | False accepts | False rejects |
|---|---|---|---|
| original (209) | 209/209 = 100% | 0 | 0 |
| seed101 (210) | 209/210 = 99.5% | 0 | 0 |
| hard (120) | 114/120 = 95.0% | 0 | 0 |

Remaining misses are all "could not confirm" (NO_DOI), never wrong acceptance. Known causes:
the cited truncated title is too generic for the right paper to be among the top candidates,
the found record lists different authors, or a title-search request was rate-limited
(`title_only-007` in the hard set: Crossref and OpenAlex both returned HTTP 429, and a failed
search currently reports NO_DOI rather than API_ERROR).
