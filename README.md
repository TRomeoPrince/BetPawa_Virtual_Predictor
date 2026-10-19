# BetPawa Predictor v0.3.1

The local folder remains **BetPawa Predictor**.

## v0.3.0

This update keeps the frozen prediction rules unchanged and adds two major product improvements.

### Personal results

Each browser receives a random anonymous cookie ID. No signup is required.

- Predictions are stored against that browser ID.
- One user cannot see another user's saved prediction history.
- Previous predictions are automatically graded when their target matchday becomes completed.
- The website shows the last prediction, final scores, WON/LOST/PENDING status, overall live wins/losses, and recent matchday performance.
- A **Refresh results** button checks whether pending predictions have finished.

### Faster prediction requests

- Completed round payloads are cached in SQLite and reused across restarts.
- Settled matchdays are never downloaded again unless the cache is missing.
- Upcoming target rounds use a short cache so fixture updates can still be detected.
- The Selenium Chrome session remains alive while the server is running instead of restarting for every request.
- The completed prediction context is reused for everyone while the same source matchday remains current.
- Multiple users therefore share the expensive public-data work without sharing personal prediction history.

## Run

```bat
cd /d "C:\Users\USER\Desktop\Bots\Personal_AI\BetPawa Predictor"
git pull origin main
run.bat
```

Open:

`http://127.0.0.1:8010`

## Notes

- Chrome is required.
- No betPawa login, password or API key is required.
- betPawa round data is requested as isolated JSON from inside the real browser session.
- The private historical rules remain backend-only.
- Predictions are historical-rule reminders, not guarantees.


## v0.3.1 multi-market foundation

No new prediction strategy is added in this release.

The personal-results engine is now ready to grade and display approved strategies
for:

- FT Over / Under goal thresholds
- BTTS Yes / No
- Home Win / Away Win / FT Draw
- HT Draw
- HT/FT combinations such as Draw/Home, Home/Home and Away/Draw

The frontend no longer hard-codes "Over 2.5 FT" in result cards. It displays the
market supplied by the approved strategy, and personal performance is broken down
by market. Unknown future market labels remain PENDING rather than being graded
incorrectly.

The original seven frozen Over 2.5 strategies are unchanged.
