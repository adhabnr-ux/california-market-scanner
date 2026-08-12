"""Alpaca REST adapter using only Python's standard library."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from market_scanner.models import Bar, Catalyst, MarketSnapshot, Quote, ScanConfig

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
        self._earnings_warning: str | None = None
        if not self.key_id or not self.secret:
            raise ProviderError(
                "Alpaca credentials missing. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY."
            )

    async def get_snapshots(
        self, symbols: list[str], as_of: datetime, config: ScanConfig
    ) -> tuple[list[MarketSnapshot], list[str]]:
        return await asyncio.to_thread(self._get_snapshots_sync, symbols, as_of, config)

    def _get_snapshots_sync(
        self, symbols: list[str], as_of: datetime, config: ScanConfig
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
        payload = self._get(
            "/v1beta1/news",
            {
                "symbols": ",".join(symbols),
                "start": (as_of - timedelta(days=3)).date().isoformat(),
                "end": as_of.date().isoformat(),
                "limit": "50",
                "sort": "desc",
            },
        )
        result: dict[str, list[Catalyst]] = defaultdict(list)
        for item in payload.get("news", []):
            for symbol in item.get("symbols", []):
                if symbol in symbols and len(result[symbol]) < 3:
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
