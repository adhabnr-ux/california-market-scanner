from __future__ import annotations

import json
from pathlib import Path

from market_scanner.cli import main


def test_demo_cli_writes_all_reports(tmp_path: Path) -> None:
    code = main(["scan", "--provider", "demo", "--output-dir", str(tmp_path)])
    assert code == 0
    assert {path.suffix for path in tmp_path.iterdir()} == {".json", ".csv", ".md", ".html"}
    report = json.loads((tmp_path / "market-scan.json").read_text(encoding="utf-8"))
    assert report["candidate_count"] == 15
    assert report["provider"] == "demo"
    assert all(candidate["passed_filters"] for candidate in report["candidates"])


def test_live_cli_fails_closed_without_credentials(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    assert main(["scan", "--provider", "alpaca", "--output-dir", str(tmp_path)]) == 2
    assert not list(tmp_path.iterdir())
