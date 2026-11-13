# Wins — FT home/away outcomes

Sources: archived multi-market shortlist (discovery `139214`, validation `139216–139226`) and BPV's 21-season English head-to-head review on 13 November 2026.

## Historical 11-season multi-market shortlist (baseline-relative; **below user's 60% floor**)
| League | Market | Rule | Wins/tests | Historical hit rate | Market baseline | Positive seasons | Notes |
|---|---|---|---:|---:|---:|---|---|
| Italian | Home Win | `P11.scored3conceded3` | 125/243 | 51.44% | 41.93% | 10/11 | Both opponents' prior matches interacted: scored >=3 vs conceded >=3 |
| German | Home Win | `P6.eq5.loser` | 188/362 | 51.93% | 47.02% | 8/11 | Exactly five source FT goals; follow source loser to its next match |
| English | Away Win | `P2.margin.winner` | 196/536 | 36.57% | 29.70% | 10/11 | Largest source winning margin; follow winner |
| Italian | Away Win | `P6.eq4.away` | 209/569 | 36.73% | 32.45% | 10/11 | Exactly four source FT goals; follow source away team |

These had positive **relative** edges but hit rates of 36–52%, so they should not be marketed as high-reliability win predictions. A saved production comment leaves Italian `P11.scored3conceded3` on hold because its original classifier cannot be reproduced exactly.

## English fixture-direction observations, 21 archived seasons — exploratory only

| Pairing and selected result | At selected team HOME | At selected team AWAY | Combined observation |
|---|---|---|---|
| AST vs CRY: Aston Villa win | 12/16 = 75.0% | 11/18 = 61.1% | 23/34 = 67.6% |
| TOT vs CRY: Tottenham win | 14/19 = 73.7% | 8/19 = 42.1% | 22/38 = 57.9% |
| CHE vs TOT: Chelsea win | 6/18 = 33.3% | 8/18 = 44.4% | 14/36 = 38.9% |

**Read carefully:** `TOT–CRY` is Tottenham *home*; `CRY–TOT` is the reverse. Same for `AST–CRY`/`CRY–AST`, `CHE–TOT`/`TOT–CHE`. Scores in the raw comparison are always **home first**. Not all seasons contain both variants: do not fill gaps with guessed matches.

Example season `139218`: `AST–CRY` MD10 **3–0**, `CRY–AST` MD29 **2–2**; `TOT–CRY` MD27 **2–0**, `CRY–TOT` MD8 **0–1**; `CHE–TOT` MD32 **3–0**, `TOT–CHE` MD13 **3–4**. A match's `home` column is not interchangeable with `away`.

**Sequence research request to complete:** After each TOT–CRY *home fixture* loss, enumerate the number of consecutive TOT–CRY home wins until the next loss, then repeat; perform separately for CRY–TOT and for a chronological combined stream. A single venue's 19 observations cannot establish reliable periodicity. No stable loss→streak length has yet been proven by this document.

## Other leads not promoted
- Spanish position-2 Home Win was previously reported as **251/408 = 61.52%** vs league baseline 47.87%, but requires reproduction from the underlying seasons and exact fixture-row rule before adoption.
- BRE ranked above SUN: previous exploratory 12-season review found BRE win 6/13 (46.2%) but avoided defeat 11/13 (84.6%). **Win and double-chance are different markets**; this is not a 84.6% BRE-win rule.

## New independent fixture-pair audit (13 Nov 2026)

See [the market-specific pair verification](PAIR_MARKETS_2026-11-13.md) for AST–CRY, TOT–CRY, CHE–TOT and BRE–SUN in **both home/away directions**, with raw scores and separately computed validation/recent rates. [Same-match overlap audit](../TESTS/PAIR_MARKET_INTERSECTIONS_2026-11-13.md) lists the occasions when BTTS YES, Over 2.5 and a home/away win simultaneously occurred. This cross-reference does **not** merge the separate market patterns, and none was enabled in the live predictor.
