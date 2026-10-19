# BetPawa Predictor v0.2.0

The folder name is intentionally kept **BetPawa Predictor** for every update.

## What changed

This version no longer tries to build or download a historical archive each time.

When **Get predictions** is pressed it:

1. Reads the current public virtual-football season/round information.
2. Reads only the completed matchdays needed for the current season check.
3. At the very start of a season, supplements the small current sample with recent rounds from up to two prior completed seasons.
4. Replays the frozen private rule for each league on those already-finished source→target pairs.
5. Calculates recent alignment and a confidence value that is shrunk toward the multi-season historical validation rate, so a tiny recent sample cannot produce a fake 100% confidence.
6. If a rule has at least 5 recent trigger outcomes and falls below 60% or below its league's normal O2.5 baseline, that league is marked **PAUSED**.
7. Applies the same private rule to the latest completed matchday and maps any trigger to the next matchday fixture.
8. Shows only league, fixture/team context, Over 2.5 FT, confidence, recent wins/tests and alignment status. Rule definitions remain backend-only.

## Run

Double-click `run.bat` and open `http://127.0.0.1:8000`.

There is no background scheduler in v0.2.0. Every click on **Get predictions** performs a fresh on-demand check.

## Notes

- No betPawa account, password or API key is required.
- Raw public feed payloads are processed in memory and are not saved as season archives.
- Predictions are historical-rule reminders, not guarantees.
