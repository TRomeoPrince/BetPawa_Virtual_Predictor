# HT/FT — half-time/full-time outcomes

`HT_FT` is one filesystem folder representing the named market **HT/FT**. Exact outcome `Home/Home` means the home team is leading at half-time *and* wins full-time; `HT Draw` is a **different, HT-only market**, not an HT/FT combination.

## Saved 11-season HT/FT shortlist

| League | Market | Rule | Wins/tests | Historical hit rate | Market baseline | Positive seasons | Notes |
|---|---|---|---:|---:|---:|---|---|
| German | HT/FT Home/Home | `P6.eq5.loser` | 126/362 | 34.81% | 28.90% | 8/11 | 34.81%; exactly five source FT goals, follow losing team; **below user's 60% floor** |

No HT/FT Home/Home, Away/Away, Draw/Home, Home/Draw or reversal strategy in the saved shortlist achieved a documented >=60% historical rate with sufficient validated tests. Do not advertise an unverified high-hit-rate HT/FT strategy.

## Related half-time-only observations — do not mislabel as HT/FT
| League | Market | Rule | Wins/tests | Historical hit rate | Market baseline | Positive seasons | Notes |
|---|---|---|---:|---:|---:|---|---|
| Spanish | HT Draw | `P6.ge6.winner` | 114/235 | 48.51% | 40.69% | 8/11 | 48.51%; source >=6 goals, follow winner; below floor |
| French | HT Draw | `P6.eq4.winner` | 159/370 | 42.97% | 37.31% | 8/11 | 42.97%; exactly four source goals, follow winner; below floor |

For future HT/FT studies store half-time and full-time home/away goals separately, list all nine mutually exclusive HT/FT outcomes, test each against its own base rate, and verify the specific offered market names and settlement rules in the event feed.
