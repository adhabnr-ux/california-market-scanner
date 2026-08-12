from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market_scanner.indicators import (
    atr_percent,
    key_levels,
    relative_volume,
    return_beta,
    spread_percent,
    trend_structure,
)
from market_scanner.models import Bar


def bars_from_returns(returns: list[float], *, multiplier: float = 1.0) -> list[Bar]:
    price = 50.0
    start = datetime(2026, 1, 1, tzinfo=UTC)
    result: list[Bar] = []
    for index, value in enumerate([0.0, *returns]):
        previous = price
        price *= 1 + value * multiplier
        result.append(
            Bar(
                start + timedelta(days=index),
                previous,
                price * 1.016,
                price * 0.984,
                price,
                2_000_000,
            )
        )
    return result


def test_beta_matches_known_linear_returns() -> None:
    returns = [0.004 + ((index % 7) - 3) * 0.003 for index in range(70)]
    benchmark = bars_from_returns(returns)
    asset = bars_from_returns(returns, multiplier=1.5)
    assert return_beta(asset, benchmark) == pytest.approx(1.5, abs=0.03)


def test_market_metrics_and_structure() -> None:
    returns = [0.004 + ((index % 5) - 2) * 0.001 for index in range(80)]
    bars = bars_from_returns(returns, multiplier=1.3)
    clean, direction, score = trend_structure(bars)
    levels, support, resistance = key_levels(bars)
    assert 2 <= atr_percent(bars, bars[-1].close) <= 5
    assert (clean, direction) == (True, "uptrend")
    assert score >= 25
    assert levels and support < resistance


def test_spread_and_time_adjusted_relative_volume() -> None:
    assert spread_percent(99.9, 100.1) == pytest.approx(0.2)
    assert relative_volume(300_000, [100_000, 200_000, 150_000]) == 2.0
    with pytest.raises(ValueError):
        relative_volume(1, [])
