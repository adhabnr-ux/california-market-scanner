from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from market_scanner.explosive import explosive_eligibility, scan_explosive_market
from market_scanner.models import Catalyst, ExplosiveConfig
from market_scanner.providers.demo import EXPLOSIVE_DEMO_SYMBOLS, DemoProvider

AS_OF = datetime(2026, 8, 11, 13, 0, tzinfo=UTC)


def test_explosive_gates_are_explicit_and_inclusive() -> None:
    config = ExplosiveConfig()
    gates = explosive_eligibility(
        config=config,
        price=5,
        average_volume=50_001,
        gap_pct=20,
        premarket_volume=250_000,
        premarket_dollar_volume=1_000_000,
        rvol=5,
        spread_pct=2,
        distance_from_high_pct=15,
        has_fresh_catalyst=True,
        shares_outstanding=50_000_000,
    )

    assert all(gates.values())
    assert not explosive_eligibility(
        config=config,
        price=5,
        average_volume=50_001,
        gap_pct=19.99,
        premarket_volume=250_000,
        premarket_dollar_volume=1_000_000,
        rvol=5,
        spread_pct=2,
        distance_from_high_pct=15,
        has_fresh_catalyst=True,
        shares_outstanding=50_000_000,
    )["positive_gap"]


def test_demo_explosive_scan_returns_ranked_unpadded_watchlist() -> None:
    result = asyncio.run(
        scan_explosive_market(
            DemoProvider(), EXPLOSIVE_DEMO_SYMBOLS, ExplosiveConfig(), as_of=AS_OF
        )
    )

    assert result.strategy == "explosive"
    assert len(result.candidates) == 15
    assert {candidate.symbol for candidate in result.candidates} == set(EXPLOSIVE_DEMO_SYMBOLS)
    assert [candidate.rank for candidate in result.candidates] == list(range(1, 16))
    assert all(all(candidate.passed_filters.values()) for candidate in result.candidates)
    assert all(candidate.premarket_dollar_volume >= 1_000_000 for candidate in result.candidates)
    assert all(candidate.risk_flags for candidate in result.candidates)


def test_stale_news_is_rejected_even_when_gap_and_volume_pass() -> None:
    class StaleProvider(DemoProvider):
        async def get_explosive_snapshots(self, symbols, as_of, config):
            snapshots, warnings = await super().get_explosive_snapshots(symbols, as_of, config)
            stale = replace(
                snapshots[0],
                catalysts=(
                    Catalyst(
                        "news",
                        "Old headline",
                        as_of - timedelta(hours=config.max_catalyst_age_hours + 1),
                    ),
                    Catalyst("news", "Undated headline"),
                ),
            )
            return [stale], warnings

    result = asyncio.run(
        scan_explosive_market(StaleProvider(), ["PLAG"], ExplosiveConfig(), as_of=AS_OF)
    )

    assert result.candidates == []
    assert result.rejection_counts == {"fresh_external_catalyst": 1}
    assert any("not padded" in warning for warning in result.warnings)


def test_unknown_share_count_is_advisory_unless_required() -> None:
    base = dict(
        price=5,
        average_volume=100_000,
        gap_pct=25,
        premarket_volume=500_000,
        premarket_dollar_volume=2_500_000,
        rvol=10,
        spread_pct=1,
        distance_from_high_pct=5,
        has_fresh_catalyst=True,
        shares_outstanding=None,
    )

    assert explosive_eligibility(config=ExplosiveConfig(), **base)["share_structure"]
    assert not explosive_eligibility(config=ExplosiveConfig(require_share_data=True), **base)[
        "share_structure"
    ]
