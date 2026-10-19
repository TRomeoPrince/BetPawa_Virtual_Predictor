# BetPawa Predictor v0.2.1

The local folder name stays **BetPawa Predictor**.

## v0.2.1 feed reliability update

This update does not change the frozen prediction rules.

When **Get predictions** is pressed, the predictor now:

1. Selects the current virtual season from the actual-season feed using the current time instead of simply taking the last season/round returned.
2. Finds the latest settled matchday inside that season and the immediately following matchday.
3. Opens betPawa's real matchday page in Chrome and watches the network request made by betPawa itself.
4. Captures the successful event response and reuses that exact endpoint shape for the recent rounds needed by the verifier.
5. Falls back to opening the individual matchday page and capturing its response directly if an older round does not work with the discovered endpoint.
6. Accepts season payloads wrapped in `responses`, `items`, `data`, or `results`.
7. Does not append custom cache-busting query parameters to event endpoints.
8. Runs locally on port **8010** so it does not clash with PrinceAI on port 8000.

The hard-coded league rules, historical rates and current-season verification logic remain unchanged.

## Run

Double-click `run.bat` and open:

`http://127.0.0.1:8010`

## Normal update workflow

```bat
cd /d "C:\Users\USER\Desktop\Bots\Personal_AI\BetPawa Predictor"
git pull origin main
run.bat
```

## Notes

- Chrome is required.
- No betPawa login, password or API key is required.
- Raw public feed payloads are processed in memory and are not saved as season archives.
- Predictions are historical-rule reminders, not guarantees.