# PLAG case study: detecting an explosive event mover

Analysis date: **August 11, 2026**. Market statistics are time-sensitive and
must be refreshed from a live feed before use.

## What moved the stock

The confirmed same-morning catalyst was Planet Green's 07:30 ET announcement
that it had begun commercial operations to source, market, and distribute
lactoferrin and was adding a Chief Scientist. The release framed lactoferrin as
a growing, supply-constrained nutrition ingredient market. That announcement—not
an earnings release—coincided with the premarket move.

Source: [Planet Green's August 11 announcement](https://www.prnewswire.com/news-releases/planet-green-enters-the-fast-growing-global-lactoferrin-market-adding-chief-scientist-to-drive-innovation-based-product-portfolio-growth-302848326.html).

The size of the reaction likely came from the interaction of:

1. fresh, easy-to-understand thematic news;
2. a low-priced security with a small tradable share base;
3. extraordinary same-window premarket turnover; and
4. momentum, crowding, and repeated volatility-halt risk after the move began.

The share-structure point has filing support. A July 13 Form 8-K calculated a
public float of about **11.64 million non-affiliate shares** at that time. That
does not prove the effective float available on August 11, nor does high volume
prove a short squeeze. “Short squeeze” remains an unverified hypothesis unless
current short-interest, borrow, and settlement data support it.

Source: [Planet Green July 13 Form 8-K](https://www.sec.gov/Archives/edgar/data/1117057/000121390026077736/ea0297814-8k_planet.htm).

## Why the original trend scan would miss it

This repo's original strategy intentionally requires a $5 minimum price, more
than one million shares of 20-day average daily volume, 2–5% ATR, beta above
one, and a clean established trend. PLAG was below $5 before the announcement
and its normal liquidity was far below the trend scanner's threshold. Relaxing
those gates would pollute the safer watchlist with thin microcaps.

The build therefore adds a separate `explosive` strategy. It searches the full
active Alpaca US-equity universe first, cheaply prefilters price and gap, then
requests detailed history/news only for the strongest 50 preliminary movers.
Trend and explosive results remain separate artifacts.

## Default PLAG-style gates

| Gate | Default | Why it exists |
| --- | ---: | --- |
| Price | $0.50–$20 | Includes sub-$5 event movers without accepting near-zero quotes |
| 20-day ADV | >50,000 | Avoids completely dormant listings; current liquidity matters more here |
| Positive gap | ≥20% | Requires a genuine repricing event |
| Premarket volume | ≥250,000 | Requires executable attention by scan time |
| Approx. premarket dollar volume | ≥$1 million | Shares × latest price prevents cheap stocks passing on share count alone |
| Same-window PM RVOL | ≥5× | Compares volume through the same clock time, not a partial day to full days |
| Quote spread | ≤2% | Rejects severely impaired quotes |
| Distance from PM high | ≤15% | Rejects movers already collapsing from the event high |
| Fresh external catalyst | News ≤24 hours old or upcoming earnings | A price gap alone is not a catalyst |
| Shares outstanding | ≤50 million when known | Favors small structures; unknown data is visibly flagged, never invented |
| Watchlist | Up to 15 | Ranked and never padded |

These are discovery gates, not entry rules. A result can still be untradeable
because of halts, spreads, slippage, dilution, or a failed news thesis.

## Filing risks the price action does not remove

The same July 8-K authorized an at-the-market program of up to approximately
**$8.92 million**, so dilution/financing review belongs in every checklist. The
2025 Form 10-K reported a **$17.79 million continuing-operations loss**, a
**$175.03 million accumulated deficit**, a **$7.07 million working-capital
deficit**, and substantial doubt about continuing as a going concern.

Sources: [ATM Form 8-K](https://www.sec.gov/Archives/edgar/data/1117057/000121390026077736/ea0297814-8k_planet.htm) and [2025 Form 10-K](https://www.sec.gov/Archives/edgar/data/1117057/000121390026037637/ea0283176-10k_planet.htm).

That is why the report always adds a filing-review risk flag, highlights unknown
share data, flags ≥100% gaps and high turnover, and sizes hypothetical risk at a
smaller default $50. Stops are not guaranteed: halts and gaps can bypass them.
The SEC likewise warns that microcaps historically combine limited information,
low liquidity, high volatility, and greater manipulation risk.

Source: [SEC Investor Bulletin on microcap risk](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/investor-2).

## Run it

```bash
.venv/bin/market-scanner scan --strategy explosive --provider alpaca --output-dir artifacts
open artifacts/explosive-scan.html
```

With `--provider alpaca` and no `--symbols`, the strategy discovers active US
equities automatically. Pass `--symbols PLAG,XYZ` only for targeted diagnosis.
Use `--provider demo` to validate the pipeline without credentials.

Before any trade, independently verify the headline against the issuer/filing,
the timestamp, consolidated quote and spread, halt state, current float/shares,
recent ATM/shelf/warrant/reverse-split filings, thesis, trigger, stop, target,
position size, and maximum loss.
