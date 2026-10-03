"""TokenForensics command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from .client import CHAINS, TokenForensicsClient, TokenForensicsError
from .report import markdown_report

app = typer.Typer(help="Run a read-only crypto token health check.")
console = Console()


def _usd(value: float) -> str:
    return f"${value:,.6f}" if 0 < value < 0.01 else f"${value:,.2f}"


@app.command()
def check(
    address: str = typer.Argument(..., help="EVM token contract address."),
    chain: str | None = typer.Option(
        None,
        "--chain",
        case_sensitive=False,
        help=f"Limit lookup to a network: {', '.join(CHAINS)}.",
    ),
    report: Path | None = typer.Option(
        None, "--report", help="Write the README-ready Markdown report to this path."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
    low_liquidity: float = typer.Option(50_000, min=0, help="Low-liquidity warning threshold in USD."),
    whale_threshold: float = typer.Option(100_000, min=0, help="Large-swap threshold in USD."),
) -> None:
    """Inspect a token's market, recent large swaps, and ownership signals."""
    selected_chain = chain.lower() if chain else None
    try:
        with TokenForensicsClient() as client:
            payload = client.analyze(
                address,
                chain=selected_chain,
                low_liquidity_usd=low_liquidity,
                whale_threshold_usd=whale_threshold,
            )
    except (TokenForensicsError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        _print_summary(payload)

    if report:
        try:
            report.write_text(markdown_report(payload), encoding="utf-8")
        except OSError as exc:
            typer.echo(f"Could not write report: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        console.print(f"Markdown report written to {report}")


def _print_summary(payload: dict[str, Any]) -> None:
    market = payload["market"]
    changes = market["price_change"]
    console.print(f"[bold cyan]{market['name']} ({market['symbol']})[/bold cyan]  {market['chain']}")
    console.print(f"[dim]{market['address']}[/dim]")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Price", _usd(market["price_usd"]))
    table.add_row("Market cap / FDV", _usd(market["market_cap_usd"]))
    table.add_row("24h volume", _usd(market["volume_24h_usd"]))
    table.add_row("Liquidity", _usd(market["liquidity_usd"]))
    table.add_row("Price trend", f"1h {_percent(changes.get('h1'))} | 6h {_percent(changes.get('h6'))} | 24h {_percent(changes.get('h24'))}")
    console.print(table)

    console.print("\n[bold]Risk checks[/bold]")
    for finding in payload["risks"]:
        console.print(f"- {finding}")
    if payload["large_swaps"]:
        console.print(f"\n[bold]Large swaps ({len(payload['large_swaps'])})[/bold]")
        for trade in payload["large_swaps"]:
            console.print(
                f"- {_usd(trade['volume_usd'])} {trade['kind']} from "
                f"{trade['wallet']} ({trade['timestamp']})"
            )
    elif payload["trades_error"]:
        console.print(f"\n[dim]Large-swap data unavailable: {payload['trades_error']}[/dim]")


def _percent(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "n/a"


if __name__ == "__main__":
    app()