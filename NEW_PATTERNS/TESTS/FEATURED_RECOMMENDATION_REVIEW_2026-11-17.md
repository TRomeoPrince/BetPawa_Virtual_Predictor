# 17 November 2026 — Conservative featured recommendations (NOT an activated betting strategy)

## Why
The previous **Top Recommended Picks** and right-side research list showed the first available model picks, which included BRE–SUN despite weak recent validation. The user asked to remove that fixture from featured recommendations and prioritize stronger archived head-to-head evidence (TOT/CHE, CRY/TOT and related teams). The market pages and historical archive should **not** be erased.

## Evidence sources
- Venue-specific raw archive: `NEW_PATTERNS/TESTS/PAIR_RESULTS_ARCHIVE_2026-11-13.csv`, 11 validation seasons 139216–139226 (plus a discovery season 139214, NOT counted below)
- Independent recent check: `NEW_PATTERNS/TESTS/PAIR_RESULTS_RECENT_2026-11-13.csv`, seasons 139430–139432
- Market-separated research: `NEW_PATTERNS/OVERS/PAIR_MARKETS_2026-11-13.md`, `BTTS/PAIR_MARKETS_2026-11-13.md`, `Wins/PAIR_MARKETS_2026-11-13.md`

## Featured only when the exact fixture/market is in the actual next-round model output

| Home – Away | Independent selection | Validation (11 seasons) | Recent checked | Displayed |
|---|---|---:|---:|---|
| TOT–CHE | BTTS YES | 9/9 | 2/2 | Featured research |
| TOT–CHE | Over 2.5 FT | 8/9 | 2/2 | Featured research |
| CHE–TOT | Over 2.5 FT | 8/9 | 2/2 | Featured research |
| AST–CRY | Home Win (AST) | 7/8 | 3/3 | Featured research |
| AST–CRY | Over 2.5 FT | 7/8 | 3/3 | Featured research |
| TOT–CRY | Home Win (TOT) | 7/10 | 2/3 | Featured research |
| TOT–CRY | Over 2.5 FT | 7/10 | 2/3 | Featured research |
| TOT–CRY | BTTS YES | 7/10 | 2/3 | Featured research |
| CRY–TOT | BTTS YES | 7/11 | 3/3 | **Watch only** — below 70% featured floor |
| BRE–SUN | Home Win | 7/11 | 0/2 | **Removed from featured** (both venue directions excluded) |

Other weak or differently oriented selections do not become featured simply because a reverse-direction match did well. Chelsea home BTTS (7/9 with 1/2 recent) is not featured; Tottenham home wins over Chelsea (4/9) are not featured. No probabilities, odds, edge estimates, guaranteed payouts or future scores are invented.

## Rules for the UI

- The full authorized `/api/recommended-picks` response retains `predictions` so existing client screens and permissions are intact. New `featured_predictions` includes only exact home/away, exact market, >=8 validation games, >=70% validation successes and >=2/3 recent successes over >=2 independent recent matches. `research_watchlist` is separate.
- Featured picks only appear if **the current, published next-round model output actually includes the fixture and market**; missing future fixtures are never inserted.
- Front-end displays the original historical **wins/tests counts**, not a forecast probability. If none qualifies, show a truthful empty state rather than promote weaker picks.
- BTC/Over/Win outcomes remain separate markets even when the same past score satisfied two or more outcomes.
- This screen does not change the underlying prediction engine, win proof grading, subscription access, or market categories.

## Important limitation
Even a 9/9 historical record comes from only nine matches in a venue-specific validation sample and just two recent observations; it is **not a sure win or a demonstrated betting edge**. There may be selection bias from researching many candidate pairs. A larger untouched, subsequent-season holdout and actual market odds are required to assess reliability and economic value. Previous summaries overlap the archive and were not added to sample sizes.
