# Over 2.5 FT — each pairing direction verified separately

**Only this market:** `Over 2.5 FT` wins if `ft_home + ft_away >= 3`. A 3–0 qualifies even if BTTS YES fails. A 1–1 draw fails Over 2.5 despite both teams scoring. The match result (Home/Away Win/Draw) is **not** required by this rule; see the separate [Wins report](../Wins/PAIR_MARKETS_2026-11-13.md) and [BTTS report](../BTTS/PAIR_MARKETS_2026-11-13.md).

Primary score evidence: [archive 12 seasons](../TESTS/PAIR_RESULTS_ARCHIVE_2026-11-13.csv) (139214 discovery, 139216–139226 validation), plus [three more recently verified seasons](../TESTS/PAIR_RESULTS_RECENT_2026-11-13.csv) (139430–139432). Market labels below encode exact home/away orientation.

| Pattern ID (venue fixed) | Archive all 12 | Validation 11 only | Recent 3 | Chronological 12-season W/L outcome stream | W immediately after L |
|---|---:|---:|---:|---|---:|
| `H2H-AST-CRY-OVER25` | 7/8 (87.5%) | 7/8 (87.5%) | 3/3 (100.0%) | `WWWWLWWW` | 1/1 (100.0%) |
| `H2H-CRY-AST-OVER25` | 5/11 (45.5%) | 4/10 (40.0%) | 3/3 (100.0%) | `WLWLLLWLLWW` | 3/6 (50.0%) |
| `H2H-TOT-CRY-OVER25` | 7/11 (63.6%) | 7/10 (70.0%) | 2/3 (66.7%) | `LWLLWWLWWWW` | 3/4 (75.0%) |
| `H2H-CRY-TOT-OVER25` | 7/12 (58.3%) | 6/11 (54.5%) | 3/3 (100.0%) | `WWWLLLWLWWLW` | 3/5 (60.0%) |
| `H2H-CHE-TOT-OVER25` | 9/10 (90.0%) | 8/9 (88.9%) | 2/2 (100.0%) | `WWWWWWLWWW` | 1/1 (100.0%) |
| `H2H-TOT-CHE-OVER25` | 8/9 (88.9%) | 8/9 (88.9%) | 2/2 (100.0%) | `WWWWLWWWW` | 1/1 (100.0%) |
| `H2H-BRE-SUN-OVER25` | 6/11 (54.5%) | 6/11 (54.5%) | 1/2 (50.0%) | `WWLWWLLWWLL` | 2/4 (50.0%) |
| `H2H-SUN-BRE-OVER25` | 2/10 (20.0%) | 2/9 (22.2%) | 1/2 (50.0%) | `LLWLLLLLLW` | 2/8 (25.0%) |

## Market-specific definitions and interpretation

Each `H2H-HOME-AWAY-OVER25` row means: **IF** the upcoming published English virtual fixture is exactly HOME vs AWAY (codes in the ID, left-hand side at home), **THEN test Over 2.5 FT**, regardless of a win or BTTS result. The reverse fixture is a *different pattern*. Scores must be complete before grading. Nonexistent reverse fixtures are omitted, never guessed.

- **AST–CRY:** 7/8 archived Overs. Reversing to **CRY–AST** changes the observed Over rate to 5/11 (45.5%); these are not interchangeable. Example 139218 MD10 AST–CRY 3–0 = Over 2.5 but BTTS NO.
- **TOT–CRY:** 7/11 archived Overs; reverse **CRY–TOT** 7/12. Example 139219 MD7 TOT–CRY 4–1 = Over 2.5 and BTTS YES; that overlap is a *separate*, verified fact.
- **CHE–TOT:** 9/10 Over; reverse **TOT–CHE** 8/9. Example 139222 MD5 CHE–TOT 4–0 = Over 2.5 but BTTS NO; 139218 MD13 TOT–CHE 3–4 = Over, BTTS, and an AWAY win. Do not combine their hit rates without counting the actual triple outcomes.
- **BRE–SUN:** 6/11 Over; reverse **SUN–BRE** 2/10. Example 139219 MD25 BRE–SUN 3–2 wins Over 2.5, while 139218 MD30 SUN–BRE 2–2 also wins Over 2.5 but fails both outright Win outcomes.

## Loss → win streaks

The W/L streams are strictly **one observation per completed fixture in the specified venue direction**, in chronological season/matchday order. For each L, the last column counts whether the **next available meeting with that same home/away orientation** cleared Over 2.5; this is not the next virtual matchday. In short samples, a single long streak can create a misleading headline. A failure does not make the next Over more likely by any demonstrated mechanism.

## Older archived 21-season cross-check

Existing [OVERS/PATTERNS.md](PATTERNS.md) reported Over 2.5 at 72.2% in both directions for CHE/TOT, and 68.8% AST home versus 38.9% CRY home for AST/CRY. Those are *overlapping historical summaries* and cannot be added to the 12-season rows. Raw 21-season results were not completely available for independent reproduction.

**Status:** research/insufficient for deployment. The user's 60% screening floor is a useful initial filter, **not proof of predictive reliability**; many venue-specific samples contain fewer than 12 matches. See the [same-match intersection audit](../TESTS/PAIR_MARKET_INTERSECTIONS_2026-11-13.md). No live strategy logic was modified.
