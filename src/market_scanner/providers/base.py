"""Provider protocol and shared utilities."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from market_scanner.models import MarketSnapshot, ScanConfig


class MarketDataProvider(Protocol):
    name: str

    async def get_snapshots(
        self, symbols: list[str], as_of: datetime, config: ScanConfig
    ) -> tuple[list[MarketSnapshot], list[str]]: ...
