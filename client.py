"""Read-only market, swap, and token-security data clients."""

from __future__ import annotations

import re
from typing import Any

import httpx


class TokenForensicsError(RuntimeError):
    """Raised when required token market data cannot be retrieved."""


CHAINS: dict[str, dict[str, str]] = {
    "ethereum": {"dex": "ethereum", "goplus": "1", "gecko": "eth"},
    "bsc": {"dex": "bsc", "goplus": "56", "gecko": "bsc"},
    "base": {"dex": "base", "goplus": "8453", "gecko": "base"},
    "polygon": {"dex": "polygon", "goplus": "137", "gecko": "polygon_pos"},
    "arbitrum": {"dex": "arbitrum", "goplus": "42161", "gecko": "arbitrum"},
    "optimism": {"dex": "optimism", "goplus": "10", "gecko": "optimism"},
    "avalanche": {"dex": "avalanche", "goplus": "43114", "gecko": "avax"},
}

_ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")


class TokenForensicsClient:
    """Fetch token market information and best-effort on-chain signals."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(timeout=20.0, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TokenForensicsClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def analyze(
        self,
        address: str,
        chain: str | None = None,
        low_liquidity_usd: float = 50_000,
        whale_threshold_usd: float = 100_000,
    ) -> dict[str, Any]:
        """Return a normalized report payload for an EVM token address."""
        if not _ADDRESS_PATTERN.fullmatch(address):
            raise ValueError("Token address must be a 0x-prefixed 40-character EVM address")
        if chain is not None and chain not in CHAINS:
            raise ValueError(f"Unsupported chain '{chain}'. Choose from: {', '.join(CHAINS)}")
        if low_liquidity_usd < 0 or whale_threshold_usd < 0:
            raise ValueError("Risk thresholds cannot be negative")

        pairs_payload = self._get_json(
            f"https://api.dexscreener.com/latest/dex/tokens/{address}"
        )
        pairs = pairs_payload.get("pairs") or []
        if chain:
            pairs = [pair for pair in pairs if pair.get("chainId") == CHAINS[chain]["dex"]]
        if not pairs:
            chain_detail = f" on {chain}" if chain else ""
            raise TokenForensicsError(f"No trading pairs found for {address}{chain_detail}")

        pair = max(pairs, key=lambda item: _number(item.get("liquidity", {}).get("usd")))
        chain_name = str(pair.get("chainId", "unknown"))
        chain_config = next(
            (config for config in CHAINS.values() if config["dex"] == chain_name), None
        )
        token = pair.get("baseToken", {})
        if str(pair.get("quoteToken", {}).get("address", "")).lower() == address.lower():
            token = pair.get("quoteToken", {})

        market = {
            "address": address,
            "name": token.get("name", "Unknown token"),
            "symbol": token.get("symbol", "?"),
            "chain": chain_name,
            "pair_address": pair.get("pairAddress", ""),
            "url": pair.get("url", ""),
            "price_usd": _number(pair.get("priceUsd")),
            "market_cap_usd": _number(pair.get("marketCap") or pair.get("fdv")),
            "volume_24h_usd": _number(pair.get("volume", {}).get("h24")),
            "liquidity_usd": _number(pair.get("liquidity", {}).get("usd")),
            "price_change": pair.get("priceChange", {}),
        }

        security: dict[str, Any] = {}
        security_error = ""
        trades: list[dict[str, Any]] = []
        trades_error = ""
        if chain_config:
            try:
                security_payload = self._get_json(
                    f"https://api.gopluslabs.io/api/v1/token_security/{chain_config['goplus']}",
                    params={"contract_addresses": address},
                )
                security = (security_payload.get("result") or {}).get(address.lower(), {})
                if not security:
                    security_error = "No holder/security data returned"
            except TokenForensicsError as exc:
                security_error = str(exc)

            try:
                trade_payload = self._get_json(
                    "https://api.geckoterminal.com/api/v2/"
                    f"networks/{chain_config['gecko']}/pools/{market['pair_address']}/trades",
                    params={"page": 1},
                )
                for item in trade_payload.get("data", []):
                    attributes = item.get("attributes", {})
                    volume = _number(attributes.get("volume_in_usd"))
                    if volume >= whale_threshold_usd:
                        trades.append(
                            {
                                "wallet": attributes.get("tx_from_address", "Unknown wallet"),
                                "volume_usd": volume,
                                "kind": attributes.get("kind", "swap"),
                                "timestamp": attributes.get("block_timestamp", ""),
                            }
                        )
            except TokenForensicsError as exc:
                trades_error = str(exc)

        return {
            "market": market,
            "large_swaps": trades,
            "holder_data": _holder_summary(security),
            "security_error": security_error,
            "trades_error": trades_error,
            "risks": _risk_findings(market, _holder_summary(security), low_liquidity_usd),
        }

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise TokenForensicsError(f"API request failed: {exc}") from exc
        except ValueError as exc:
            raise TokenForensicsError("API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise TokenForensicsError("API returned an unexpected response")
        return payload


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _holder_summary(security: dict[str, Any]) -> dict[str, Any]:
    holders = security.get("holders") or []
    if not holders:
        return {"top_holder_percent": None, "top_10_percent": None}

    percentages = sorted((_number(holder.get("percent")) * 100 for holder in holders), reverse=True)
    return {
        "top_holder_percent": percentages[0],
        "top_10_percent": sum(percentages[:10]),
    }


def _risk_findings(
    market: dict[str, Any], holders: dict[str, Any], low_liquidity_usd: float
) -> list[str]:
    findings = []
    if market["liquidity_usd"] < low_liquidity_usd:
        findings.append(
            f"Low liquidity: ${market['liquidity_usd']:,.0f} is below "
            f"the ${low_liquidity_usd:,.0f} threshold."
        )
    top_holder = holders["top_holder_percent"]
    top_ten = holders["top_10_percent"]
    if top_holder is None:
        findings.append("Holder concentration could not be assessed from available data.")
    elif top_holder >= 20 or top_ten >= 50:
        findings.append(
            f"Concentrated ownership: top holder {top_holder:.1f}%, "
            f"top 10 holders {top_ten:.1f}%."
        )
    if not findings:
        findings.append("No configured liquidity or holder-concentration thresholds were crossed.")
    return findings