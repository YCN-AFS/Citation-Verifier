#!/usr/bin/env python3
"""
Build a labeled benchmark of references from live Crossref data.

Every case has a known-correct expected outcome, derived from real
records (so labels are trustworthy), then optionally corrupted:

  good          real DOI + its true title                -> VERIFIED
  noisy         real DOI + case/punctuation-noised title -> VERIFIED
  wrong_title   real DOI + a different paper's title     -> MISMATCH
  fake_doi      plausible but non-existent DOI           -> DEAD_DOI
  retracted     DOI of a paper with a retraction notice  -> RETRACTED
  title_only    real title, no DOI                       -> TITLE_MATCHED
  fake_title    invented title, no DOI                   -> NO_DOI

Extra "hard" classes (--hard; no DOI, aimed at title-only matching):
  truncated_subtitle  real title minus subtitle, real authors -> TITLE_MATCHED
  fake_authors        real title/year/journal, invented authors -> NO_DOI
  fake_mixed          halves of two real titles + real authors of one -> NO_DOI

Usage:  python benchmark/build_benchmark.py [--per-class 30] [--seed 7]
Writes: benchmark/cases.jsonl
"""

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from citation_verifier.config import USER_AGENT  # noqa: E402

API = "https://api.crossref.org/works"
OUT = Path(__file__).parent / "cases.jsonl"
S = requests.Session()
S.headers["User-Agent"] = USER_AGENT


def get(url, **params):
    params["mailto"] = "citeguard@giize.com"
    for attempt in range(4):
        r = S.get(url, params=params, timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()["message"]
    raise RuntimeError(f"giving up on {url}")


def usable(item):
    t = (item.get("title") or [""])[0]
    year = ((item.get("issued") or {}).get("date-parts") or [[None]])[0][0]
    authors = item.get("author") or []
    return (
        item.get("type") == "journal-article"
        and 25 <= len(t) <= 220
        and year and authors and authors[0].get("family")
        and not t.lower().startswith(("retract", "withdraw", "erratum", "correction"))
        and item.get("DOI") and not item["DOI"].endswith(".")  # trailing dot is indistinguishable from punctuation
    )


def meta(item):
    authors = item["author"][:3]
    names = ", ".join(f"{a.get('family')}, {(a.get('given') or '?')[0]}." for a in authors)
    if len(item["author"]) > 3:
        names += ", et al."
    return {
        "doi": item["DOI"].lower(),
        "title": re.sub(r"\s+", " ", item["title"][0]).strip(),
        "year": item["issued"]["date-parts"][0][0],
        "authors": names,
        "journal": (item.get("container-title") or ["Journal"])[0],
    }


def ref_text(m, title=None, doi=True):
    s = f"{m['authors']} ({m['year']}). {title or m['title']}. {m['journal']}."
    if doi:
        s += f" https://doi.org/{m['doi']}"
    return s


def noise(title, rng):
    """Formatting noise a real student reference list would contain."""
    choice = rng.choice(["lower", "title_case", "no_punct", "spaces"])
    if choice == "lower":
        return title.lower()
    if choice == "title_case":
        return title.title()
    if choice == "no_punct":
        return re.sub(r"[:;,\-–—]", " ", title)
    return title.replace(" ", "  ")


def sample_real(n, rng):
    out, seen = [], set()
    while len(out) < n:
        for it in get(API, sample=100, filter="type:journal-article,from-pub-date:2005-01-01")["items"]:
            if usable(it) and it["DOI"].lower() not in seen:
                seen.add(it["DOI"].lower())
                out.append(it)
        time.sleep(0.3)
    rng.shuffle(out)
    return out[:n]


def sample_retracted(n):
    """Original papers that Crossref says were retracted."""
    out, cursor, seen = [], "*", set()
    while len(out) < n:
        msg = get(API, filter="update-type:retraction,type:journal-article", rows=100, cursor=cursor)
        if not msg["items"]:
            break
        cursor = msg["next-cursor"]
        for notice in msg["items"]:
            for upd in notice.get("update-to", []):
                if upd.get("type") != "retraction" or upd["DOI"].lower() in seen:
                    continue
                seen.add(upd["DOI"].lower())
                try:
                    orig = get(f"{API}/{upd['DOI']}")
                except requests.RequestException:
                    continue
                if usable(orig):
                    out.append(orig)
                time.sleep(0.2)
                if len(out) >= n:
                    return out
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--hard", action="store_true", help="build only the hard no-DOI classes")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    n, rng = args.per_class, random.Random(args.seed)

    cases = []

    def add(kind, expected, text, **extra):
        cases.append({"id": f"{kind}-{sum(c['kind'] == kind for c in cases) + 1:03d}",
                      "kind": kind, "expected": expected, "text": text, **extra})

    if args.hard:
        build_hard(cases, n, rng)
        write(cases, args.out)
        return

    pool = [meta(i) for i in sample_real(n * 5 + 5, rng)]
    it = iter(pool)

    for _ in range(n):
        m = next(it)
        add("good", ["VERIFIED"], ref_text(m), doi=m["doi"])
    for _ in range(n):
        m = next(it)
        add("noisy", ["VERIFIED"], ref_text(m, title=noise(m["title"], rng)), doi=m["doi"])
    for _ in range(n):
        m, other = next(it), next(it)
        add("wrong_title", ["MISMATCH"], ref_text(m, title=other["title"]), doi=m["doi"])
    for _ in range(n):
        m = next(it)
        fake = f"{m['doi'].split('/')[0]}/{''.join(rng.choices('abcdefghjkmnpqrstuvwxyz23456789', k=14))}"
        add("fake_doi", ["DEAD_DOI"], ref_text({**m, "doi": fake}), doi=fake)
    for o in sample_retracted(n):
        m = meta(o)
        add("retracted", ["RETRACTED"], ref_text(m), doi=m["doi"])

    # No-DOI cases (fresh pool so titles are not reused from the above)
    title_pool = [meta(i) for i in sample_real(n * 2, rng)]
    for m in title_pool[:n]:
        add("title_only", ["TITLE_MATCHED"], ref_text(m, doi=False))
    words = ["Quantum", "Neural", "Adaptive", "Distributed", "Probabilistic", "Hierarchical",
             "Stochastic", "Bayesian", "Topological", "Asymmetric", "Latent", "Federated"]
    nouns = ["manifolds", "lattices", "oscillators", "ensembles", "gradients", "kernels",
             "membranes", "tensors", "graphs", "cascades", "regimes", "invariants"]
    for _ in range(n):
        t = (f"{rng.choice(words)} {rng.choice(nouns)} and {rng.choice(words).lower()} "
             f"{rng.choice(nouns)} in {rng.choice(words).lower()} {rng.choice(nouns)}")
        add("fake_title", ["NO_DOI"],
            f"Nowak, K., Ivanova, P. ({rng.randint(2008, 2023)}). {t}. Journal of Imaginary Results.")

    write(cases, args.out)


def write(cases, out):
    with out.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    kinds = {}
    for c in cases:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    print(f"wrote {len(cases)} cases -> {out}\n{kinds}")


_SURNAMES = ["Nowak", "Ivanova", "Okafor", "Lindqvist", "Tanaka", "Moreau", "Haddad",
             "Petrov", "Santos", "Kowalski", "Ibrahim", "Johansson", "Chen", "Mukherjee"]


def _fake_authors(rng):
    names = rng.sample(_SURNAMES, 2)
    return f"{names[0]}, {rng.choice('ABCDEFGHJKLMNPRSTVW')}., {names[1]}, {rng.choice('ABCDEFGHJKLMNPRSTVW')}."


def build_hard(cases, n, rng):
    """No-DOI classes designed to tempt a title-only matcher."""
    def add(kind, expected, text):
        cases.append({"id": f"{kind}-{sum(c['kind'] == kind for c in cases) + 1:03d}",
                      "kind": kind, "expected": expected, "text": text})

    # Positive control: dropping the subtitle is common and must still verify.
    with_sub = [m for m in (meta(i) for i in sample_real(n * 12, rng))
                if ":" in m["title"] and len(m["title"].split(":")[0].split()) >= 4]
    for m in with_sub[:n]:
        add("truncated_subtitle", ["TITLE_MATCHED"], ref_text(m, title=m["title"].split(":")[0], doi=False))

    pool = [meta(i) for i in sample_real(n * 4, rng)]
    for m in pool[:n]:
        add("title_only", ["TITLE_MATCHED"], ref_text(m, doi=False))
    for m in pool[n:2 * n]:
        add("fake_authors", ["NO_DOI"], ref_text({**m, "authors": _fake_authors(rng)}, doi=False))
    for a, b in zip(pool[2 * n:3 * n], pool[3 * n:4 * n]):
        wa, wb = a["title"].split(), b["title"].split()
        mixed = " ".join(wa[: max(3, len(wa) // 2)] + wb[len(wb) // 2:])
        add("fake_mixed", ["NO_DOI"], ref_text({**a}, title=mixed, doi=False))


if __name__ == "__main__":
    main()
