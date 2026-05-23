#!/usr/bin/env python3
"""
Citation Verifier — CLI Entry Point.

Automated Citation Verification System that cross-references academic
citations against Crossref, DataCite, and OpenAlex to detect mismatches,
fake DOIs, and incorrect metadata.

Usage:
    python main.py --file references.txt          # From file
    python main.py --text "Lewis, P. ... (2020)"  # Inline text
    python main.py                                 # Interactive stdin
    python main.py --file refs.txt --json report.json  # With JSON export

Exit codes:
    0 — All citations verified (or only suspicious ones)
    1 — At least one MISMATCH or DEAD DOI detected
"""

import argparse
import logging
import sys

from citation_verifier.config import Verdict
from citation_verifier.reporter import print_results, save_json_report
from citation_verifier.verifier import CitationVerifier


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="🔍 Automated Citation Verification System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --file references.txt
  python main.py --file refs.txt --json report.json
  python main.py --text "[1]. Lewis, P. (2020). Retrieval-Augmented Generation..."
  echo "..." | python main.py
        """,
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="Path to a text file containing references.",
    )
    parser.add_argument(
        "--text", "-t",
        type=str,
        help="Inline reference text (wrap in quotes).",
    )
    parser.add_argument(
        "--json", "-j",
        type=str,
        default=None,
        help="Save JSON report to this file path.",
    )
    parser.add_argument(
        "--no-cross-validate",
        action="store_true",
        help="Disable OpenAlex cross-validation (faster, less thorough).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging.",
    )

    args = parser.parse_args()

    # ── Configure Logging ─────────────────────────────────────────────
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── Read Input ────────────────────────────────────────────────────
    text = _read_input(args)
    if not text:
        parser.print_help()
        print("\n❌ Error: No input provided. Use --file, --text, or pipe via stdin.")
        sys.exit(1)

    # ── Run Verification ──────────────────────────────────────────────
    cross_validate = not args.no_cross_validate
    verifier = CitationVerifier(cross_validate=cross_validate)

    try:
        results = verifier.verify_text(text)
    except KeyboardInterrupt:
        print("\n⚠️ Verification interrupted by user.")
        sys.exit(130)

    # ── Output Results ────────────────────────────────────────────────
    print_results(results)

    # ── Save JSON Report ──────────────────────────────────────────────
    if args.json:
        json_path = save_json_report(results, args.json)
        print(f"📄 JSON report saved to: {json_path}")

    # ── Exit Code ─────────────────────────────────────────────────────
    has_critical = any(
        r.verdict in (Verdict.MISMATCH, Verdict.DEAD_DOI)
        for r in results
    )
    sys.exit(1 if has_critical else 0)


def _read_input(args) -> str:
    """
    Read reference text from the specified source.

    Priority: --file > --text > stdin (if not a TTY)

    Args:
        args: Parsed CLI arguments.

    Returns:
        Reference text string.
    """
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            print(f"❌ Error: File not found: {args.file}")
            sys.exit(1)
        except IOError as e:
            print(f"❌ Error reading file: {e}")
            sys.exit(1)

    if args.text:
        return args.text

    # Try stdin (piped input)
    if not sys.stdin.isatty():
        return sys.stdin.read()

    # Interactive mode: prompt user
    print("📝 Paste your references below (press Ctrl+D when done):\n")
    try:
        lines = []
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass

    return "\n".join(lines)


if __name__ == "__main__":
    main()
