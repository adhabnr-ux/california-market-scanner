"""TOML configuration and symbol-universe loading."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from market_scanner.models import ScanConfig

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DATA = Path(__file__).with_name("data")


def load_config(path: str | Path | None = None) -> tuple[ScanConfig, dict, dict]:
    requested = path or os.environ.get("MARKET_SCANNER_CONFIG")
    if requested:
        config_path = Path(requested)
        if not config_path.exists():
            raise FileNotFoundError(f"config file not found: {config_path}")
    else:
        repository_config = ROOT / "config/scanner.toml"
        config_path = (
            repository_config if repository_config.exists() else PACKAGE_DATA / "scanner.toml"
        )
    with config_path.open("rb") as handle:
        payload = tomllib.load(handle)
    scanner_values = payload.get("scanner", {})
    known = set(ScanConfig.__dataclass_fields__)
    unknown = set(scanner_values) - known
    if unknown:
        raise ValueError(f"Unknown scanner config keys: {', '.join(sorted(unknown))}")
    return ScanConfig(**scanner_values), payload.get("provider", {}), payload.get("output", {})


def load_symbols(path: str | Path | None = None) -> list[str]:
    if path:
        universe_path = Path(path)
        if not universe_path.exists():
            raise FileNotFoundError(f"universe file not found: {universe_path}")
    else:
        repository_universe = ROOT / "config/universe.txt"
        universe_path = (
            repository_universe if repository_universe.exists() else PACKAGE_DATA / "universe.txt"
        )
    lines = universe_path.read_text(encoding="utf-8").splitlines()
    symbols = [line.strip().upper() for line in lines if line.strip() and not line.startswith("#")]
    if not symbols:
        raise ValueError("symbol universe is empty")
    return list(dict.fromkeys(symbols))
