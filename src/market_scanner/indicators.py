"""Deterministic, dependency-free market indicators."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean

from market_scanner.models import Bar


def average_true_range(bars: Sequence[Bar], period: int = 14) -> float:
    if len(bars) < period + 1:
        raise ValueError(f"ATR requires at least {period + 1} bars")
    ranges: list[float] = []
    for previous, current in zip(bars[-period - 1 : -1], bars[-period:], strict=True):
        ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return fmean(ranges)


def atr_percent(bars: Sequence[Bar], price: float, period: int = 14) -> float:
    if price <= 0:
        raise ValueError("price must be positive")
    return average_true_range(bars, period) / price * 100


def return_beta(asset: Sequence[Bar], benchmark: Sequence[Bar], period: int = 60) -> float:
    asset_by_date = {bar.timestamp.date(): bar.close for bar in asset}
    benchmark_by_date = {bar.timestamp.date(): bar.close for bar in benchmark}
    dates = sorted(asset_by_date.keys() & benchmark_by_date.keys())[-(period + 1) :]
    if len(dates) < period + 1:
        raise ValueError(f"beta requires at least {period + 1} aligned bars")
    asset_returns = [
        asset_by_date[current] / asset_by_date[previous] - 1
        for previous, current in zip(dates[:-1], dates[1:], strict=True)
    ]
    market_returns = [
        benchmark_by_date[current] / benchmark_by_date[previous] - 1
        for previous, current in zip(dates[:-1], dates[1:], strict=True)
    ]
    market_mean = fmean(market_returns)
    asset_mean = fmean(asset_returns)
    covariance = fmean(
        (asset_return - asset_mean) * (market_return - market_mean)
        for asset_return, market_return in zip(asset_returns, market_returns, strict=True)
    )
    variance = fmean((market_return - market_mean) ** 2 for market_return in market_returns)
    if variance == 0:
        raise ValueError("benchmark variance is zero")
    return covariance / variance


def relative_volume(current: int, historical_same_window: Sequence[int]) -> float:
    usable = [value for value in historical_same_window if value > 0]
    if not usable:
        raise ValueError("RVOL requires prior same-window volume")
    return current / fmean(usable)


def spread_percent(bid: float, ask: float) -> float:
    if bid <= 0 or ask <= 0 or ask < bid:
        raise ValueError("quote must contain a valid positive bid/ask")
    midpoint = (bid + ask) / 2
    return (ask - bid) / midpoint * 100


def trend_structure(bars: Sequence[Bar]) -> tuple[bool, str, float]:
    """Quantify trend using MA alignment, 20-day slope, and path efficiency."""
    if len(bars) < 50:
        raise ValueError("trend requires at least 50 bars")
    closes = [bar.close for bar in bars]
    last = closes[-1]
    sma20 = fmean(closes[-20:])
    sma50 = fmean(closes[-50:])
    slope = (fmean(closes[-5:]) - fmean(closes[-20:-15])) / fmean(closes[-20:-15])
    travel = sum(
        abs(right - left) for left, right in zip(closes[-20:-1], closes[-19:], strict=True)
    )
    efficiency = abs(closes[-1] - closes[-20]) / travel if travel else 0.0
    up = last > sma20 > sma50 and slope > 0.01
    down = last < sma20 < sma50 and slope < -0.01
    clean = (up or down) and efficiency >= 0.25
    direction = "uptrend" if up else "downtrend" if down else "mixed"
    score = min(100.0, max(0.0, efficiency * 100 + min(abs(slope) * 500, 30)))
    return clean, direction, score


def key_levels(bars: Sequence[Bar], lookback: int = 20) -> tuple[bool, float, float]:
    if len(bars) < lookback + 1:
        raise ValueError("levels require more history")
    window = bars[-lookback - 1 : -1]
    support = min(bar.low for bar in window)
    resistance = max(bar.high for bar in window)
    price = bars[-1].close
    clear = support < price and resistance > support and (resistance - support) / price >= 0.04
    return clear, support, resistance
