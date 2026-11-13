# BTTS YES / BTTS NO — direction-specific fixture verification

The score test is unambiguous: **BTTS YES** if both clubs score at least one FT goal; **BTTS NO** if at least one club finishes with zero. BTTS does **not** require Over 2.5, Home Win, or Away Win. All these are separate markets, recorded under [OVERS](../OVERS/PAIR_MARKETS_2026-11-13.md) and [Wins](../Wins/PAIR_MARKETS_2026-11-13.md) respectively. A row with score 1–1 wins BTTS YES but loses Over 2.5 and both outright Win outcomes.

Evidence: [12-season raw scores](../TESTS/PAIR_RESULTS_ARCHIVE_2026-11-13.csv) (139214 discovery; 139216–139226 validation), and [three recent verified seasons](../TESTS/PAIR_RESULTS_RECENT_2026-11-13.csv) (139430–139432). Each fixture orientation is treated as its own trigger.

| Fixture direction / YES ID | YES, all 12 | YES, 11 validation | YES, recent 3 | NO, all 12 | YES W/L stream, all 12 | Next YES after previous NO |
|---|---:|---:|---:|---:|---|---:|
| `H2H-AST-CRY-BTTSYES` | 5/8 (62.5%) | 5/8 (62.5%) | 3/3 (100.0%) | 3/8 (37.5%) | `WLLWLWWW` | 2/3 (66.7%) |
| `H2H-CRY-AST-BTTSYES` | 4/11 (36.4%) | 3/10 (30.0%) | 2/3 (66.7%) | 7/11 (63.6%) | `WLWLLLWLLLW` | 3/7 (42.9%) |
| `H2H-TOT-CRY-BTTSYES` | 7/11 (63.6%) | 7/10 (70.0%) | 2/3 (66.7%) | 4/11 (36.4%) | `LWLLWWLWWWW` | 3/4 (75.0%) |
| `H2H-CRY-TOT-BTTSYES` | 8/12 (66.7%) | 7/11 (63.6%) | 3/3 (100.0%) | 4/12 (33.3%) | `WWWLWLWLWWLW` | 4/4 (100.0%) |
| `H2H-CHE-TOT-BTTSYES` | 8/10 (80.0%) | 7/9 (77.8%) | 1/2 (50.0%) | 2/10 (20.0%) | `WWLWWLWWWW` | 2/2 (100.0%) |
| `H2H-TOT-CHE-BTTSYES` | 9/9 (100.0%) | 9/9 (100.0%) | 2/2 (100.0%) | 0/9 (0.0%) | `WWWWWWWWW` | 0/0 (none observed) |
| `H2H-BRE-SUN-BTTSYES` | 7/11 (63.6%) | 7/11 (63.6%) | 1/2 (50.0%) | 4/11 (36.4%) | `WWLWWLLWWLW` | 3/4 (75.0%) |
| `H2H-SUN-BRE-BTTSYES` | 6/10 (60.0%) | 5/9 (55.6%) | 1/2 (50.0%) | 4/10 (40.0%) | `WLWWWLLWLW` | 3/4 (75.0%) |

## Separate BTTS YES and BTTS NO pattern IDs

All 8 orientations above have *two independently labeled outcomes*:

| Home vs Away | BTTS YES selection ID | BTTS NO selection ID | Trigger |
|---|---|---|---|
| AST–CRY | `H2H-AST-CRY-BTTSYES` | `H2H-AST-CRY-BTTSNO` | Fixture exactly `AST - CRY` in English virtual league |
| CRY–AST | `H2H-CRY-AST-BTTSYES` | `H2H-CRY-AST-BTTSNO` | Fixture exactly `CRY - AST` in English virtual league |
| TOT–CRY | `H2H-TOT-CRY-BTTSYES` | `H2H-TOT-CRY-BTTSNO` | Fixture exactly `TOT - CRY` in English virtual league |
| CRY–TOT | `H2H-CRY-TOT-BTTSYES` | `H2H-CRY-TOT-BTTSNO` | Fixture exactly `CRY - TOT` in English virtual league |
| CHE–TOT | `H2H-CHE-TOT-BTTSYES` | `H2H-CHE-TOT-BTTSNO` | Fixture exactly `CHE - TOT` in English virtual league |
| TOT–CHE | `H2H-TOT-CHE-BTTSYES` | `H2H-TOT-CHE-BTTSNO` | Fixture exactly `TOT - CHE` in English virtual league |
| BRE–SUN | `H2H-BRE-SUN-BTTSYES` | `H2H-BRE-SUN-BTTSNO` | Fixture exactly `BRE - SUN` in English virtual league |
| SUN–BRE | `H2H-SUN-BRE-BTTSYES` | `H2H-SUN-BRE-BTTSNO` | Fixture exactly `SUN - BRE` in English virtual league |

**YES** and **NO** are mutually exclusive score outcomes. The NO historical success count is exactly total matches minus YES successes; it is not a second predictive discovery or a reason to place an opposing market simultaneously. For NO's validation figure, subtract the YES successes from the listed validation denominator. There are no undisclosed missing-match fills.

## Specific observations

- **CHE–TOT at Tottenham's venue:** TOT–CHE had **9/9 BTTS YES** in the 12-season raw archive, also 9/9 in validation, but just **2/2** in recent verification. This is not a reliable 100% forecast: only nine validation matches and candidate selection among many pairs. The earlier 21-season archived summary states **14/18 (77.8%)** in each venue direction, overlapping this set and therefore not additive.
- **CHE–TOT at Chelsea's venue:** 8/10 BTTS YES, not equal to the reverse's 9/9 in the raw 12-season subset. In season 139218 MD32 CHE–TOT **3–0**, BTTS YES fails despite Over 2.5 and Chelsea winning.
- **CRY–TOT:** 8/12 BTTS YES with CRY home. In this sample a BTTS NO result was followed by BTTS YES at the next observed CRY–TOT meeting **4/4 times**, but four transitions are inadequate for a reliability claim.
- **AST–CRY:** 5/8 BTTS YES with AST home, versus just 4/11 when CRY hosts AST; reverse venues must not be combined silently.
- **BRE–SUN:** 7/11 BTTS YES with BRE home, and 6/10 with SUN home. The two venue directions have sharply different Over 2.5 rates even though BTTS YES is not rare in either: don't infer O2.5 from BTTS alone.

## Sequence semantics

The strings above use **W = BTTS YES** and **L = BTTS NO** at each chronological *qualifying pairing* in that exact venue orientation. They are **not** consecutive five-minute matchdays, and a loss does not force a subsequent winning result. For the BTTS NO market the meaning of W/L is reversed and must be labeled as such when used.

**Status:** research/insufficient. Several observed percentages exceed 60%, but samples are small. Historical odds, expected return and unseen-season persistence are unverified. The [same-match intersection report](../TESTS/PAIR_MARKET_INTERSECTIONS_2026-11-13.md) counts exact coincidences of BTTS YES + O2.5 + Home/Away Win without merging the individual rules. No live prediction rules were activated.
