"""Hard eligibility gates and transparent ranking."""

from __future__ import annotations

from collections.abc import Mapping

from market_scanner.models import ScanConfig


def eligibility(
    *,
    config: ScanConfig,
    price: float,
    average_volume: float,
    spread_pct: float,
    atr_pct: float,
    beta: float,
    rvol: float,
    clean_trend: bool,
    clear_levels: bool,
    has_catalyst: bool,
) -> dict[str, bool]:
    """Evaluate every named requirement; strict inequalities match the brief."""
    return {
        "price": config.min_price <= price <= config.max_price,
        "average_volume": average_volume > config.min_average_volume,
        "tight_spread": spread_pct <= config.max_spread_pct,
        "atr": config.min_atr_pct <= atr_pct <= config.max_atr_pct,
        "beta": beta > config.min_beta,
        "rvol": rvol > config.min_rvol,
        "clean_trend": clean_trend,
        "clear_levels": clear_levels,
        "catalyst": has_catalyst or not config.require_catalyst,
    }


def all_eligible(gates: Mapping[str, bool]) -> bool:
    return bool(gates) and all(gates.values())


def rank_score(
    *,
    rvol: float,
    atr_pct: float,
    beta: float,
    spread_pct: float,
    trend_score: float,
    catalyst_count: int,
    gap_pct: float,
) -> float:
    """Rank eligible names; no score can bypass a failed hard gate."""
    volatility_fit = max(0.0, 1 - abs(atr_pct - 3.5) / 1.5)
    score = (
        min(rvol / 3, 1) * 30
        + volatility_fit * 15
        + min(max(beta - 1, 0) / 1.5, 1) * 10
        + max(0.0, 1 - spread_pct / 0.30) * 10
        + min(trend_score / 100, 1) * 20
        + min(catalyst_count, 2) / 2 * 10
        + min(abs(gap_pct) / 5, 1) * 5
    )
    return round(score, 2)
