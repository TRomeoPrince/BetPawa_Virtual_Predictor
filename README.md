# BetPawa Predictor v0.3.6

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

`http://127.0.0.1:8011`

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


## v0.3.2 qualified strategy implementation

The original seven frozen Over 2.5 strategies remain intact.

This release implements the 41 qualified multi-market rules from the latest
validation shortlist:

- 3 Over 1.5 FT strategies
- 4 Under 4.5 FT strategies
- 4 Under 3.5 FT strategies
- 16 Over 2.5 FT strategies
- 14 BTTS YES strategies

Rules use completed source/prior matches only. Target scores are never used for
qualification.

When several strategies support the same market on the same fixture, the API and
UI merge that market into one prediction and preserve every supporting rule's
individual historical rate, wins/tests, baseline edge and positive-season count.
No average or synthetic combined probability is calculated.

The candidate view now groups different markets under one fixture card and adds
filters for All, 80%+, 70%+, 60%+, Overs, Unders and BTTS.

Personal history stores the supporting strategy metadata for each market pick so
the later WON/LOST result remains auditable.


## v0.3.3 strategy-output protection

The browser no longer receives strategy IDs, strategy names, trigger descriptions,
source fixtures, selected-team logic, or other private rule metadata.

The backend still stores the full internal support metadata for grading and
auditing, but public API responses expose only:

- league and target fixture
- target market
- number of private supporting strategies
- top historical hit rate
- top rule's wins/tests
- top baseline edge
- positive-season summary

This prevents the frontend and browser developer tools from revealing the
underlying strategy logic. Full source protection still requires server-side
hosting; a locally distributed backend remains inspectable by whoever owns that
machine.


## v0.3.4 simplified market pages

The previous all-in-one candidate screen was replaced with separate pages:

- /overs
- /unders
- /btts
- /wins

The home page is now a simple market chooser.

Each market page has its own current candidates, last result and personal
performance view. Public API responses can also be scoped to one market family,
so the Overs page does not render BTTS or Under predictions and vice versa.

The existing private rules, v0.3.3 strategy-output protection, caching, personal
history and grading logic remain unchanged.


## v0.3.5 ranked picks, personal combos and league sections

Each market page now ranks its available picks by:

1. historical win rate
2. number of historical wins
3. number of private supporting strategies
4. historical test count

The ranking does not manufacture a combined probability.

Users can add exact predictions to **My Combo**. That choice is stored against the
browser user's saved prediction row, so it survives page refreshes and can be
graded later.

The page separates:

- Top Ranked Picks
- My Combo
- Predictions by League (ENGLISH, DUTCH, SPANISH, etc.)
- My Combo Results
- Other Prediction Results

Personal stats on a market page now emphasize the user's selected matches rather
than mixing every generated candidate into the same result summary.


## v0.3.6 English live tracker + reliable restart

The Overs page now includes a live current-season tracker for the English pattern
the user requested to watch.

Internal tracker logic:
- identify the highest full-time goal-total level in the completed English round
- follow the winner(s) into their next fixture
- grade whether the next fixture finishes Over 2.5 FT

Lifecycle:
- ACTIVE + loss -> RISKY
- RISKY + win -> ACTIVE
- RISKY + loss -> ABANDONED for the rest of that season

No future target score is used to qualify a pick.

The tracker is intentionally separate from ranked validated strategies because it
does not yet have an approved historical validation rate for the main ranking.

The market page exposes only tracker state, season record and target fixture(s);
the private trigger implementation remains backend-side.

### Combo Not Found fix

A browser could load the new v0.3.5 HTML while an older Uvicorn process was still
serving the backend, causing `/api/selection` to return 404 Not Found.

`run.bat` now stops the existing listener on dedicated port 8010 before starting
the current predictor, and the frontend warns when its version does not match the
running backend.
