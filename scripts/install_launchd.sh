#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_PATH="$HOME/Library/LaunchAgents/com.market-scanner.daily.plist"
LOG_DIR="$PROJECT_DIR/artifacts/logs"

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

if [[ ! -x "$PROJECT_DIR/.venv/bin/market-scanner" ]]; then
  echo "Create the project environment first:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 1
fi

python3 - "$PROJECT_DIR" "$PLIST_PATH" <<'PY'
import plistlib
import sys
from pathlib import Path

project = Path(sys.argv[1]).resolve()
destination = Path(sys.argv[2])
payload = {
    "Label": "com.market-scanner.daily",
    "ProgramArguments": [str(project / "scripts" / "run_scan.sh")],
    "WorkingDirectory": str(project),
    "StartCalendarInterval": [
        {"Weekday": weekday, "Hour": 6, "Minute": 0}
        for weekday in range(1, 6)
    ],
    "StandardOutPath": str(project / "artifacts" / "logs" / "launchd.log"),
    "StandardErrorPath": str(project / "artifacts" / "logs" / "launchd-error.log"),
    "ProcessType": "Background",
}
with destination.open("wb") as handle:
    plistlib.dump(payload, handle, sort_keys=False)
PY

chmod 600 "$PLIST_PATH"
launchctl bootout "gui/$(id -u)/com.market-scanner.daily" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
echo "Installed $PLIST_PATH"
echo "Store credentials in your user launchd environment or edit the plist EnvironmentVariables section."
