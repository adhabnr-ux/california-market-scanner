from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market_scanner.models import ScanConfig
from market_scanner.providers.alpaca import (
    EASTERN,
    AlpacaProvider,
    ProviderError,
    _parse_time,
    _same_window_volumes,
)


def test_alpaca_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    with pytest.raises(ProviderError, match="credentials missing"):
        AlpacaProvider()


def test_nanosecond_timestamp_is_parsed_safely() -> None:
    parsed = _parse_time("2026-08-11T13:00:00.123456789Z")
    assert parsed == datetime(2026, 8, 11, 13, 0, 0, 123456, tzinfo=UTC)


def test_rvol_windows_align_by_eastern_time() -> None:
    rows = [
        {"t": "2026-08-10T12:59:00Z", "v": 10},  # 08:59 EDT
        {"t": "2026-08-10T13:01:00Z", "v": 999},  # after cutoff
        {"t": "2026-08-11T12:30:00Z", "v": 30},  # 08:30 EDT
        {"t": "2026-08-11T10:00:00Z", "v": 20},  # 06:00 EDT
        {"t": "2026-08-11T07:59:00Z", "v": 999},  # before 04:00 EDT
    ]
    as_of = datetime(2026, 8, 11, 9, 0, tzinfo=EASTERN)
    volumes = _same_window_volumes(rows, as_of)
    assert volumes[datetime(2026, 8, 10).date()] == 10
    assert volumes[datetime(2026, 8, 11).date()] == 50


def test_alpaca_adapter_normalizes_batched_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APCA_API_KEY_ID", "test-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test-secret")
    provider = AlpacaProvider()
    as_of = datetime(2026, 8, 11, 9, 0, tzinfo=EASTERN)
    start = as_of - timedelta(days=140)

    def row(index: int, *, benchmark: bool = False) -> dict:
        market_move = 0.003 + ((index % 7) - 3) * 0.002
        factor = 1.0 if benchmark else 1.4
        close = 40 * (1.004**index) * (1 + market_move * factor)
        return {
            "t": (start + timedelta(days=index)).astimezone(UTC).isoformat(),
            "o": close * 0.997,
            "h": close * 1.016,
            "l": close * 0.984,
            "c": close,
            "v": 2_000_000,
        }

    daily = {
        "TEST": [row(index) for index in range(90)],
        "SPY": [row(index, benchmark=True) for index in range(90)],
    }
    minute = {
        "TEST": [
            {"t": "2026-08-10T12:30:00Z", "v": 100_000},
            {"t": "2026-08-11T12:30:00Z", "v": 200_000},
        ]
    }
    monkeypatch.setattr(
        provider,
        "_paged",
        lambda _path, params, _field: daily if params["timeframe"] == "1Day" else minute,
    )
    monkeypatch.setattr(
        provider,
        "_get",
        lambda _path, _params: {
            "TEST": {
                "latestQuote": {"bp": 58.0, "ap": 58.05, "t": "2026-08-11T13:00:00Z"},
                "latestTrade": {"p": 58.02, "t": "2026-08-11T13:00:00Z"},
                "minuteBar": {"c": 58.02, "t": "2026-08-11T13:00:00Z"},
            }
        },
    )
    monkeypatch.setattr(provider, "_news", lambda _symbols, _as_of: {})
    monkeypatch.setattr(provider, "_earnings", lambda _as_of: {})

    snapshots, warnings = provider._get_snapshots_sync(["TEST"], as_of, ScanConfig())
    assert len(snapshots) == 1
    assert snapshots[0].symbol == "TEST"
    assert snapshots[0].current_premarket_volume == 200_000
    assert snapshots[0].historical_premarket_volumes == (100_000,)
    assert len(snapshots[0].daily_bars) == 90
    assert any("IEX" in warning for warning in warnings)
