"""
HMA Stock Scanner — Orchestrator
Runs the full scan pipeline: fetch → compute → score → display.
"""

import sys
import time
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.text import Text
from rich import box

from data_fetcher import fetch_daily_data, fetch_delivery_data, resample_to_weekly, get_stock_list
from scorer import score_stock
from config import HIGH_CONVICTION_MIN, WATCHLIST_MIN

console = Console()


def run_scan(universe: str = "nifty50", min_score: int = 0, skip_delivery: bool = False, only_high: bool = False):
    """
    Run the full stock scanner.
    Returns list of scored stock dicts, sorted by score descending.
    """
    stocks = get_stock_list(universe)
    total = len(stocks)

    console.print()
    console.print(Panel.fit(
        f"[bold cyan]🔍 HMA STOCK SCANNER[/bold cyan]\n"
        f"[dim]Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]\n"
        f"[dim]Universe: {universe.upper()} ({total} stocks)[/dim]",
        border_style="cyan",
    ))
    console.print()

    results = []
    skipped = []
    errors = []
    start_time = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning stocks...", total=total)

        for i, symbol in enumerate(stocks):
            progress.update(task, description=f"[cyan]{symbol}[/cyan] ({i+1}/{total})")

            try:
                # Fetch daily data
                daily_df = fetch_daily_data(symbol)
                if daily_df is None or len(daily_df) < 100:
                    skipped.append(symbol)
                    progress.advance(task)
                    continue

                # Resample to weekly
                weekly_df = resample_to_weekly(daily_df)
                # Require a minimum number of weekly candles (lowered to 20 to allow newer stocks)
                if weekly_df is None or len(weekly_df) < 20:
                    skipped.append(symbol)
                    progress.advance(task)
                    continue

                # Fetch delivery data (optional)
                delivery_pct = None
                if not skip_delivery:
                    delivery_pct = fetch_delivery_data(symbol)

                    # Also try from daily_df if equity_history returned it
                    if delivery_pct is None and "Delivery_Pct" in daily_df.columns:
                        recent_del = daily_df["Delivery_Pct"].dropna()
                        if len(recent_del) >= 5:
                            delivery_pct = float(recent_del.iloc[-20:].mean())

                # Score the stock
                result = score_stock(daily_df, weekly_df, symbol, delivery_pct)
                results.append(result)

            except Exception as e:
                errors.append(f"{symbol}: {str(e)[:80]}")

            progress.advance(task)

    elapsed = time.time() - start_time

    # Filter by minimum score
    if min_score > 0:
        results = [r for r in results if r.get("score", 0) >= min_score]

    # Sort by score descending
    results.sort(key=lambda x: x.get("score", 0), reverse=True)

    # If requested, only keep high conviction results for display
    display_only = results
    if only_high:
        display_only = [r for r in results if r.get("conviction") == "HIGH"]

    # Display results (pass through only_high so display can limit top items)
    display_results(display_only, total, len(skipped), len(errors), elapsed, only_high=only_high)

    # Telegram Notification
    if only_high and display_only:
        from utils import send_telegram_message
        top_5 = display_only[:5]
        msg = f"<b>🚀 Daily Stock Scan - {datetime.now().strftime('%d %b %Y')}</b>\n\n"
        for s in top_5:
            msg += f"<b>{s['ticker']}</b> (Score: {s['score']})\n"
            msg += f"Price: ₹{s['price']:,.2f} | {s['category']} | {s['tier']}\n"
            msg += f"<b>RSI:</b> {s['rsi']:.0f} | <b>MACD:</b> {'Bullish' if s['macd_bullish'] else 'Bearish'}\n"
            msg += f"<b>HMA55:</b> ₹{s['hma55']:,.2f} (Dist: {s['distance_pct']}%)\n"
            msg += f"<b>Tgt:</b> ₹{s['target1']:,.2f} / ₹{s['target2']:,.2f}\n"
            msg += f"<b>SL:</b> ₹{s['stop_loss']:,.2f} ({s['sl_pct']}% Risk)\n"
            cautions = ", ".join(s.get("caution_flags", []))
            if cautions:
                msg += f"⚠️ <i>{cautions}</i>\n"
            msg += "-------------------\n"
        
        send_telegram_message(msg)

    # Show errors if any
    if errors:
        console.print()
        console.print("[dim yellow]⚠ Errors during scan:[/dim yellow]")
        for err in errors[:10]:
            console.print(f"  [dim]{err}[/dim]")
        if len(errors) > 10:
            console.print(f"  [dim]... and {len(errors) - 10} more[/dim]")

    return results


def display_results(results, total_scanned, skipped_count, error_count, elapsed_secs, only_high: bool = False):
    """Display scan results as beautiful rich tables."""

    # Separate by conviction
    high = [r for r in results if r.get("conviction") == "HIGH"]
    watchlist = [r for r in results if r.get("conviction") == "WATCHLIST"]
    rejected = [r for r in results if r.get("conviction") == "REJECTED"]
    bullish = [r for r in results if r.get("tier") == "Bullish"]
    neutral = [r for r in results if r.get("tier") == "Neutral"]

    # Summary panel
    mins = int(elapsed_secs // 60)
    secs = int(elapsed_secs % 60)
    console.print()
    console.print(Panel.fit(
        f"[bold green]✅ SCAN COMPLETE[/bold green]\n"
        f"Scanned: [bold]{total_scanned}[/bold] stocks  │  "
        f"Scored: [bold]{len(results)}[/bold]  │  "
        f"Skipped: [dim]{skipped_count}[/dim]  │  "
        f"Errors: [dim]{error_count}[/dim]\n"
        f"Bullish: [green]{len(bullish)}[/green]  │  "
        f"Neutral: [yellow]{len(neutral)}[/yellow]  │  "
        f"Time: [cyan]{mins}m {secs}s[/cyan]\n"
        f"[green]HIGH CONVICTION: {len(high)}[/green]  │  "
        f"[yellow]WATCHLIST: {len(watchlist)}[/yellow]  │  "
        f"[red]REJECTED: {len(rejected)}[/red]",
        border_style="green",
    ))

    # HIGH CONVICTION table (limit to top 5 when only_high requested)
    if high:
        display_high = high
        if only_high:
            display_high = high[:5]
        console.print()
        console.print("[bold green]🟢 HIGH CONVICTION (Score ≥ 7)[/bold green]")
        _print_table(display_high, "green")

    # WATCHLIST table
    if watchlist:
        console.print()
        console.print("[bold yellow]🟡 WATCHLIST (Score 4-6)[/bold yellow]")
        _print_table(watchlist, "yellow")

    # REJECTED summary — show table with scores and classification as requested
    if rejected:
        console.print()
        console.print("[bold red]🔴 REJECTED (Score < 4)[/bold red]")
        _print_table(rejected, "red")

    # If there are no results at all, show the empty message
    if not results:
        console.print()
        console.print("[bold red]No stocks matched the criteria.[/bold red]")


def _print_table(stocks: list, color: str):
    """Print a formatted table of scored stocks."""
    table = Table(
        box=box.ROUNDED,
        border_style=color,
        header_style=f"bold {color}",
        row_styles=["", "dim"],
        show_lines=False,
        pad_edge=True,
        expand=True,
    )

    table.add_column("Ticker", style="bold white", min_width=10)
    table.add_column("Score", justify="center", min_width=5)
    table.add_column("Tier", justify="center", min_width=8)
    table.add_column("Category", min_width=10)
    table.add_column("Price", justify="right", min_width=8)
    table.add_column("HMA55", justify="right", min_width=8)
    table.add_column("Dist%", justify="right", min_width=6)
    table.add_column("RSI", justify="center", min_width=5)
    table.add_column("MACD", justify="center", min_width=5)
    table.add_column("Risk%", justify="right", min_width=6)
    table.add_column("SL%", justify="right", min_width=6)
    table.add_column("T1%", justify="right", min_width=6)
    table.add_column("T2%", justify="right", min_width=6)
    table.add_column("Sector", min_width=8)
    table.add_column("Delivery%", justify="right", min_width=8)
    table.add_column("Entry", justify="right", min_width=9)
    table.add_column("Tgt1", justify="right", min_width=9)
    table.add_column("Tgt2", justify="right", min_width=9)
    table.add_column("Caution", min_width=12)

    for s in stocks:
        score = s.get("score", 0)
        score_style = "bold green" if score >= 7 else ("yellow" if score >= 4 else "red")

        tier = s.get("tier", "?")
        tier_style = "green" if tier == "Bullish" else ("yellow" if tier == "Neutral" else "red")

        macd_txt = "✓" if s.get("macd_bullish") else "✗"
        macd_style = "green" if s.get("macd_bullish") else "red"

        caution = ", ".join(s.get("caution_flags", [])) or "—"
        caution_style = "yellow" if s.get("caution_flags") else "dim"

        del_pct = s.get("delivery_pct")
        del_txt = f"{del_pct:.1f}" if del_pct is not None else "N/A"
        entry = s.get("entry")
        t1 = s.get("target1")
        t2 = s.get("target2")
        entry_txt = f"{entry:,.2f}" if entry is not None else "N/A"
        t1_txt = f"{t1:,.2f}" if t1 is not None else "N/A"
        t2_txt = f"{t2:,.2f}" if t2 is not None else "N/A"

        sl_pct = s.get("sl_pct")
        t1_pct = s.get("t1_pct")
        t2_pct = s.get("t2_pct")
        sl_txt = f"{sl_pct:.1f}%" if sl_pct is not None else "N/A"
        t1_pct_txt = f"{t1_pct:.1f}%" if t1_pct is not None else "N/A"
        t2_pct_txt = f"{t2_pct:.1f}%" if t2_pct is not None else "N/A"

        table.add_row(
            s.get("ticker", "?"),
            Text(str(score), style=score_style),
            Text(tier, style=tier_style),
            s.get("category", "?"),
            f"{s.get('price', 0):,.2f}",
            f"{s.get('hma55', 0):,.2f}",
            f"{s.get('distance_pct', 0):.1f}%",
            f"{s.get('rsi', 0):.0f}",
            Text(macd_txt, style=macd_style),
            f"{s.get('risk_pct', 0):.1f}%",
            sl_txt,
            t1_pct_txt,
            t2_pct_txt,
            s.get("sector", "?"),
            del_txt,
            entry_txt,
            t1_txt,
            t2_txt,
            Text(caution, style=caution_style),
        )

    console.print(table)

    # Also print a compact targets table to ensure Entry/Stop/Targets are visible
    tgt_table = Table(
        box=box.MINIMAL,
        header_style=f"bold {color}",
        show_lines=False,
        pad_edge=True,
        expand=False,
    )
    tgt_table.add_column("Ticker", style="bold white", min_width=8)
    tgt_table.add_column("Entry", justify="right", min_width=10)
    tgt_table.add_column("Stop", justify="right", min_width=10)
    tgt_table.add_column("SL%", justify="right", min_width=6)
    tgt_table.add_column("Tgt1", justify="right", min_width=10)
    tgt_table.add_column("T1%", justify="right", min_width=6)
    tgt_table.add_column("Tgt2", justify="right", min_width=10)
    tgt_table.add_column("T2%", justify="right", min_width=6)

    for s in stocks:
        stop = s.get("stop_loss")
        stop_txt = f"{stop:,.2f}" if stop is not None else "N/A"
        entry = s.get("entry")
        t1 = s.get("target1")
        t2 = s.get("target2")
        entry_txt = f"{entry:,.2f}" if entry is not None else "N/A"
        t1_txt = f"{t1:,.2f}" if t1 is not None else "N/A"
        t2_txt = f"{t2:,.2f}" if t2 is not None else "N/A"
        sl_pct = s.get("sl_pct")
        t1_pct = s.get("t1_pct")
        t2_pct = s.get("t2_pct")
        sl_txt = f"{sl_pct:.1f}%" if sl_pct is not None else "N/A"
        t1_pct_txt = f"{t1_pct:.1f}%" if t1_pct is not None else "N/A"
        t2_pct_txt = f"{t2_pct:.1f}%" if t2_pct is not None else "N/A"
        tgt_table.add_row(s.get("ticker", "?"), entry_txt, stop_txt, sl_txt, t1_txt, t1_pct_txt, t2_txt, t2_pct_txt)

    console.print()
    console.print(f"  [dim]Entry/Stop/Targets:[/dim]")
    console.print(tgt_table)

    # Print score breakdown for top stocks
    if stocks:
        console.print()
        console.print(f"  [dim]Score Breakdown (top 5):[/dim]")
        for s in stocks[:5]:
            bd = s.get("breakdown", {})
            parts = []
            for key, val in bd.items():
                if val > 0:
                    parts.append(f"[green]+{val} {key}[/green]")
                elif val < 0:
                    parts.append(f"[red]{val} {key}[/red]")
            ticker = s.get("ticker", "?")
            console.print(f"  [bold]{ticker}[/bold] ({s.get('score', 0)}): {' '.join(parts)}")
