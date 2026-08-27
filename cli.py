"""
LITSEARCH CLI v2 - Command-line interface for the job search engine.
"""

import os
import sys
import io
import time
import logging
import argparse
from datetime import datetime

# Fix Windows encoding for Unicode output
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    from rich.text import Text
    from rich.columns import Columns
    from rich.align import Align
    from rich.markdown import Markdown
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from .cv_parser import parse_cv
from .keyword_analyzer import generate_search_queries
from .scorer import rank_jobs, get_match_label
from .checker import run_checker, format_checker_summary
from .scrapers.manager import ScraperManager, DEFAULT_PORTALS
from .excel_export import export_to_excel

# Logger setup
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("litsearch")


BANNER = r"""
 ██╗     ███╗   ███╗████████╗███████╗ █████╗ ████████╗
 ██║     ████╗ ████║╚══██╔══╝██╔════╝██╔══██╗╚══██╔══╝
 ██║     ██╔████╔██║   ██║   █████╗  ███████║   ██║
 ██║     ██║╚██╔╝██║   ██║   ██╔══╝  ██╔══██║   ██║
 ███████╗██║ ╚═╝ ██║   ██║   ███████╗██║  ██║   ██║
 ╚══════╝╚═╝     ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝   ╚═╝
       🔍 AI-Powered Multi-Portal Job Search Engine 🔍
"""


def print_banner(console=None):
    """Print the LITSEARCH banner."""
    if console and HAS_RICH:
        console.print()
        console.print(Panel(
            Align.center(Text(BANNER, style="bold cyan")),
            border_style="bright_blue",
            padding=(0, 1),
        ))
        console.print()
    else:
        print(BANNER)


def run_search(cv_path: str, output: str = None, portals: list[str] = None,
               location: str = "", max_results: int = 20, verbose: bool = False,
               top_n: int = 10, queries: list[str] = None, freshness_days: int = 7):
    """
    Main search function (v2).

    Args:
        cv_path: Path to CV PDF file
        output: Output Excel file path
        portals: List of portals to search
        location: Job location filter
        max_results: Max results per portal
        verbose: Enable verbose logging
        top_n: Number of top matches to display
        queries: Custom search queries (overrides auto-generation)
        freshness_days: Only show jobs posted within this many days
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    console = Console() if HAS_RICH else None

    # --- Banner ---
    print_banner(console)

    # --- Step 1: Parse CV ---
    if console and HAS_RICH:
        with console.status("[bold green]📄 Parsing your CV...") as status:
            cv_data = parse_cv(cv_path)
    else:
        print("📄 Parsing your CV...")
        cv_data = parse_cv(cv_path)

    if console and HAS_RICH:
        # Display CV summary
        cv_table = Table(title="📋 CV Profile Extracted", box=box.ROUNDED, border_style="blue")
        cv_table.add_column("Field", style="bold")
        cv_table.add_column("Value")

        cv_table.add_row("Name", cv_data["name"])
        cv_table.add_row("Location", cv_data["location"])
        cv_table.add_row("Skills", ", ".join(cv_data["skills"][:15]) + ("..." if len(cv_data["skills"]) > 15 else ""))
        cv_table.add_row("Suggested Roles", "\n".join(cv_data["suggested_roles"]))
        cv_table.add_row("Experience", f"{len(cv_data['experience'])} positions found")
        cv_table.add_row("Education", "\n".join(cv_data["education"][:3]))

        console.print(cv_table)
        console.print()
    else:
        print(f"\n📋 CV Profile:")
        print(f"  Name: {cv_data['name']}")
        print(f"  Location: {cv_data['location']}")
        print(f"  Skills: {', '.join(cv_data['skills'][:10])}")
        print(f"  Suggested Roles: {', '.join(cv_data['suggested_roles'])}")
        print()

    # --- Step 2: Generate Search Queries ---
    if queries:
        search_queries = [{"query": q, "source_skills": [], "priority": 1} for q in queries]
    else:
        search_queries = generate_search_queries(cv_data, max_queries=8)

    if console and HAS_RICH:
        console.print(f"[bold]🔍 Generated {len(search_queries)} search queries:[/bold]")
        for i, sq in enumerate(search_queries[:8], 1):
            console.print(f"  {i}. [cyan]{sq['query']}[/cyan] (priority: {sq['priority']})")
        if len(search_queries) > 8:
            console.print(f"  ... and {len(search_queries) - 8} more")
        console.print()
    else:
        print(f"🔍 Generated {len(search_queries)} search queries:")
        for sq in search_queries[:5]:
            print(f"  - {sq['query']}")
        print()

    # --- Step 3: Search Job Portals (v2 manager) ---
    manager = ScraperManager(portals=portals)

    if console and HAS_RICH:
        console.print(f"[bold]🌐 Searching across {len(manager.scrapers)} portals...[/bold]")
        console.print(f"   Portals: {', '.join(manager.scrapers.keys())}")
        console.print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            main_task = progress.add_task("Overall Progress", total=1)
            progress.update(main_task, description="[bold]Running search across all portals...[/bold]")
            all_jobs, portal_counts, portal_status = manager.search_all(
                [sq["query"] for sq in search_queries], location,
                max_results=min(max_results, 10), freshness_days=freshness_days)
            progress.advance(main_task)
    else:
        print("🌐 Searching across all portals...")
        all_jobs, portal_counts, portal_status = manager.search_all(
            [sq["query"] for sq in search_queries], location,
            max_results=min(max_results, 10), freshness_days=freshness_days)

    # Show portal status
    if console and HAS_RICH:
        for p, st in portal_status.items():
            if st != "OK":
                console.print(f"  [red]⚠ {p}: {st}[/red]")
        console.print()
    else:
        for p, st in portal_status.items():
            if st != "OK":
                print(f"  ⚠ {p}: {st}")

    # --- Step 4: QC Checker & Score ---
    if console and HAS_RICH:
        with console.status("[bold yellow]📊 Running QC checker & scoring...") as status:
            qc_report = run_checker(all_jobs, portal_counts)
            console.print(format_checker_summary(qc_report))
            scored_jobs = rank_jobs(cv_data, qc_report["accepted"])
    else:
        print("\n📊 Running QC checker & scoring...")
        qc_report = run_checker(all_jobs, portal_counts)
        print(format_checker_summary(qc_report))
        scored_jobs = rank_jobs(cv_data, qc_report["accepted"])

    # --- Step 4b: Enrich top-N with full descriptions, then re-score ---
    if scored_jobs:
        if console and HAS_RICH:
            with console.status("[bold cyan]📝 Fetching job descriptions for top candidates...") as status:
                n = manager.enrich_descriptions(scored_jobs, top_n=top_n)
                if n:
                    scored_jobs = rank_jobs(cv_data, scored_jobs)  # re-score with full-text
                    console.print(f"  [green]✓ Enriched {n} jobs with full descriptions[/green]")
        else:
            n = manager.enrich_descriptions(scored_jobs, top_n=top_n)
            if n:
                scored_jobs = rank_jobs(cv_data, scored_jobs)

    # Clean up browser instances
    manager.close()

    # --- Step 5: Display Top Matches ---
    if console and HAS_RICH:
        console.print()
        console.rule("[bold green]🏆 TOP MATCHES[/bold green]")
        console.print()

        if not scored_jobs:
            console.print("[yellow]No jobs found. Try broadening your search or checking your internet connection.[/yellow]")
        else:
            # Top matches table
            top_table = Table(
                title=f"🎯 Top {min(top_n, len(scored_jobs))} Job Matches",
                box=box.DOUBLE_EDGE,
                border_style="green",
                show_lines=True,
            )
            top_table.add_column("#", style="bold", width=4)
            top_table.add_column("Company", style="bold cyan", max_width=25)
            top_table.add_column("Role", style="bold white", max_width=30)
            top_table.add_column("Match %", justify="center", width=10)
            top_table.add_column("Score", justify="center", width=8)
            top_table.add_column("Source", width=10)
            top_table.add_column("Missing Skills", max_width=20)
            top_table.add_column("Link", width=12)

            for idx, job in enumerate(scored_jobs[:top_n], 1):
                score = job.get("score", 0)
                match_pct = f"{score}%"
                label = get_match_label(score)

                # Color the score
                if score >= 80:
                    score_style = "bold green"
                elif score >= 60:
                    score_style = "bold blue"
                elif score >= 40:
                    score_style = "yellow"
                else:
                    score_style = "red"

                missing = ", ".join(job.get("missing_skills", [])[:3]) or "—"

                top_table.add_row(
                    str(idx),
                    job.get("company", "N/A")[:25],
                    job.get("title", "N/A")[:30],
                    f"[{score_style}]{match_pct}[/{score_style}]",
                    f"[{score_style}]{label}[/{score_style}]",
                    job.get("source", "N/A"),
                    f"[dim]{missing}[/dim]",
                    f"[link={job.get('url', '')}]Apply[/link]" if job.get("url") else "N/A",
                )

            console.print(top_table)

            # Summary stats
            console.print()
            stats = Table(box=box.SIMPLE, border_style="dim")
            stats.add_column("Metric", style="bold")
            stats.add_column("Value")
            stats.add_row("Total Jobs Found", str(len(scored_jobs)))
            stats.add_row("Excellent Matches (80+)", str(sum(1 for j in scored_jobs if j.get("score", 0) >= 80)))
            stats.add_row("Good Matches (60+)", str(sum(1 for j in scored_jobs if 60 <= j.get("score", 0) < 80)))
            stats.add_row("Moderate Matches (40+)", str(sum(1 for j in scored_jobs if 40 <= j.get("score", 0) < 60)))
            stats.add_row("Full-text Scored", str(sum(1 for j in scored_jobs if j.get("score_basis") == "full-text")))
            stats.add_row("Portals Searched", str(len(portal_counts)))
            for portal, count in sorted(portal_counts.items()):
                status_str = portal_status.get(portal, "OK")
                if status_str == "OK":
                    stats.add_row(f"  └─ {portal.title()}", str(count))
                else:
                    stats.add_row(f"  └─ {portal.title()}", f"[red]{status_str}[/red]")
            console.print(stats)
    else:
        print("\n" + "=" * 60)
        print("🏆 TOP MATCHES")
        print("=" * 60)
        if not scored_jobs:
            print("No jobs found. Try broadening your search.")
        else:
            for idx, job in enumerate(scored_jobs[:top_n], 1):
                score = job.get("score", 0)
                print(f"\n  #{idx} | Score: {score}/100 {get_match_label(score)}")
                print(f"     Company:  {job.get('company', 'N/A')}")
                print(f"     Role:     {job.get('title', 'N/A')}")
                print(f"     Source:   {job.get('source', 'N/A')}")
                print(f"     Link:     {job.get('url', 'N/A')}")
                missing = job.get("missing_skills", [])
                if missing:
                    print(f"     Gap:      {', '.join(missing[:5])}")

        print(f"\n  Total: {len(scored_jobs)} jobs found across {len(portal_counts)} portals")

    # --- Step 6: Export to Excel ---
    if console and HAS_RICH:
        console.print()
        with console.status("[bold green]📁 Exporting to Excel...") as status:
            output_path = export_to_excel(scored_jobs, cv_data, output, portal_counts, qc_report=qc_report)
        console.print(f"[bold green]✅ Excel file saved:[/bold green] [link=file://{os.path.abspath(output_path)}]{output_path}[/link]")
    else:
        print("\n📁 Exporting to Excel...")
        output_path = export_to_excel(scored_jobs, cv_data, output, portal_counts, qc_report=qc_report)
        print(f"✅ Excel file saved: {output_path}")

    console.print() if console else print()
    return scored_jobs, output_path


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="litsearch",
        description="🔍 LITSEARCH - AI-Powered Multi-Portal Job Search Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  litsearch --cv ~/Desktop/Ashish_CV.pdf
  litsearch --cv cv.pdf --location Mumbai --portals linkedin indeed naukri
  litsearch --cv cv.pdf --queries "equity research analyst" "financial analyst"
  litsearch --cv cv.pdf --top 20 --output my_jobs.xlsx
  litsearch --cv cv.pdf --freshness 14   # jobs posted in last 14 days
        """,
    )

    parser.add_argument(
        "--cv", "-c",
        required=True,
        help="Path to your CV/resume PDF file",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output Excel file path (auto-generated if not specified)",
    )
    parser.add_argument(
        "--portals", "-p",
        nargs="+",
        default=None,
        choices=["linkedin", "indeed", "naukri", "glassdoor", "shine", "foundit"],
        help="Job portals to search (default: all)",
    )
    parser.add_argument(
        "--location", "-l",
        default="",
        help="Job location (e.g., 'Bengaluru', 'Mumbai', 'Remote')",
    )
    parser.add_argument(
        "--max-results", "-m",
        type=int,
        default=15,
        help="Max results per portal per query (default: 15)",
    )
    parser.add_argument(
        "--top", "-t",
        type=int,
        default=10,
        help="Number of top matches to display (default: 10)",
    )
    parser.add_argument(
        "--queries", "-q",
        nargs="+",
        default=None,
        help="Custom search queries (overrides auto-generation from CV)",
    )
    parser.add_argument(
        "--freshness",
        type=int,
        default=7,
        help="Only show jobs posted within N days (default: 7)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="LITSEARCH 2.0.0",
    )

    args = parser.parse_args()

    # Validate CV path
    if not os.path.exists(args.cv):
        print(f"❌ Error: CV file not found: {args.cv}")
        sys.exit(1)

    try:
        scored_jobs, output_path = run_search(
            cv_path=args.cv,
            output=args.output,
            portals=args.portals,
            location=args.location,
            max_results=args.max_results,
            verbose=args.verbose,
            top_n=args.top,
            queries=args.queries,
            freshness_days=args.freshness,
        )
    except KeyboardInterrupt:
        print("\n\n⚠ Search cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
