from __future__ import annotations

import asyncio

from market_scanner.config import load_symbols
from market_scanner.models import ScanConfig
from market_scanner.providers import DemoProvider
from market_scanner.scanner import scan_market
from market_scanner.scoring import all_eligible, eligibility


def test_exact_filter_boundaries_and_strict_gates() -> None:
    config = ScanConfig()
    base = dict(
        config=config,
        price=5.0,
        average_volume=1_000_001,
        spread_pct=0.30,
        atr_pct=2.0,
        beta=1.01,
        rvol=1.51,
        clean_trend=True,
        clear_levels=True,
        has_catalyst=True,
    )
    assert all_eligible(eligibility(**base))
    for field, boundary in (
        ("average_volume", 1_000_000),
        ("beta", 1.0),
        ("rvol", 1.5),
    ):
        values = {**base, field: boundary}
        assert not eligibility(**values)[field if field != "average_volume" else "average_volume"]
    assert eligibility(**{**base, "price": 150.0})["price"]
    assert eligibility(**{**base, "atr_pct": 5.0})["atr"]
    assert not eligibility(**{**base, "spread_pct": 0.301})["tight_spread"]
    assert not eligibility(**{**base, "has_catalyst": False})["catalyst"]


def test_demo_scan_caps_at_15_and_every_result_passes_every_gate() -> None:
    result = asyncio.run(scan_market(DemoProvider(), load_symbols(), ScanConfig()))
    assert result.symbols_scanned == 30
    assert len(result.candidates) == 15
    assert [item.rank for item in result.candidates] == list(range(1, 16))
    assert all(all(item.passed_filters.values()) for item in result.candidates)
    assert all(item.avg_volume > 1_000_000 for item in result.candidates)
    assert all(item.rvol > 1.5 and item.beta > 1 for item in result.candidates)
    assert all(2 <= item.atr_percent <= 5 for item in result.candidates)
    assert all(
        item.thesis and item.stop and item.target and item.risk for item in result.candidates
    )


def test_scanner_never_pads_when_fewer_than_ten_pass() -> None:
    result = asyncio.run(scan_market(DemoProvider(), ["AMD"], ScanConfig()))
    assert len(result.candidates) == 1
    assert any("not padded" in warning for warning in result.warnings)
