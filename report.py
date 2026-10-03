"""Terminal and Markdown rendering for token analysis results."""

from __future__ import annotations

from typing import Any


def markdown_report(payload: dict[str, Any]) -> str:
    market = payload["market"]
    changes = market["price_change"]
    holders = payload["holder_data"]
    lines = [
        f"# TokenForensics: {market['name']} ({market['symbol']})",
        "",
        f"- **Network:** {market['chain']}",
        f"- **Contract:** `{market['address']}`",
        f"- **Price:** {_usd(market['price_usd'])}",
        f"- **Market cap / FDV:** {_usd(market['market_cap_usd'])}",
        f"- **24h volume:** {_usd(market['volume_24h_usd'])}",
        f"- **Liquidity:** {_usd(market['liquidity_usd'])}",
        f"- **Price change:** 1h {_percent(changes.get('h1'))} | "
        f"6h {_percent(changes.get('h6'))} | 24h {_percent(changes.get('h24'))}",
        "",
        "## Risk checks",
    ]
    lines.extend(f"- {finding}" for finding in payload["risks"])
    if holders["top_holder_percent"] is not None:
        lines.extend(
            [
                f"- Top holder: {holders['top_holder_percent']:.1f}%",
                f"- Top 10 holders: {holders['top_10_percent']:.1f}%",
            ]
        )
    if payload["security_error"]:
        lines.append(f"- Holder data unavailable: {payload['security_error']}")

    lines.extend(["", "## Large recent swaps"])
    if payload["large_swaps"]:
        lines.extend(
            [
                "| Wallet | Type | USD value | Timestamp |",
                "| --- | --- | ---: | --- |",
            ]
        )
        for trade in payload["large_swaps"]:
            lines.append(
                f"| `{trade['wallet']}` | {trade['kind']} | "
                f"{_usd(trade['volume_usd'])} | {trade['timestamp']} |"
            )
    else:
        lines.append("No swaps above the configured threshold were returned.")
    if payload["trades_error"]:
        lines.append(f"- Swap data unavailable: {payload['trades_error']}")

    if market["url"]:
        lines.extend(["", f"[View pair on DexScreener]({market['url']})"])
    lines.extend(["", "> Data is informational, may be incomplete, and is not financial advice."])
    return "\n".join(lines) + "\n"


def _usd(value: float) -> str:
    return f"${value:,.6f}" if 0 < value < 0.01 else f"${value:,.2f}"


def _percent(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "n/a"