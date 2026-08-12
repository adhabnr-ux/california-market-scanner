# Scheduling and operations

## GitHub Actions: 6:00 AM California time

`.github/workflows/market-scan.yml` runs at **06:00 Monday-Friday** in
`America/Los_Angeles`. GitHub Actions supports an IANA `timezone` alongside the
cron expression, making the schedule daylight-saving-time safe:

```yaml
schedule:
  - cron: "0 6 * * 1-5"
    timezone: "America/Los_Angeles"
```

Scheduled Actions are best-effort. GitHub notes that high load—especially at the
start of an hour—can delay a run and, in extreme cases, drop it. This workflow
keeps the requested exact 06:00 schedule; use the local `launchd` option below
if runner dispatch timing must be controlled by your Mac.

Scheduled workflows run from the latest commit on the default branch. GitHub
may disable schedules after 60 days without repository activity in a public
repository. A manual **Run workflow** trigger is included for recovery/testing.

Official references:

- [GitHub workflow schedule syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule)
- [Schedule event limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## Repository secrets

In **Settings → Secrets and variables → Actions**, add:

| Secret | Required | Purpose |
| --- | --- | --- |
| `APCA_API_KEY_ID` | Yes | Alpaca market-data API key ID |
| `APCA_API_SECRET_KEY` | Yes | Alpaca market-data API secret |
| `FINNHUB_API_KEY` | No | Enriches catalyst/news data when supported |

The workflow does not grant write access to repository contents. It validates
the two required Alpaca values without printing them, runs the complete test
suite, performs the scan, and retains `artifacts/` as an Actions run artifact for
30 days. Artifact access follows the repository's GitHub permissions. Do not
commit `.env` files or API keys.

## Manual run

Open **Actions → Market scan → Run workflow**. Choose `demo` to validate the
complete cloud workflow without credentials, or `alpaca` for live data. With
GitHub CLI:

```bash
gh workflow run market-scan.yml -f provider=demo
```

Download output from the completed run's **Artifacts** section.

## Local macOS schedule with launchd

`launchd` uses the Mac's local timezone. On a Mac configured for California
time, this follows PST/PDT automatically. Install after creating the virtual
environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
./scripts/install_launchd.sh
```

The generated job runs weekdays at 06:00 and writes logs under
`artifacts/logs/`. The Mac must be awake; macOS may run a missed calendar event
after wake rather than at exactly 06:00.

Credential files are intentionally not generated. Prefer a secrets manager that
injects values before `scripts/run_scan.sh`, or manually add an
`EnvironmentVariables` dictionary to
`~/Library/LaunchAgents/com.market-scanner.daily.plist` and keep its permissions
at `0600`. Required variable names match the GitHub secrets above.

Check and remove the job:

```bash
launchctl print "gui/$(id -u)/com.market-scanner.daily"
launchctl bootout "gui/$(id -u)/com.market-scanner.daily"
rm ~/Library/LaunchAgents/com.market-scanner.daily.plist
```

## Docker

```bash
docker build -t market-scanner .
docker run --rm \
  -e APCA_API_KEY_ID \
  -e APCA_API_SECRET_KEY \
  -e FINNHUB_API_KEY \
  -v "$PWD/artifacts:/app/artifacts" \
  market-scanner
```

The image runs as an unprivileged user. Docker does not provide scheduling by
itself; schedule `docker run` with the host scheduler or use GitHub Actions.
