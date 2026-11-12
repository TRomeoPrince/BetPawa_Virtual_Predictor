# betPawa backtest results collection

Updated 12 November 2026 (Africa/Kampala).

## Verified new official results

`betpawa_new_verified_seasons_139421-139429.csv` contains 20,196 fixtures from provider seasons 139421 through 139429, across seven leagues (63 league-season groups). All 34 advertised matchdays per season are present. England, Spain and Italy each contain 3,060 fixtures; Germany, France, Netherlands and Portugal each contain 2,754.

Fixture times span 10 November 2026 21:15 UTC through 11 November 2026 22:40 UTC (12 November 01:40 in Kampala). Fresh public past/actual lists were checked again at 12 November 00:01 UTC: the same nine completed seasons were advertised. Season 139430 was still in progress and was excluded. This is a snapshot, not a live feed.

Every result has halftime/fulltime scores, source IDs, source URL, collection time, response hash and completion provenance. All-team W/D/L, points and goal totals reconcile exactly with official final standings. The endpoint exposes no explicit betting-market settlement flag: historical membership, elapsed season, non-live state, period-score consistency and standings corroborate completed results, not individual market payouts.

The original `betpawa_raw_fixtures.csv` is preserved byte-for-byte. It contains 26,928 rows from 12 different seasons. Exact season/league identity and season/league/matchday/home/away comparison found zero overlaps with the 20,196 newly collected fixtures. Original SHA-256: daa27e12eeaed0de8c461cad3cddeba47243572c4ee215893e3016253a47ffe1.

## Furthest accessible older data — separate, unverified

`betpawa_older_community_seasons_UNVERIFIED.csv` contains 6,460 English League fixtures from 19 structurally complete 34-matchday seasons, obtained from the public mugabi2/BP repository. Its reported capture timestamps span 22 July–15 August 2026. Capture timestamps are not independently verified fixture dates. There is no continuous October-to-November coverage.

These rows pass structural checks (340 unique fixtures per season, 20 teams once per matchday, matchdays 1–34, nonnegative scores and halftime not exceeding full time). Conflicting repeated scores and incomplete seasons were excluded. They do not overlap the original archive's season IDs. They are NOT verified against official historical results and are excluded from the official new-results CSV. A request for known community season 138971 returned HTTP 404 SPORTSBOOK_STANDING_NOT_FOUND. Do not use this separate file as verified settlement evidence.

Source: https://github.com/mugabi2/BP/blob/main/data/match_day_results/match_results_master.csv

## Access limits and October gap

Current public betPawa endpoints use v2 season/standings routes and v3 events, with the site's public X-Pawa-Brand header. No cookies, login or credentials were used. The legacy v1 routes in SimTechPro documentation returned 404. The current past list exposes nine seasons with no pagination in the inspected client. No authorized public route to a complete October archive was established; older season or round IDs were not guessed. Realnaps' results API returned 401 missing_api_key, so no authenticated retrieval was attempted.

Sources: https://www.betpawa.ug/virtual-sports ; https://github.com/SimTechPro/BetPawa ; https://virtual-games.realnaps.com/docs

## Evidence and repeatability

`season_coverage.csv` lists every official league-season check. `archive_comparison.json` records original-file identity and counts. `collection_evidence.zip` contains raw official responses and URL/time/hash metadata, fresh index checks, original community source CSV, and the collection/validation scripts. Extract to a fresh directory and run `python outputs/collect_public_results.py`, then `python outputs/validate_results.py` (Python 3 plus requests). The validator's archive option requires canonical identity-column mapping as documented in the earlier workflow; the present archive comparison used the actual original columns and exact league-name mapping, with no fuzzy matching.

The collection was kept separate from the historical archive. No predictor code was changed. No model backtest was run.
