"""
Rich CLI reporter and JSON report generator.

Produces two output modes:
    1. Rich terminal output — colored, emoji-decorated, human-readable
    2. JSON report — machine-readable, saved to a file

Both formats include per-reference details and a summary dashboard.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import Verdict, VerificationResult

logger = logging.getLogger(__name__)

# Verdict display configuration
_VERDICT_STYLES = {
    Verdict.VERIFIED:      ("✅", "bold green",  "VERIFIED"),
    Verdict.SUSPICIOUS:    ("⚠️",  "bold yellow", "SUSPICIOUS"),
    Verdict.MISMATCH:      ("❌", "bold red",    "MISMATCH"),
    Verdict.DEAD_DOI:      ("💀", "bold red",    "DEAD/FAKE DOI"),
    Verdict.NO_DOI:        ("🔍", "dim",         "NO DOI"),
    Verdict.API_ERROR:     ("🔌", "bold magenta","API ERROR"),
    Verdict.TITLE_MATCHED: ("📗", "bold cyan",   "TITLE MATCHED"),
}


def print_results(results: List[VerificationResult], console: Optional[Console] = None):
    """
    Print verification results as a rich, colored terminal report.

    Args:
        results: List of verification results.
        console: Optional Rich Console instance (for testing).
    """
    if console is None:
        console = Console()

    # ── Header ────────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel.fit(
            "[bold white]📚 Automated Citation Verification Report[/bold white]",
            border_style="bright_blue",
            padding=(0, 2),
        )
    )
    console.print(
        f"  [dim]Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
        f"| References: {len(results)}[/dim]"
    )
    console.print()

    # ── Per-Reference Results ─────────────────────────────────────────
    for i, res in enumerate(results, 1):
        _print_single_result(console, i, res)

    # ── Summary Dashboard ─────────────────────────────────────────────
    _print_summary(console, results)


def _print_single_result(console: Console, index: int, res: VerificationResult):
    """Print a single reference verification result."""
    emoji, style, label = _VERDICT_STYLES.get(
        res.verdict, ("❓", "dim", "UNKNOWN")
    )

    ref = res.reference
    ref_num = ref.ref_number if ref.ref_number else index

    # Reference header
    console.print(f"{'─' * 70}", style="dim")
    console.print(f"  {emoji} [bold]Ref [{ref_num}][/bold] — [{style}]{label}[/{style}]")

    # DOI
    if ref.doi:
        console.print(f"     DOI: [cyan]{ref.doi}[/cyan]")
    else:
        console.print(f"     DOI: [dim]Not found[/dim]")

    # Cited title
    if ref.candidate_title:
        title_display = ref.candidate_title[:100]
        if len(ref.candidate_title) > 100:
            title_display += "..."
        console.print(f"     Cited Title: [white]{title_display}[/white]")

    # Ground truth
    if res.ground_truth and res.ground_truth.title:
        gt_title = res.ground_truth.title[:100]
        if len(res.ground_truth.title) > 100:
            gt_title += "..."
        console.print(
            f"     API Title:   [white]{gt_title}[/white] "
            f"[dim]({res.ground_truth.api_source})[/dim]"
        )

    # Comparison scores
    if res.comparison and res.comparison.final_score > 0:
        scores = res.comparison
        console.print(
            f"     Scores: ratio={scores.ratio_score:.1f} | "
            f"token_sort={scores.token_sort_score:.1f} | "
            f"token_set={scores.token_set_score:.1f} → "
            f"[bold]final={scores.final_score:.1f}%[/bold]"
        )

    # Year match
    if res.comparison and res.comparison.year_match is not None:
        year_icon = "✓" if res.comparison.year_match else "✗"
        year_style = "green" if res.comparison.year_match else "red"
        console.print(
            f"     Year: [{year_style}]{year_icon}[/{year_style}] "
            f"(cited={res.reference.year}, actual={res.ground_truth.year})"
        )

    # Cross-validation status
    if res.cross_validated:
        console.print(f"     Cross-validated: [green]✓ Confirmed by OpenAlex[/green]")

    # Error message
    if res.error_message:
        console.print(f"     [yellow]Note: {res.error_message}[/yellow]")

    console.print()


def _print_summary(console: Console, results: List[VerificationResult]):
    """Print a summary dashboard of all verification results."""
    console.print(f"{'═' * 70}", style="bright_blue")
    console.print()

    # Count verdicts
    counts = {}
    for v in Verdict:
        counts[v] = sum(1 for r in results if r.verdict == v)

    total = len(results)

    # Summary table
    table = Table(
        title="📊 Verification Summary",
        show_header=True,
        header_style="bold white",
        border_style="bright_blue",
        padding=(0, 2),
    )
    table.add_column("Verdict", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Percentage", justify="right")

    for verdict, count in counts.items():
        if count > 0:
            emoji, style, label = _VERDICT_STYLES.get(
                verdict, ("❓", "dim", "UNKNOWN")
            )
            pct = (count / total * 100) if total > 0 else 0
            table.add_row(
                f"{emoji} {label}",
                str(count),
                f"{pct:.1f}%",
                style=style,
            )

    console.print(table)
    console.print()

    # Critical alerts
    mismatches = counts.get(Verdict.MISMATCH, 0)
    dead_dois = counts.get(Verdict.DEAD_DOI, 0)

    if mismatches > 0 or dead_dois > 0:
        console.print(
            Panel(
                f"[bold red]⚠️  ATTENTION: {mismatches} MISMATCH(es) and "
                f"{dead_dois} DEAD DOI(s) detected.\n"
                f"These citations require immediate manual review.[/bold red]",
                border_style="red",
            )
        )
    elif counts.get(Verdict.SUSPICIOUS, 0) > 0:
        console.print(
            Panel(
                f"[bold yellow]📝 {counts[Verdict.SUSPICIOUS]} citation(s) flagged "
                f"as SUSPICIOUS. Manual review recommended.[/bold yellow]",
                border_style="yellow",
            )
        )
    else:
        console.print(
            Panel(
                "[bold green]✅ All citations verified successfully![/bold green]",
                border_style="green",
            )
        )

    console.print()


def save_json_report(
    results: List[VerificationResult],
    output_path: str = "verification_report.json",
):
    """
    Save verification results as a structured JSON report.

    Args:
        results: List of verification results.
        output_path: File path for the JSON output.
    """
    report = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_references": len(results),
            "system_version": "1.2.0",
        },
        "summary": _build_summary(results),
        "results": [_serialize_result(r) for r in results],
    }

    output = Path(output_path)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("JSON report saved to: %s", output.resolve())

    return str(output.resolve())


def _build_summary(results: List[VerificationResult]) -> dict:
    """Build summary statistics for the JSON report."""
    counts = {}
    for v in Verdict:
        count = sum(1 for r in results if r.verdict == v)
        if count > 0:
            counts[v.value] = count

    return {
        "total": len(results),
        "verdicts": counts,
        "has_critical_issues": any(
            r.verdict in (Verdict.MISMATCH, Verdict.DEAD_DOI) for r in results
        ),
    }


def _serialize_result(res: VerificationResult) -> dict:
    """Serialize a VerificationResult to a JSON-compatible dict."""
    entry = {
        "ref_number": res.reference.ref_number,
        "verdict": res.verdict.value,
        "doi": res.reference.doi,
        "cited_title": res.reference.candidate_title,
        "raw_text": res.reference.raw_text[:300],  # Truncate long raw text
    }

    if res.ground_truth:
        entry["ground_truth"] = {
            "title": res.ground_truth.title,
            "authors": res.ground_truth.authors[:5],  # Limit authors
            "year": res.ground_truth.year,
            "source_journal": res.ground_truth.source_journal,
            "api_source": res.ground_truth.api_source,
        }

    if res.comparison:
        entry["scores"] = {
            "ratio": round(res.comparison.ratio_score, 1),
            "token_sort": round(res.comparison.token_sort_score, 1),
            "token_set": round(res.comparison.token_set_score, 1),
            "final": round(res.comparison.final_score, 1),
            "year_match": res.comparison.year_match,
        }

    entry["cross_validated"] = res.cross_validated

    if res.error_message:
        entry["error"] = res.error_message

    return entry
