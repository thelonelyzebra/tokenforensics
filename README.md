# TokenForensics

A read-only terminal health check for EVM token contracts. TokenForensics combines market and liquidity data, recent large swaps, basic price trends, and available holder-concentration signals, then can write a Markdown report suitable for a GitHub README.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
```

No API key is required. Market data comes from DexScreener, recent swaps from GeckoTerminal, and token holder/security information from GoPlus. The latter two checks are best-effort and can be unavailable due to provider coverage or rate limits.

## Usage

```bash
tokenforensics 0x0000000000000000000000000000000000000000
tokenforensics 0x0000000000000000000000000000000000000000 --chain base
tokenforensics 0x0000000000000000000000000000000000000000 --report README-token-health.md
tokenforensics 0x0000000000000000000000000000000000000000 --json
```

Supported network filters: `ethereum`, `bsc`, `base`, `polygon`, `arbitrum`, `optimism`, and `avalanche`. Without `--chain`, the CLI chooses the matching pair with the highest reported liquidity. Thresholds can be adjusted with `--low-liquidity` and `--whale-threshold` (USD).

Large swaps are a public trade-feed signal, not a complete record of wallet transfers. Holder concentration uses the holders returned by the security provider and is explicitly marked unavailable when no data is returned. This tool is informational, not investment advice.

## Development

```bash
pytest
python -m tokenforensics.cli --help
```

## License

TokenForensics is licensed under the Apache License 2.0. See [LICENSE](LICENSE).

Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any suggestions or improvements.

ETH: 0x2F6B79c8e1e51A760Ef7930b40eEF7d668098328
