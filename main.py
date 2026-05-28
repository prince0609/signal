import argparse
import sys

from scanner import run_scan
from utils import clear_cache
from rich.console import Console

console = Console()

def main():
    parser = argparse.ArgumentParser(description="HMA Stock Scanner (NSE)")
    parser.add_argument(
        "--universe",
        type=str,
        default="all",
        help="Stock universe to scan: all, nifty50, nifty200, nifty500, or a comma-separated list"
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip database synchronization"
    )
    parser.add_argument(
        "--all-results",
        action="store_true",
        help="Show all results instead of only the top 5 high conviction stocks"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear cached data before running the scan"
    )
    args = parser.parse_args()

    # Database synchronization (Default: ON)
    if not args.no_sync:
        from bhavcopy_downloader import sync_database
        console.print("[dim yellow]Synchronizing local database with NSE...[/dim yellow]")
        sync_database(400)

    if args.clear_cache:
        console.print("[dim yellow]Clearing cache...[/dim yellow]")
        clear_cache()
        console.print("[dim green]Cache cleared.[/dim green]")

    try:
        run_scan(
            universe=args.universe,
            min_score=0,
            skip_delivery=False,
            only_high=not args.all_results,
        )
    except KeyboardInterrupt:
        console.print("\n[bold red]Scan interrupted by user.[/bold red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Fatal Error:[/bold red] {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
