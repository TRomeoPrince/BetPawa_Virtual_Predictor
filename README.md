# BetPawa Predictor v0.3.9

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


## v0.3.7 Pattern 2 transition / sequence family

Pattern 1 remains the existing strategy family. Pattern 2 adds the eight approved
transition/sequence rules from the latest research brief:

- Dutch O2.5: 6+ source goals -> follow both teams
- French O2.5: previous 3 team matches all O2.5
- French O2.5: 5+ source goals -> follow home team
- Spanish O2.5: highest-total previous-round fixture -> follow away team
- Italian O2.5: HT 0-0 and FT O2.5 -> follow home team
- Dutch BTTS YES: 6+ source goals -> follow winner
- French BTTS YES: biggest-margin source match -> follow winner
- Spanish BTTS YES: both target teams' previous matches were O2.5

No new Pattern 2 Over 1.5 or Under 3.5 rule is added. The optional Italian Home
Win P11.scored3conceded3 rule remains on hold because its exact original
classifier is not present and is not guessed.

Several of these exact mechanics were already present in the older broad research
list. They remain preserved there for provenance, but are evaluated as Pattern 2
only, avoiding duplicate support and artificial ranking inflation.

Prediction cards now display Pattern 1, Pattern 2, or Pattern 1 + Pattern 2 when
different family rules independently select the same fixture and market.

A normalized prediction_supports table stores family and exact rule ID internally,
along with league, fixture, market, historical rate, edge and later WON/LOST
outcome. Public API responses continue to hide exact private rule IDs.

Pattern-family live performance is shown separately by market. ROI is not
calculated because the current feed does not store betting odds.

Automated unittest coverage was added for no-lookahead, next-fixture lookup,
season-boundary reset behavior, previous-round ranking, ties, both-team follow,
winner/home/away roles, family labels and merged cards.


### Run the automated strategy tests

```bat
cd /d "C:\Users\USER\Desktop\Bots\Personal_AI\BetPawa Predictor"
test.bat
```

The same unittest suite is also configured in GitHub Actions for pushes to main.


## v0.3.8 estimated EAT time-window confirmation

A valid Pattern 1 / Pattern 2 strategy signal is still mandatory. The time layer
cannot create a prediction by itself.

Estimated target times are reconstructed from:

- anchor: season 139222 / matchday 33 / 2026-10-18 15:05 EAT
- 5 minutes per virtual matchday
- 34 matchdays per season (170 minutes)

The UI labels each valid pick with its estimated EAT kickoff, one-hour bucket and
one of: VERY STRONG, STRONG, MODERATE-STRONG, NORMAL or UNCONFIRMED.

Historical time evidence is keyed to the exact rule + league + market. It is never
borrowed from another rule. When multiple rules support one fixture, their time
records stay separate and the public overall TIME SUPPORT uses the strongest
record without averaging percentages.

Time is a ranking / confirmation signal only. NORMAL and UNCONFIRMED do not block
otherwise valid strategy predictions.

The database now stores time metadata on both the combined prediction and each
exact private support record. Completed supports accumulate live per-rule,
per-hour-window wins/losses for future research. These live counts do not
automatically rewrite the frozen historical time labels.

Automated tests cover anchor reconstruction, 5-minute progression, 34-matchday
rollover, midnight rollover, EAT metadata, hour buckets, exact-rule isolation,
no target-result leakage, family preservation and no percentage averaging.


## v0.3.9 recoverable English season tracker

The English highest-total -> winner -> next-match O2.5 tracker no longer becomes
ABANDONED for the entire season after two losses.

New lifecycle:

- ACTIVE + loss -> RISKY
- RISKY + win -> ACTIVE
- RISKY + loss -> WATCHING
- WATCHING + loss -> remain WATCHING
- WATCHING + win -> ACTIVE again

WATCHING continues evaluating every future actual trigger. Current WATCHING
candidates are shown as observation-only so a later recovery is visible instead
of being missed.
