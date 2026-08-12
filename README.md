# California Premarket Scanner

An evidence-first US equity scanner that builds a focused premarket watchlist at
**06:00 California time** every weekday. It filters measurable liquidity,
volatility, relative-volume, spread, and technical-structure criteria; enriches
survivors with catalysts; then emits JSON, CSV, Markdown, and a polished HTML
report with a complete pre-trade checklist. A separate explosive-mover strategy
finds PLAG-style fresh-catalyst microcap events without weakening the safer
trend screen.

> **Research only, not investment advice.** A scanner can reduce a universe; it
> cannot verify a trade for you. Recheck prices, quotes, news, earnings, levels,
> position size, and market conditions in a live broker feed before trading.

## Criteria encoded

| Requirement | Default implementation |
| --- | --- |
| Liquidity | 20-session average daily volume strictly above 1,000,000 shares |
| Tight spread | Bid/ask spread at or below 0.30% of midpoint |
| Volatility | 14-session ATR is 2–5% of price, inclusive |
| Beta | 60-session return beta to SPY strictly above 1.0 |
| Clean trend | Objective moving-average alignment/slope and directional-efficiency score |
| Clear levels | 20-session support/resistance exist with actionable room |
| Catalysts | Recent Alpaca news, upcoming earnings when configured, and/or a measurable gap |
| Price | $5–$150, inclusive |
| RVOL | Time-adjusted premarket relative volume strictly above 1.5 |
| Watchlist | Ranked, never padded, capped at 15; fewer than 10 is reported honestly |
| Checklist | Generated thesis, stop, target, and dollar/share risk for every result |

All thresholds live in [`config/scanner.toml`](config/scanner.toml). A symbol
must pass **every hard gate**, including evidence of at least one catalyst
(recent news, an upcoming earnings event, or a ≥2% gap). Missing optional
earnings data remains unknown rather than being treated as “no earnings.”

## PLAG-style explosive movers

PLAG's August 11, 2026 move followed a fresh company announcement about entering
commercial lactoferrin operations. Its sub-$5 starting price and low normal
volume meant it correctly failed the original trend gates. The new `explosive`
strategy instead requires a ≥20% gap, ≥250,000 premarket shares, ≥$1 million approximate
premarket dollar volume, ≥5× same-window premarket RVOL, ≤2% spread, proximity
to the premarket high, and either verified news no older than 24 hours or an
upcoming earnings event. Shares outstanding must be ≤50 million when available; unknown
share data is flagged, not guessed.

Run both strategies:

```bash
.venv/bin/market-scanner scan --provider alpaca --output-dir artifacts
.venv/bin/market-scanner scan --strategy explosive --provider alpaca --output-dir artifacts
```

Live explosive mode discovers Alpaca's active US-equity universe automatically,
then narrows it before expensive history/news calls. Read the evidence,
inferences, filing risks, and full filter rationale in
[`docs/PLAG_CASE_STUDY.md`](docs/PLAG_CASE_STUDY.md).

## Quick start

Python 3.11+ required.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
```

Export the two Alpaca values from `.env` in your shell, then:

```bash
.venv/bin/market-scanner scan --provider alpaca --output-dir artifacts
```

No credentials yet? Exercise the complete pipeline deterministically:

```bash
.venv/bin/market-scanner scan --provider demo --output-dir artifacts
.venv/bin/market-scanner scan --strategy explosive --provider demo --output-dir artifacts
open artifacts/market-scan.html
open artifacts/explosive-scan.html
```

You can override the seed universe:

```bash
.venv/bin/market-scanner scan --provider alpaca --symbols AMD,NVDA,TSLA,PLTR
```

## Outputs

Each successful run writes:

- `artifacts/market-scan.json` — stable machine-readable result and run metadata
- `artifacts/market-scan.csv` — ranked watchlist for spreadsheet workflows
- `artifacts/market-scan.md` — concise human review
- `artifacts/market-scan.html` — responsive, self-contained dashboard

Explosive mode writes the same four formats under `artifacts/explosive-scan.*`
and includes gap, premarket volume/dollar volume, same-window RVOL, distance from
premarket high, share data, catalyst evidence, and risk flags.

Outputs include data timestamps, warnings, applied criteria, raw metrics,
catalyst evidence, technical levels, and the pre-trade checklist. Provider or
data failures produce an explicit non-zero exit; they never silently fall back
from live to demo data.

## Data and methodology boundaries

- **Universe:** trend mode uses the curated `config/universe.txt`. Live
  explosive mode discovers active tradable US equities through Alpaca unless
  `--symbols` is supplied. Every symbol still faces the same strategy gates.
- **Alpaca feed:** defaults to IEX for broad account compatibility. IEX quotes
  reflect one venue and may understate consolidated volume or differ from NBBO.
  Use SIP only when your subscription permits it.
- **06:00 PT timing:** 09:00 ET on normal US trading days. RVOL compares
  cumulative extended-hours volume through the same time-of-day across prior
  sessions where data is available; inspect the report's method/warnings.
- **Beta:** historical estimate, not a stable property or forecast.
- **Levels/trend:** deterministic heuristics, not visual certainty. They create
  review candidates, not trade instructions.
- **Finnhub:** optional `FINNHUB_API_KEY` enriches the earnings calendar and
  explosive-mode shares outstanding/market cap. Unknown data remains unknown.
- **Holidays/stale data:** the weekday schedule can run on exchange holidays.
  Check `data_as_of` and warnings before acting.

Alpaca's snapshot endpoint supplies latest trade/quote/daily bars; historical
bars supply indicator history, and its news endpoint supplies headlines. See
[Alpaca Market Data documentation](https://docs.alpaca.markets/docs/about-market-data-api).

## 06:00 California scheduling

The included GitHub Actions workflow uses:

```yaml
- cron: "0 6 * * 1-5"
  timezone: "America/Los_Angeles"
```

That remains 06:00 through PST/PDT changes. Add `APCA_API_KEY_ID` and
`APCA_API_SECRET_KEY` under **Settings → Secrets and variables → Actions**, then
enable the workflow. GitHub schedules are best-effort and can be delayed or
dropped under load; [`docs/SCHEDULING.md`](docs/SCHEDULING.md) covers manual
runs (including credential-free demo validation), exact operational limits,
Docker, and a local macOS `launchd` alternative.

## Quality checks

```bash
.venv/bin/ruff check .
.venv/bin/pytest --cov=market_scanner --cov-report=term-missing
```

Tests are deterministic and never call live services. CI runs lint and tests on
every push and pull request.

## Architecture

```text
provider (Alpaca/demo)
  → normalized quotes, daily/minute bars, news, earnings
  → trend gates OR explosive event/liquidity gates
  → technical/catalyst scoring
  → rank + cap (never relax/pad)
  → JSON / CSV / Markdown / HTML
```

Provider I/O, calculations, scanner decisions, and rendering are separate
modules so each can be tested or replaced independently.

## License

MIT. See [`LICENSE`](LICENSE).
