"""Alpaca REST adapter using only Python's standard library."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from market_scanner.models import (
    Bar,
    Catalyst,
    ExplosiveConfig,
    MarketSnapshot,
    Quote,
    ScanConfig,
)

EASTERN = ZoneInfo("America/New_York")


class ProviderError(RuntimeError):
    """Safe provider failure with no credential content."""


class AlpacaProvider:
    name = "alpaca"

    def __init__(self, *, feed: str = "iex", timeout: int = 30) -> None:
        self.key_id = os.environ.get("APCA_API_KEY_ID", "")
        self.secret = os.environ.get("APCA_API_SECRET_KEY", "")
        self.finnhub_key = os.environ.get("FINNHUB_API_KEY", "")
        self.feed = feed
        self.timeout = timeout
        self.base_url = "https://data.alpaca.markets"
        self.trading_url = "https://api.alpaca.markets"
        self._earnings_warning: str | None = None
        if not self.key_id or not self.secret:
            raise ProviderError(
                "Alpaca credentials missing. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY."
            )

    async def get_snapshots(
        self, symbols: list[str], as_of: datetime, config: ScanConfig
    ) -> tuple[list[MarketSnapshot], list[str]]:
        return await asyncio.to_thread(self._get_snapshots_sync, symbols, as_of, config)

    async def discover_symbols(self) -> list[str]:
        """Return active tradable US equities for broad explosive-mover discovery."""
        return await asyncio.to_thread(self._discover_symbols_sync)

    def _discover_symbols_sync(self) -> list[str]:
        assets = self._get_url(f"{self.trading_url}/v2/assets?status=active&asset_class=us_equity")
        exchanges = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS"}
        return sorted(
            asset["symbol"]
            for asset in assets
            if asset.get("tradable")
            and asset.get("status") == "active"
            and asset.get("exchange") in exchanges
            and isinstance(asset.get("symbol"), str)
        )

    async def get_explosive_snapshots(
        self, symbols: list[str], as_of: datetime, config: ExplosiveConfig
    ) -> tuple[list[MarketSnapshot], list[str]]:
        return await asyncio.to_thread(self._get_explosive_snapshots_sync, symbols, as_of, config)

    def _get_explosive_snapshots_sync(
        self, symbols: list[str], as_of: datetime, config: ExplosiveConfig
    ) -> tuple[list[MarketSnapshot], list[str]]:
        clean_symbols = list(dict.fromkeys(symbol.upper() for symbol in symbols if symbol))
        if len(clean_symbols) > config.shortlist_limit:
            snapshots = self._bulk_snapshots(clean_symbols)
            preliminary: list[tuple[float, str]] = []
            for symbol, snapshot in snapshots.items():
                trade = snapshot.get("latestTrade") or {}
                minute = snapshot.get("minuteBar") or {}
                previous = snapshot.get("prevDailyBar") or {}
                price = float(trade.get("p") or minute.get("c") or 0)
                previous_close = float(previous.get("c") or 0)
                if not price or not previous_close:
                    continue
                gap_pct = (price / previous_close - 1) * 100
                if config.min_price <= price <= config.max_price and gap_pct >= config.min_gap_pct:
                    preliminary.append((gap_pct, symbol))
            preliminary.sort(reverse=True)
            shortlisted = [symbol for _, symbol in preliminary[: config.shortlist_limit]]
        else:
            shortlisted = clean_symbols
        if not shortlisted:
            return [], [
                f"Broad prefilter found 0 candidates across {len(clean_symbols):,} active symbols."
            ]
        results, warnings = self._get_snapshots_sync(shortlisted, as_of, config)
        profiles = self._profiles(shortlisted)
        enriched = [
            replace(
                snapshot,
                shares_outstanding=profiles.get(snapshot.symbol, {}).get("shares_outstanding"),
                market_cap=profiles.get(snapshot.symbol, {}).get("market_cap"),
            )
            for snapshot in results
        ]
        warnings.append(
            f"Broad prefilter reduced {len(clean_symbols):,} symbols to "
            f"{len(shortlisted):,} gap/price candidates before history requests."
        )
        if not self.finnhub_key:
            warnings.append(
                "Share-count filter is advisory: FINNHUB_API_KEY is not configured; verify float."
            )
        return enriched, warnings

    def _get_snapshots_sync(
        self, symbols: list[str], as_of: datetime, config: ScanConfig | ExplosiveConfig
    ) -> tuple[list[MarketSnapshot], list[str]]:
        clean_symbols = list(dict.fromkeys(symbol.upper() for symbol in symbols if symbol))
        requested = list(dict.fromkeys([*clean_symbols, "SPY"]))
        start = (as_of.date() - timedelta(days=max(config.history_days * 2, 150))).isoformat()
        end = as_of.astimezone(UTC).isoformat().replace("+00:00", "Z")
        symbol_param = ",".join(requested)
        daily = self._paged(
            "/v2/stocks/bars",
            {
                "symbols": symbol_param,
                "timeframe": "1Day",
                "start": start,
                "end": end,
                "adjustment": "all",
                "feed": self.feed,
                "limit": "10000",
                "sort": "asc",
            },
            "bars",
        )
        snapshot_json = self._get(
            "/v2/stocks/snapshots", {"symbols": ",".join(clean_symbols), "feed": self.feed}
        )
        minute_start = (as_of.astimezone(EASTERN).date() - timedelta(days=35)).isoformat()
        minutes = self._paged(
            "/v2/stocks/bars",
            {
                "symbols": ",".join(clean_symbols),
                "timeframe": "1Min",
                "start": minute_start,
                "end": end,
                "adjustment": "all",
                "feed": self.feed,
                "limit": "10000",
                "sort": "asc",
            },
            "bars",
        )
        news = self._news(clean_symbols, as_of)
        earnings = self._earnings(as_of)
        benchmark = tuple(_bar(row) for row in daily.get("SPY", []))
        warnings = [
            f"Alpaca {self.feed.upper()} feed used; verify coverage and entitlement before trading."
        ]
        if not self.finnhub_key:
            warnings.append("Upcoming earnings unknown: FINNHUB_API_KEY is not configured.")
        elif self._earnings_warning:
            warnings.append(self._earnings_warning)
        results: list[MarketSnapshot] = []
        for symbol in clean_symbols:
            snap = snapshot_json.get(symbol)
            rows = daily.get(symbol, [])
            if not snap or not rows:
                continue
            quote_row = snap.get("latestQuote") or {}
            trade_row = snap.get("latestTrade") or {}
            minute_row = snap.get("minuteBar") or {}
            price = float(trade_row.get("p") or minute_row.get("c") or rows[-1]["c"])
            bid, ask = float(quote_row.get("bp") or 0), float(quote_row.get("ap") or 0)
            if not bid or not ask:
                continue
            quote_time = _parse_time(quote_row.get("t") or trade_row.get("t") or end)
            volumes = _same_window_volumes(minutes.get(symbol, []), as_of)
            today = as_of.astimezone(EASTERN).date()
            current_volume = volumes.pop(today, 0)
            prior_volumes = tuple(value for _, value in sorted(volumes.items())[-20:])
            premarket_high, premarket_low = _current_premarket_range(minutes.get(symbol, []), as_of)
            catalysts = [*news.get(symbol, []), *earnings.get(symbol, [])]
            results.append(
                MarketSnapshot(
                    symbol=symbol,
                    price=price,
                    quote=Quote(bid, ask, quote_time),
                    daily_bars=tuple(_bar(row) for row in rows[-config.history_days :]),
                    benchmark_bars=benchmark[-config.history_days :],
                    current_premarket_volume=current_volume,
                    historical_premarket_volumes=prior_volumes,
                    catalysts=tuple(catalysts),
                    data_as_of=max(quote_time, _parse_time(minute_row.get("t") or end)),
                    premarket_high=premarket_high,
                    premarket_low=premarket_low,
                )
            )
        if len(results) < len(clean_symbols):
            warnings.append(
                f"Alpaca returned complete quote/history data for {len(results)} of "
                f"{len(clean_symbols)} requested symbols."
            )
        stale = [
            snapshot.symbol
            for snapshot in results
            if as_of.astimezone(UTC) - snapshot.data_as_of.astimezone(UTC) > timedelta(minutes=15)
        ]
        if stale:
            warnings.append(
                f"Stale market timestamps (>15 minutes) detected for {len(stale)} symbols; "
                "verify market session/holiday status."
            )
        return results, warnings

    def _get(self, path: str, params: dict[str, str]) -> dict:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        return self._get_url(url, path=path)

    def _get_url(self, url: str, *, path: str = "/v2/assets"):
        request = urllib.request.Request(
            url,
            headers={
                "APCA-API-KEY-ID": self.key_id,
                "APCA-API-SECRET-KEY": self.secret,
                "Accept": "application/json",
                "User-Agent": "california-market-scanner/0.1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise ProviderError(
                f"Alpaca request failed with HTTP {error.code} at {path}"
            ) from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ProviderError(
                f"Alpaca request failed at {path}: {type(error).__name__}"
            ) from error

    def _bulk_snapshots(self, symbols: list[str], chunk_size: int = 150) -> dict:
        combined: dict = {}
        for offset in range(0, len(symbols), chunk_size):
            chunk = symbols[offset : offset + chunk_size]
            combined.update(
                self._get(
                    "/v2/stocks/snapshots",
                    {"symbols": ",".join(chunk), "feed": self.feed},
                )
            )
        return combined

    def _paged(self, path: str, params: dict[str, str], field: str) -> dict[str, list[dict]]:
        combined: dict[str, list[dict]] = defaultdict(list)
        page_token: str | None = None
        while True:
            page_params = dict(params)
            if page_token:
                page_params["page_token"] = page_token
            payload = self._get(path, page_params)
            for symbol, values in (payload.get(field) or {}).items():
                combined[symbol].extend(values)
            page_token = payload.get("next_page_token")
            if not page_token:
                return dict(combined)

    def _news(self, symbols: list[str], as_of: datetime) -> dict[str, list[Catalyst]]:
        result: dict[str, list[Catalyst]] = defaultdict(list)
        symbol_set = set(symbols)
        # Chunking prevents one news-heavy ticker from consuming the result cap
        # for an entire explosive-mode shortlist.
        for offset in range(0, len(symbols), 10):
            chunk = symbols[offset : offset + 10]
            payload = self._get(
                "/v1beta1/news",
                {
                    "symbols": ",".join(chunk),
                    "start": (as_of - timedelta(days=3)).date().isoformat(),
                    "end": as_of.date().isoformat(),
                    "limit": "50",
                    "sort": "desc",
                },
            )
            for item in payload.get("news", []):
                for symbol in item.get("symbols", []):
                    if symbol in symbol_set and len(result[symbol]) < 3:
                        result[symbol].append(
                            Catalyst(
                                "news",
                                str(item.get("headline", "News catalyst")),
                                _parse_time(item["created_at"]) if item.get("created_at") else None,
                                item.get("url"),
                            )
                        )
        return dict(result)

    def _earnings(self, as_of: datetime) -> dict[str, list[Catalyst]]:
        if not self.finnhub_key:
            return {}
        start = as_of.date()
        end = start + timedelta(days=7)
        url = "https://finnhub.io/api/v1/calendar/earnings?" + urllib.parse.urlencode(
            {"from": start.isoformat(), "to": end.isoformat(), "token": self.finnhub_key}
        )
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            self._earnings_warning = (
                "Upcoming earnings unknown: Finnhub calendar request failed for this run."
            )
            return {}
        result: dict[str, list[Catalyst]] = defaultdict(list)
        for item in payload.get("earningsCalendar", []):
            symbol = item.get("symbol")
            if symbol:
                result[symbol].append(
                    Catalyst("earnings", f"Earnings scheduled {item.get('date', 'date unknown')}")
                )
        return dict(result)

    def _profiles(self, symbols: list[str]) -> dict[str, dict[str, float | int]]:
        if not self.finnhub_key:
            return {}
        result: dict[str, dict[str, float | int]] = {}
        for symbol in symbols:
            url = "https://finnhub.io/api/v1/stock/profile2?" + urllib.parse.urlencode(
                {"symbol": symbol, "token": self.finnhub_key}
            )
            try:
                with urllib.request.urlopen(url, timeout=self.timeout) as response:
                    profile = json.load(response)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                continue
            shares_millions = profile.get("shareOutstanding")
            market_cap_millions = profile.get("marketCapitalization")
            values: dict[str, float | int] = {}
            if shares_millions:
                values["shares_outstanding"] = int(float(shares_millions) * 1_000_000)
            if market_cap_millions:
                values["market_cap"] = float(market_cap_millions) * 1_000_000
            if values:
                result[symbol] = values
        return result


def _parse_time(value: str) -> datetime:
    # Alpaca may send nanoseconds; datetime accepts microseconds.
    normalized = value.replace("Z", "+00:00")
    if "." in normalized:
        head, tail = normalized.split(".", 1)
        fraction, offset = tail.split("+", 1) if "+" in tail else (tail, "00:00")
        normalized = f"{head}.{fraction[:6]}+{offset}"
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _bar(row: dict) -> Bar:
    return Bar(
        _parse_time(row["t"]),
        float(row["o"]),
        float(row["h"]),
        float(row["l"]),
        float(row["c"]),
        int(row["v"]),
    )


def _same_window_volumes(rows: list[dict], as_of: datetime) -> dict[date, int]:
    cutoff = as_of.astimezone(EASTERN).time().replace(tzinfo=None, second=0, microsecond=0)
    cutoff = min(cutoff, time(9, 29))
    result: dict[date, int] = defaultdict(int)
    for row in rows:
        timestamp = _parse_time(row["t"]).astimezone(EASTERN)
        local_time = timestamp.time().replace(tzinfo=None)
        if time(4, 0) <= local_time <= cutoff and timestamp.weekday() < 5:
            result[timestamp.date()] += int(row.get("v", 0))
    return dict(result)


def _current_premarket_range(
    rows: list[dict], as_of: datetime
) -> tuple[float | None, float | None]:
    local_date = as_of.astimezone(EASTERN).date()
    cutoff = as_of.astimezone(EASTERN).time().replace(tzinfo=None, second=0, microsecond=0)
    cutoff = min(cutoff, time(9, 29))
    current = []
    for row in rows:
        timestamp = _parse_time(row["t"]).astimezone(EASTERN)
        local_time = timestamp.time().replace(tzinfo=None)
        if (
            timestamp.date() == local_date
            and time(4, 0) <= local_time <= cutoff
            and row.get("h") is not None
            and row.get("l") is not None
        ):
            current.append(row)
    if not current:
        return None, None
    return max(float(row["h"]) for row in current), min(float(row["l"]) for row in current)
