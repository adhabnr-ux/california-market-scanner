"""PLAG-style event-momentum scanner.

This strategy is intentionally separate from the clean-trend strategy. It finds
fresh-news, low-priced stocks whose *current* premarket liquidity has expanded
dramatically; it does not relax the primary scanner's safer baseline.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from statistics import fmean

from market_scanner.indicators import atr_percent, relative_volume, return_beta, spread_percent
from market_scanner.models import Candidate, Catalyst, ExplosiveConfig, MarketSnapshot, ScanResult


def explosive_filter_descriptions(config: ExplosiveConfig) -> dict[str, str]:
    share_rule = f"≤{config.max_shares_outstanding:,} shares when data is available"
    if config.require_share_data:
        share_rule += " (data required)"
    return {
        "strategy": "fresh-catalyst explosive mover (separate from clean-trend mode)",
        "price": f"${config.min_price:g}–${config.max_price:g}",
        "average_volume": f">{config.min_average_volume:,} shares (20-session mean)",
        "gap": f"≥{config.min_gap_pct:g}% above previous close",
        "premarket_volume": f"≥{config.min_premarket_volume:,} shares by scan time",
        "premarket_dollar_volume": (
            f"≥${config.min_premarket_dollar_volume:,.0f} approximate (shares × latest price)"
        ),
        "rvol": f"≥{config.min_rvol:g}× same-window premarket volume",
        "spread": f"≤{config.max_spread_pct:g}% of quote midpoint",
        "momentum": (f"≤{config.max_distance_from_premarket_high_pct:g}% below premarket high"),
        "catalyst": (f"verified news ≤{config.max_catalyst_age_hours:g}h old or upcoming earnings"),
        "share_structure": share_rule,
        "watchlist_size": f"up to {config.watchlist_size}; never padded",
    }


def _fresh_external_catalysts(
    catalysts: tuple[Catalyst, ...], as_of: datetime, max_age_hours: float
) -> list[Catalyst]:
    cutoff = as_of.astimezone(UTC) - timedelta(hours=max_age_hours)
    result: list[Catalyst] = []
    for catalyst in catalysts:
        if catalyst.kind == "gap":
            continue
        if catalyst.kind == "earnings" or (
            catalyst.timestamp is not None and catalyst.timestamp.astimezone(UTC) >= cutoff
        ):
            result.append(catalyst)
    return result


def explosive_eligibility(
    *,
    config: ExplosiveConfig,
    price: float,
    average_volume: float,
    gap_pct: float,
    premarket_volume: int,
    premarket_dollar_volume: float,
    rvol: float,
    spread_pct: float,
    distance_from_high_pct: float,
    has_fresh_catalyst: bool,
    shares_outstanding: int | None,
) -> dict[str, bool]:
    share_pass = shares_outstanding is None or shares_outstanding <= config.max_shares_outstanding
    if config.require_share_data and shares_outstanding is None:
        share_pass = False
    return {
        "price": config.min_price <= price <= config.max_price,
        "average_volume": average_volume > config.min_average_volume,
        "positive_gap": gap_pct >= config.min_gap_pct,
        "premarket_volume": premarket_volume >= config.min_premarket_volume,
        "premarket_dollar_volume": (premarket_dollar_volume >= config.min_premarket_dollar_volume),
        "rvol": rvol >= config.min_rvol,
        "spread": spread_pct <= config.max_spread_pct,
        "near_premarket_high": (
            distance_from_high_pct <= config.max_distance_from_premarket_high_pct
        ),
        "fresh_external_catalyst": has_fresh_catalyst,
        "share_structure": share_pass,
    }


def _risk_flags(
    snapshot: MarketSnapshot,
    *,
    gap_pct: float,
    spread_pct: float,
    average_volume: float,
) -> list[str]:
    flags = [
        "Review current SEC filings for ATM, shelf, warrant, reverse-split, and going-concern risk."
    ]
    if snapshot.shares_outstanding is None:
        flags.append("Shares/float unavailable; verify independently before any trade.")
    if snapshot.price < 1:
        flags.append("Sub-$1 security: listing, manipulation, and financing risk are elevated.")
    if gap_pct >= 100:
        flags.append("Extreme ≥100% gap: LULD halts, slippage, and violent mean reversion likely.")
    if spread_pct >= 1:
        flags.append("Spread is ≥1%; market orders can create material slippage.")
    if snapshot.current_premarket_volume > average_volume * 10:
        flags.append(
            "Premarket turnover exceeds 10× ADV; crowding and exhaustion risk are elevated."
        )
    return flags


def _evaluate_explosive(
    snapshot: MarketSnapshot, config: ExplosiveConfig, as_of: datetime
) -> Candidate | tuple[str, ...]:
    if len(snapshot.daily_bars) < 20:
        return ("insufficient_history",)
    try:
        price = snapshot.price
        average_volume = fmean(bar.volume for bar in snapshot.daily_bars[-20:])
        spread_pct = spread_percent(snapshot.quote.bid, snapshot.quote.ask)
        rvol = relative_volume(
            snapshot.current_premarket_volume, snapshot.historical_premarket_volumes
        )
        atr_pct = atr_percent(snapshot.daily_bars, price)
    except (ValueError, ZeroDivisionError):
        return ("invalid_or_insufficient_data",)

    previous_close = snapshot.daily_bars[-1].close
    gap_pct = (price / previous_close - 1) * 100 if previous_close else 0.0
    premarket_high = snapshot.premarket_high or price
    premarket_low = snapshot.premarket_low or min(price, previous_close)
    distance_from_high = max(0.0, (premarket_high - price) / premarket_high * 100)
    dollar_volume = snapshot.current_premarket_volume * price
    fresh_catalysts = _fresh_external_catalysts(
        snapshot.catalysts, as_of, config.max_catalyst_age_hours
    )
    gates = explosive_eligibility(
        config=config,
        price=price,
        average_volume=average_volume,
        gap_pct=gap_pct,
        premarket_volume=snapshot.current_premarket_volume,
        premarket_dollar_volume=dollar_volume,
        rvol=rvol,
        spread_pct=spread_pct,
        distance_from_high_pct=distance_from_high,
        has_fresh_catalyst=bool(fresh_catalysts),
        shares_outstanding=snapshot.shares_outstanding,
    )
    if not all(gates.values()):
        return tuple(name for name, passed in gates.items() if not passed)

    try:
        beta = return_beta(snapshot.daily_bars, snapshot.benchmark_bars)
    except ValueError:
        beta = 0.0
    risk_pct = min(max(atr_pct, 8.0), 15.0)
    stop = max(premarket_low, price * (1 - risk_pct / 100))
    if stop >= price:
        stop = price * 0.90
    per_share_risk = price - stop
    target = price + per_share_risk * config.reward_to_risk
    shares = int(config.risk_per_trade_dollars // per_share_risk) if per_share_risk else 0
    flags = _risk_flags(
        snapshot, gap_pct=gap_pct, spread_pct=spread_pct, average_volume=average_volume
    )
    score = (
        min(gap_pct / 150, 1) * 25
        + min(rvol / 30, 1) * 25
        + min(dollar_volume / 10_000_000, 1) * 20
        + max(0, 1 - spread_pct / config.max_spread_pct) * 10
        + max(0, 1 - distance_from_high / config.max_distance_from_premarket_high_pct) * 10
        + (10 if snapshot.shares_outstanding is not None else 0)
    )
    catalysts = [*fresh_catalysts, Catalyst("gap", f"Premarket gap {gap_pct:+.2f}%")]
    as_of_value = snapshot.data_as_of or snapshot.quote.timestamp
    return Candidate(
        symbol=snapshot.symbol,
        price=round(price, 4),
        avg_volume=round(average_volume),
        current_volume=snapshot.current_premarket_volume,
        rvol=round(rvol, 3),
        rvol_method=snapshot.rvol_method,
        atr_percent=round(atr_pct, 3),
        beta=round(beta, 3),
        spread_percent=round(spread_pct, 4),
        gap_percent=round(gap_pct, 3),
        trend="event momentum",
        trend_score=round(max(0.0, 100 - distance_from_high), 2),
        levels={
            "premarket_low": round(premarket_low, 2),
            "premarket_high": round(premarket_high, 2),
        },
        catalysts=[item.description for item in catalysts],
        catalyst_details=[
            {
                "kind": item.kind,
                "description": item.description,
                "timestamp": item.timestamp.isoformat() if item.timestamp else None,
                "url": item.url,
            }
            for item in catalysts
        ],
        thesis=(
            f"Fresh catalyst with {gap_pct:+.1f}% gap and {rvol:.1f}× aligned RVOL; "
            f"only consider a defined setup that holds/reclaims the ${premarket_high:.2f} "
            "premarket-high area—do not chase extension."
        ),
        stop=round(stop, 2),
        target=round(target, 2),
        risk=(
            f"${per_share_risk:.2f}/share; at most {shares} shares for "
            f"${config.risk_per_trade_dollars:.0f} planned risk. Stops may fail during halts."
        ),
        score=round(score, 2),
        data_as_of=as_of_value.isoformat(),
        passed_filters=gates,
        strategy="explosive",
        premarket_dollar_volume=round(dollar_volume, 2),
        premarket_high=round(premarket_high, 4),
        distance_from_premarket_high_pct=round(distance_from_high, 3),
        shares_outstanding=snapshot.shares_outstanding,
        market_cap=snapshot.market_cap,
        risk_flags=flags,
    )


async def scan_explosive_market(
    provider, symbols: list[str], config: ExplosiveConfig, as_of: datetime | None = None
) -> ScanResult:
    now = as_of or datetime.now(UTC)
    getter = getattr(provider, "get_explosive_snapshots", provider.get_snapshots)
    snapshots, provider_warnings = await getter(symbols, now, config)
    qualified: list[Candidate] = []
    rejected: Counter[str] = Counter()
    for snapshot in snapshots:
        result = _evaluate_explosive(snapshot, config, now)
        if isinstance(result, Candidate):
            qualified.append(result)
        else:
            rejected.update(result)
    qualified.sort(key=lambda item: (-item.score, item.symbol))
    qualified = [
        replace(item, rank=rank)
        for rank, item in enumerate(qualified[: config.watchlist_size], start=1)
    ]
    warnings = [
        *provider_warnings,
        (
            "Explosive-mover mode is high-risk event detection, not a buy signal. "
            "Halts can bypass stops."
        ),
    ]
    if not qualified:
        warnings.append("No symbols passed every explosive-mover gate; results were not padded.")
    return ScanResult(
        candidates=qualified,
        generated_at=datetime.now(UTC).isoformat(),
        data_as_of=min((item.data_as_of for item in qualified), default=None),
        provider=provider.name,
        symbols_scanned=len(symbols),
        symbols_qualified=len(qualified),
        filters=explosive_filter_descriptions(config),
        warnings=warnings,
        rejection_counts=dict(sorted(rejected.items())),
        strategy="explosive",
    )
