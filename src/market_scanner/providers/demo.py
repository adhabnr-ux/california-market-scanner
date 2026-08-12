"""Deterministic provider for setup validation, screenshots, and tests."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from market_scanner.models import (
    Bar,
    Catalyst,
    ExplosiveConfig,
    MarketSnapshot,
    Quote,
    ScanConfig,
)

EXPLOSIVE_DEMO_SYMBOLS = [
    "PLAG",
    "EVNT",
    "GAPX",
    "NEWS",
    "RVOL",
    "FLOT",
    "MOMO",
    "HALT",
    "VOLA",
    "CATL",
    "SURG",
    "PULS",
    "RIPR",
    "FIRE",
    "WAVE",
]


class DemoProvider:
    name = "demo"

    async def get_snapshots(
        self, symbols: list[str], as_of: datetime, config: ScanConfig
    ) -> tuple[list[MarketSnapshot], list[str]]:
        benchmark = _bars("SPY", as_of, 96, beta_factor=1.0, base=55)
        snapshots: list[MarketSnapshot] = []
        for index, symbol in enumerate(symbols):
            base = 18 + index * 2.7
            if base > 140:
                base = 25 + index
            bars = _bars(symbol, as_of, 96, beta_factor=1.25 + (index % 4) * 0.12, base=base)
            previous = bars[-1].close
            price = previous * (1.022 + (index % 3) * 0.003)
            spread = price * (0.0008 + (index % 3) * 0.0002)
            historical = tuple(48_000 + day * 900 + index * 110 for day in range(12))
            current = int(sum(historical) / len(historical) * (1.72 + (index % 5) * 0.12))
            catalysts = (
                Catalyst(
                    "news",
                    f"Demo catalyst for {symbol} — replace with verified live headline",
                    as_of - timedelta(hours=2),
                ),
            )
            snapshots.append(
                MarketSnapshot(
                    symbol=symbol,
                    price=price,
                    quote=Quote(price - spread / 2, price + spread / 2, as_of),
                    daily_bars=tuple(bars),
                    benchmark_bars=tuple(benchmark),
                    current_premarket_volume=current,
                    historical_premarket_volumes=historical,
                    catalysts=catalysts,
                    data_as_of=as_of,
                )
            )
        return snapshots, [
            "DEMO DATA: deterministic synthetic prices, volume, quotes, and catalysts; "
            "do not trade."
        ]

    async def get_explosive_snapshots(
        self, symbols: list[str], as_of: datetime, config: ExplosiveConfig
    ) -> tuple[list[MarketSnapshot], list[str]]:
        del config
        benchmark = _bars("SPY", as_of, 96, beta_factor=1.0, base=55)
        snapshots: list[MarketSnapshot] = []
        for index, symbol in enumerate(symbols):
            bars = _event_bars(as_of, base=0.55 + index * 0.23)
            previous = bars[-1].close
            gap = 1.25 + (index % 5) * 0.22
            price = previous * gap
            spread = price * (0.004 + (index % 3) * 0.001)
            historical = tuple(8_000 + day * 400 + index * 50 for day in range(12))
            current = 1_500_000 + index * 125_000
            snapshots.append(
                MarketSnapshot(
                    symbol=symbol,
                    price=price,
                    quote=Quote(price - spread / 2, price + spread / 2, as_of),
                    daily_bars=tuple(bars),
                    benchmark_bars=tuple(benchmark),
                    current_premarket_volume=current,
                    historical_premarket_volumes=historical,
                    catalysts=(
                        Catalyst(
                            "news",
                            f"Demo fresh commercial catalyst for {symbol}",
                            as_of - timedelta(hours=1),
                        ),
                    ),
                    data_as_of=as_of,
                    premarket_high=price * 1.05,
                    premarket_low=max(previous, price * 0.78),
                    shares_outstanding=11_000_000 + index * 1_000_000,
                    market_cap=price * (11_000_000 + index * 1_000_000),
                )
            )
        return snapshots, [
            "DEMO DATA: synthetic PLAG-style gaps, catalysts, quotes, and volume; do not trade."
        ]


def _bars(
    symbol: str,
    as_of: datetime,
    count: int,
    *,
    beta_factor: float,
    base: float,
) -> list[Bar]:
    del symbol
    start = as_of.astimezone(UTC).date() - timedelta(days=count * 2)
    bars: list[Bar] = []
    price = base
    market_price = base
    day = start
    index = 0
    while len(bars) < count:
        if day.weekday() < 5:
            market_return = 0.003 + math.sin(index * 0.73) * 0.009
            asset_return = 0.0035 + beta_factor * (market_return - 0.003)
            market_price *= 1 + market_return
            price *= 1 + asset_return
            # Range ~3% while closes remain directionally efficient.
            high = price * 1.016
            low = price * 0.984
            bars.append(
                Bar(
                    datetime.combine(day, datetime.min.time(), UTC),
                    price / (1 + asset_return),
                    high,
                    low,
                    price,
                    1_600_000 + (index % 7) * 90_000,
                )
            )
            index += 1
        day += timedelta(days=1)
    return bars


def _event_bars(as_of: datetime, *, base: float) -> list[Bar]:
    bars = _bars("event", as_of, 96, beta_factor=1.2, base=base)
    return [
        Bar(bar.timestamp, bar.open, bar.high * 1.04, bar.low * 0.96, bar.close, 85_000)
        for bar in bars
    ]
