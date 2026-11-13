# NEW_PATTERNS — BPV research notebook

**Private research only.** Created 13 November 2026. This directory captures the market-specific patterns from previous betPawa Virtual Football research and the existing private predictor rules; adding a pattern here does **not** activate or change any production prediction.

## Folder map
- [Wins](Wins/PATTERNS.md): Home/Away wins, home/away fixture-direction studies and exploratory ranked-position leads.
- [OVERS](OVERS/PATTERNS.md): Over 1.5/2.5/3.5, original seven frozen Over 2.5 rules and candidate head-to-head effects.
- [UNDERS](UNDERS/PATTERNS.md): Under 3.5 and historical Under 2.5/4.5 observations.
- [BTTS](BTTS/PATTERNS.md): BTTS Yes/No, source-goal and venue-specific observations.
- [HT_FT](HT_FT/PATTERNS.md): HT/FT outcomes and separate HT-only context. The folder is `HT_FT` because a filesystem cannot name a single directory `HT/FT` (slash denotes a nested path).

## Data provenance and strict interpretation
- **Discovery:** season `139214`. **Historical validation:** seasons `139216–139226` (11 seasons); seven leagues, 12 seasons and 26,928 fixtures in the saved multi-market shortlist dated 19 October 2026.
- **Additional archived pairing check:** 21 English league seasons: `139214`, `139216–139226`, `139421–139429`; see Wins, OVERS and BTTS. These are *exploratory historical observations*, not independently validated forecasts.
- **Current deployed rules:** repository file `backend/private_rules.py` supplies the original seven Over 2.5 rules, 37 newer multi-market rules, and eight Pattern 2 aliases/variants. An alias using identical mechanics is not independent supporting evidence.
- **Saved research sources:** `betpawa_multimarket_shortlist_2026-10-19.md`, `betPawa_Virtual_Football_Pattern_Backtest_2026-10-18.docx`, `betpawa_winrate_preliminary_2026-10-18.md`, `collect_betpawa_seasons.py`, and BPV discussions from 12–13 November 2026. These archived research files are retained outside this repository; reattach the raw results for independent reproduction.
- Matchdays are numbered 1–34 per season. The virtual schedule commonly advances in five-minute intervals; **use actual round start/end timestamps**, not a guessed interval, to locate the next occurrence. A 34-matchday schedule is *not* a 38-matchday full double round-robin: not every club pairing occurs twice in every season.
- Reported `wins/tests` means number of historical target fixtures satisfying the named market divided by all graded triggers, **not a probability guarantee, profitability claim or proof of an exploitable edge**.
- The user's screening floor is **60% historical hit rate** (55–60% exploratory only). Below-floor observations remain here for auditing and are **not recommended**. Even a 60%+ rule needs an unseen-season holdout, adequate sample size, market availability, and actual odds analysis before any financial decision. The saved backtest's extra quality filters were >=200 validation tests, >=3 pp lift over market baseline, >=8/11 positive validation seasons, and nonzero discovery support; not every recorded lead passes these filters.
- **Market availability matters:** `Under 4.5` looked strong in an archive but was previously removed because that betPawa market was unavailable. Verify availability each time, never silently substitute a different market.

## How we discovered the patterns
1. Download or read full **completed** historical seasons, including both full-time and half-time results. Preserve season ID, round ID, matchday, league ID, *fixture row position*, home/away, score, and result status.
2. Build distinct candidate families: source match goal-total ranks (preserve ties), largest winning margin, second-half goals, 0–0 at half-time/full-time, exact 4/5 or >=6 goals, winner/loser/home/away/both continuation, same-row behaviour, league-table rank, both opponents' prior states, HT→FT changes, and win/loss streaks. Also compare a team pairing in **both home/away directions**.
3. For next-matchday rules, evaluate source matchday `m` using finished data only, then find selected teams' fixture at `m+1`; do **not** cross a season boundary unless explicitly declaring and separately validating a cross-season strategy. Dedupe identical target fixtures pointed to by multiple teams in one test.
4. Grade the **target** only after its result settles: FT Home/Away Win, FT O/U thresholds, BTTS, HT-only or HT/FT as appropriate. Never use the target's future score as a trigger.
5. Freeze rule parameters on discovery season `139214`, backtest untouched seasons `139216–139226`, report wins/tests, rate, base market frequency, edge in percentage points, positive seasons, maximum loss streak and trigger count, then hold out additional unseen seasons.
6. Reject cherry-picked variants or overlapping duplicates. Report losses followed by exact subsequent win-run lengths for sequence hypotheses, not just a cumulative success percentage. Record negative findings too.
7. To schedule a future trigger, locate the latest *published* season/round list and round timestamps; search **current and subsequent published seasons**. The fixture may be missing in a given season. Convert timezone-aware UTC timestamps to **Africa/Kampala (EAT, UTC+3)**; do not treat site arrival times as exact settlement times.

## Fetching virtual fixture/results and market data
The project already contains a working read-only provider at `backend/providers/betpawa.py`. It is the first place to check before writing a new collector. As of that provider version:

| Purpose | Browser same-origin GET |
|---|---|
| Actual/published season catalog | `/api/sportsbook/virtual/v2/seasons/list/actual` |
| Past season catalog | `/api/sportsbook/virtual/v2/seasons/list/past` |
| Fixtures and available event/market payload for a round | `/api/sportsbook/virtual/v3/events/list/by-round/{round_id}?page=matchups` |
| Results UI | `/virtual-sports?virtualTab=results&resultsTab=matches` |
| One round UI | `/virtual-sports/matchday/{season_id}?matchday={matchday}&leagueId={league_id}` |

These are observed application routes, **not a stable public API contract**. An older collector used v1/v2 endpoints; prefer the newer route names documented in the current repository, and inspect the live browser network feed if the schema changes.

Open `https://www.betpawa.ug/virtual-sports` in your browser and run the following read-only browser-console example on **that same site**:

```js
(async () => {
  const headers = {
    Accept: "application/json, text/plain, */*",
    "X-Pawa-Brand": "betpawa-uganda",
    "X-Pawa-Language": "en",
    deviceType: "web",
  };
  async function get(path) {
    const response = await fetch(path, { credentials: "include", cache: "no-store", headers });
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${path}`);
    return response.json();
  }
  const catalog = await get("/api/sportsbook/virtual/v2/seasons/list/actual");
  const seasons = Array.isArray(catalog) ? catalog : (catalog.items || []);
  console.table(seasons.map(s => ({ season: s.id, rounds: s.rounds?.length ?? 0 })));
  // Choose the actual season + round you need; do not assume the first is next.
  const season = seasons.find(s => Array.isArray(s.rounds) && s.rounds.length);
  if (!season) return console.log("No published rounds in the current catalog");
  const round = season.rounds[0];
  const data = await get(`/api/sportsbook/virtual/v3/events/list/by-round/${encodeURIComponent(round.id)}?page=matchups`);
  console.log({ seasonId: season.id, roundId: round.id, round, payloadKeys: Object.keys(data), data });
  // Inspect data's event/market structures before mapping prices or score markets.
})();
```

**To fetch markets** (BTTS, Overs/Unders, Win, HT/FT), inspect the actual event data or betPawa Network tab: find the selected league's event, market type and selection identifiers. Do not assume every market is supplied by `page=matchups`, or that a market's odds/availability remains the same in later rounds. Full-time and first-half group slugs observed by the current provider are `FULL_TIME_EXCLUDING_OVERTIME` and `FIRST_HALF`. If a market is missing, record `unavailable`, not zero odds. Results can also be graded from finished FT/HT scores independently of offered odds. League IDs used by the provider: English `7794`, Spanish `7795`, Italian `7796`, German `9184`, French `9183`, Dutch `13774`, Portuguese `13773`.

Read only your authorized public/session data. Respect rate limits and terms, do not collect credentials/cookies or copy session tokens into the repository. The provider's browser-assisted retrieval is appropriate where direct HTTP requests fail.

## New entry checklist
Record `pattern_id`, market, league, exact trigger (including home vs away and fixture position), source/target matchday definition, season IDs, sample rows/results, discovery and holdout counts, successes/failures, rate, baseline, edge, positive seasons, longest win/loss streak, availability, timestamp zone, overlaps, and **status** (`research`, `validated-historical`, `insufficient`, `rejected`). Keep raw data and reproducible code separate from production activation. Do not overwrite existing research when a newer run disagrees; append a dated re-evaluation.

## Deployment and responsible use
This is **documentation only**, not authorization to enable a rule, update payment logic, or claim consistent betting profits. Revalidate using complete, untouched current seasons. Gambling is risky and historical correlations often collapse when many combinations are screened.
