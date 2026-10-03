import httpx
import pytest

from tokenforensics.client import TokenForensicsClient, TokenForensicsError
from tokenforensics.report import markdown_report

ADDRESS = "0x" + "a" * 40


def test_analyze_selects_liquid_pair_and_builds_risk_findings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "dexscreener" in request.url.host:
            return httpx.Response(
                200,
                json={
                    "pairs": [
                        {
                            "chainId": "ethereum",
                            "pairAddress": "0xpool",
                            "baseToken": {"address": ADDRESS, "name": "Sample", "symbol": "SMP"},
                            "quoteToken": {"address": "0xquote"},
                            "priceUsd": "0.5",
                            "marketCap": 1_000_000,
                            "volume": {"h24": 50_000},
                            "liquidity": {"usd": 20_000},
                            "priceChange": {"h1": 1.5, "h6": -2, "h24": 4},
                        }
                    ]
                },
            )
        if "gopluslabs" in request.url.host:
            return httpx.Response(
                200,
                json={"result": {ADDRESS: {"holders": [{"percent": "0.25"}, {"percent": "0.1"}]}}},
            )
        return httpx.Response(200, json={"data": []})

    with TokenForensicsClient(transport=httpx.MockTransport(handler)) as client:
        payload = client.analyze(ADDRESS)

    assert payload["market"]["symbol"] == "SMP"
    assert payload["market"]["liquidity_usd"] == 20_000
    assert payload["holder_data"]["top_holder_percent"] == 25
    assert any("Low liquidity" in finding for finding in payload["risks"])
    assert any("Concentrated ownership" in finding for finding in payload["risks"])


def test_analyze_rejects_invalid_address_before_request() -> None:
    transport = httpx.MockTransport(lambda _: pytest.fail("unexpected request"))
    with TokenForensicsClient(transport=transport) as client:
        with pytest.raises(ValueError, match="EVM address"):
            client.analyze("not-an-address")


def test_missing_market_pairs_is_an_error() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"pairs": []}))
    with TokenForensicsClient(transport=transport) as client:
        with pytest.raises(TokenForensicsError, match="No trading pairs"):
            client.analyze(ADDRESS)


def test_markdown_report_includes_market_and_risk_sections() -> None:
    payload = {
        "market": {
            "name": "Sample",
            "symbol": "SMP",
            "chain": "ethereum",
            "address": ADDRESS,
            "price_usd": 0.5,
            "market_cap_usd": 1_000_000,
            "volume_24h_usd": 50_000,
            "liquidity_usd": 80_000,
            "price_change": {"h1": 1, "h6": -2, "h24": 4},
            "url": "https://example.com/pair",
        },
        "holder_data": {"top_holder_percent": None, "top_10_percent": None},
        "security_error": "",
        "trades_error": "",
        "large_swaps": [],
        "risks": ["Holder concentration could not be assessed."],
    }

    report = markdown_report(payload)

    assert "# TokenForensics: Sample (SMP)" in report
    assert "## Risk checks" in report
    assert "## Large recent swaps" in report