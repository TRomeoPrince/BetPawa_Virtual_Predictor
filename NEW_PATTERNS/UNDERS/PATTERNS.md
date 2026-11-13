# UNDERS — full-time goal totals

Validation: 11 seasons `139216–139226`, selected from 12-season research. An Under 3.5 outcome means total FT goals <=3. A rule is a historical correlation, not a profitable signal.

## Four existing Under 3.5 strategy definitions (`backend/private_rules.py`)
| League | Market | Rule | Wins/tests | Historical hit rate | Market baseline | Positive seasons | Notes |
|---|---|---|---:|---:|---:|---|---|
| Italian | Under 3.5 | `P1.rank1.winner` | 307/444 | 69.14% | 65.62% | 8/11 | Highest distinct FT-total source match; follow winner |
| Spanish | Under 3.5 | `P6.eq5.loser` | 249/363 | 68.60% | 65.29% | 8/11 | Exactly five source FT goals; follow loser |
| English | Under 3.5 | `P12.avgge3.5` | 556/820 | 67.80% | 63.83% | 8/11 | Source matchday average >=3.5; all next-round fixtures |
| Dutch | Under 3.5 | `P7.htdrawdecisive.loser` | 458/753 | 60.82% | 57.79% | 8/11 | Source HT draw to decisive FT; follow loser; **below 60% floor** |

## Archival tests / not deployed
| League | Market | Rule | Wins/tests | Historical hit rate | Market baseline | Positive seasons | Notes |
|---|---|---|---:|---:|---:|---|---|
| Spanish | Under 4.5 | `P6.eq4.away` | 480/564 | 85.11% | 81.71% | 9/11 | 85.11% historical but market was reported unavailable on betPawa: **do not offer** |
| Spanish | Under 2.5 | `P11.bothunder` | 305/647 | 47.14% | 42.78% | 9/11 | 47.14% historical, below 60% floor; both target teams previously U2.5 |

Keep market availability independent from score validation. A 85% rate on an unavailable threshold does not justify switching to Under 3.5.
