# Pair-specific FULL-TIME WINS — verified research, 13 Nov 2026

This is the **Wins** category, distinct from [Over 2.5](../OVERS/PAIR_MARKETS_2026-11-13.md) and [BTTS](../BTTS/PAIR_MARKETS_2026-11-13.md). A row `H2H-{HOME}-{AWAY}-HOMEWIN` is one named outcome; `H2H-{HOME}-{AWAY}-AWAYWIN` is **another**. The exact home/away direction is part of the trigger. A draw loses both outright-win markets. Score notation is HOME–AWAY.

## Market-specific, two-direction tests

Raw scores: [12-season archive](../TESTS/PAIR_RESULTS_ARCHIVE_2026-11-13.csv) (139214 discovery; 139216–139226 11-season validation) and [independent recent three-season sample](../TESTS/PAIR_RESULTS_RECENT_2026-11-13.csv) (139430–139432). The 21-season older figures already in [PATTERNS.md](PATTERNS.md) overlap these 12 seasons, so **do not add the sample sizes**.

| Exact fixture orientation | HOMEWIN pattern ID and all-12 / validation / recent results | AWAYWIN pattern ID and all-12 / validation / recent results |
|---|---|---|
| AST–CRY | `H2H-AST-CRY-HOMEWIN`: 7/8 (87.5%) / 7/8 (87.5%) / 3/3 (100.0%) | `H2H-AST-CRY-AWAYWIN`: 1/8 (12.5%) / 1/8 (12.5%) / 0/3 (0.0%) |
| CRY–AST | `H2H-CRY-AST-HOMEWIN`: 3/11 (27.3%) / 3/10 (30.0%) / 3/3 (100.0%) | `H2H-CRY-AST-AWAYWIN`: 6/11 (54.5%) / 5/10 (50.0%) / 0/3 (0.0%) |
| TOT–CRY | `H2H-TOT-CRY-HOMEWIN`: 8/11 (72.7%) / 7/10 (70.0%) / 2/3 (66.7%) | `H2H-TOT-CRY-AWAYWIN`: 3/11 (27.3%) / 3/10 (30.0%) / 0/3 (0.0%) |
| CRY–TOT | `H2H-CRY-TOT-HOMEWIN`: 4/12 (33.3%) / 4/11 (36.4%) / 1/3 (33.3%) | `H2H-CRY-TOT-AWAYWIN`: 6/12 (50.0%) / 5/11 (45.5%) / 0/3 (0.0%) |
| CHE–TOT | `H2H-CHE-TOT-HOMEWIN`: 5/10 (50.0%) / 4/9 (44.4%) / 2/2 (100.0%) | `H2H-CHE-TOT-AWAYWIN`: 2/10 (20.0%) / 2/9 (22.2%) / 0/2 (0.0%) |
| TOT–CHE | `H2H-TOT-CHE-HOMEWIN`: 4/9 (44.4%) / 4/9 (44.4%) / 1/2 (50.0%) | `H2H-TOT-CHE-AWAYWIN`: 3/9 (33.3%) / 3/9 (33.3%) / 0/2 (0.0%) |
| BRE–SUN | `H2H-BRE-SUN-HOMEWIN`: 7/11 (63.6%) / 7/11 (63.6%) / 0/2 (0.0%) | `H2H-BRE-SUN-AWAYWIN`: 2/11 (18.2%) / 2/11 (18.2%) / 2/2 (100.0%) |
| SUN–BRE | `H2H-SUN-BRE-HOMEWIN`: 1/10 (10.0%) / 1/9 (11.1%) / 1/2 (50.0%) | `H2H-SUN-BRE-AWAYWIN`: 2/10 (20.0%) / 2/9 (22.2%) / 0/2 (0.0%) |

Every column is **a different outcome test**, not one combined recommendation. Denominators count only actual matches of that exact orientation (some seasons contain no reverse pairing). `Recent` means 139430–139432, not a continuously refreshed live rate. The older 21-season archived observations were: AST win 12/16 at AST–CRY and 11/18 at CRY–AST; Tottenham win 14/19 at TOT–CRY and 8/19 at CRY–TOT; Chelsea win 6/18 at CHE–TOT and 8/18 at TOT–CHE. They remain archival summaries, not newly reverified rows.

## Direction-specific sample proofs

- **AST–CRY (AST HOMEWIN):** Season 139218 MD10, AST–CRY 3–0. The reverse **CRY–AST** MD29 was 2–2, so Aston Villa's *away-win* market failed. Neither is interchangeable.
- **TOT–CRY (TOT HOMEWIN):** Season 139218 MD27, TOT–CRY 2–0. Reverse **CRY–TOT** MD8, 0–1, was an **AWAYWIN**, not a home win.
- **CHE–TOT:** Season 139218 MD32 CHE–TOT 3–0 = HOMEWIN; reverse MD13 TOT–CHE 3–4 = AWAYWIN. Both indicate Chelsea winning, but they are separately indexed fixture conditions.
- **BRE–SUN:** Season 139219 MD25 BRE–SUN 3–2 = HOMEWIN. **SUN–BRE** season 139218 MD30 ended 2–2 = **DRAW**, so both outright-win labels fail. Prior BRE-above-SUN standings evidence (6/13 outright wins; 11/13 avoided defeat) is a **conditional rank-based test**, not the same denominator as this fixture test.

## Sequence checking and decision status

For a Win-market sequence, code `W` if the specifically named HOMEWIN or AWAYWIN occurs; `L` otherwise (including draws). Read matches chronologically within the SAME orientation. After an L, count subsequent W outcomes until the next L, **but only at later qualifying meetings**, not at every five-minute matchday. For example, in the 12-season TOT–CRY HOMEWIN observations: `W L L W W W W W L W W`; the five-win run occurred between separate failures, yet a second failure also followed immediately in another section. This is *not* a guaranteed repeating cycle. Full fixture rows and season IDs are available in the linked score CSVs.

**Status:** exploratory/insufficient for deployment. Even the apparent >60% rates generally have only 8–12 matches per venue in this reproducible 12-season dataset; the larger older archive is not an independent dataset. No betting odds, expected value or unseen-month verification were established. Cross-market co-occurrence is audited [separately](../TESTS/PAIR_MARKET_INTERSECTIONS_2026-11-13.md).
