# OVERS — full-time goal totals

Unless otherwise noted, validation refers to seasons `139216–139226`, and a *source* is a completed previous matchday. Count target success when full-time total is > market threshold. Rules repeated under Pattern 2 are **aliases of existing tests**, not new independent sample sizes.

## Original frozen Over 2.5 strategies (from `backend/private_rules.py`)

| League | Market | Rule | Wins/tests | Historical hit rate | Market baseline | Positive seasons | Notes |
|---|---|---|---:|---:|---:|---|---|
| English | Over 2.5 | `P4.ht00.pos7` | 68/107 | 63.55% | 58.68% | 6/11 | Source row 7 HT 0-0; target the same row next matchday |
| Spanish | Over 2.5 | `P7.ht00over.loser` | 145/212 | 68.40% | 57.22% | 9/11 | 0–0 HT, decisive Over 2.5 FT; follow losing team |
| Italian | Over 2.5 | `P4.ht00.pos6` | 68/105 | 64.76% | 56.56% | 8/11 | Source row 6 HT 0-0; target same row |
| German | Over 2.5 | `P13.rank3.loser` | 374/558 | 67.03% | 62.50% | 8/11 | Third-highest distinct source FT-goal total; follow loser |
| French | Over 2.5 | `P7.ht00over.winner` | 104/157 | 66.24% | 59.60% | 8/11 | Source 0–0 HT to Over 2.5 FT; follow winner |
| Dutch | Over 2.5 | `P4.ft00` | 89/126 | 70.63% | 65.04% | 9/11 | Source 0–0 FT; follow same fixture row |
| Portuguese | Over 2.5 | `P6.ge6.loser` | 159/245 | 64.90% | 58.74% | 7/11 | Source >=6 FT goals; follow loser |

These are existing code definitions, not re-run in this documentation change. Even when above 60%, a strategy may have season instability or weak baseline edge.

## 3 deployed/newer Over 1.5 rules
| League | Market | Rule | Wins/tests | Historical hit rate | Market baseline | Positive seasons | Notes |
|---|---|---|---:|---:|---:|---|---|
| Spanish | Over 1.5 | `P7.ht00over.loser` | 184/212 | 86.79% | 80.08% | 10/11 | Same source event as Spanish O2.5 but different target threshold |
| Portuguese | Over 1.5 | `P6.ge6.home` | 252/300 | 84.00% | 80.96% | 8/11 | Source >=6 total; follow source home side |
| Spanish | Over 1.5 | `P3.sh3.loser` | 586/703 | 83.36% | 80.08% | 9/11 | >=3 second-half source goals; follow source loser |

## 16 deployed/newer Over 2.5 entries

| League | Market | Rule | Wins/tests | Historical hit rate | Market baseline | Positive seasons | Notes |
|---|---|---|---:|---:|---:|---|---|
| Dutch | Over 2.5 | `P7.htdrawdecisive.winner` | 516/751 | 68.71% | 65.04% | 9/11 | HT draw, decisive FT; follow winner |
| Dutch | Over 2.5 | `P6.ge6.both` | 511/745 | 68.59% | 65.04% | 10/11 | Source >=6 total; follow both teams; P2-O25-01 alias |
| Spanish | Over 2.5 | `P7.ht00over.loser` | 145/212 | 68.40% | 57.22% | 9/11 | Same as original Spanish frozen rule; not a second independent observation |
| German | Over 2.5 | `P6.ge6.winner` | 186/280 | 66.43% | 62.50% | 8/11 | Source >=6 total; follow winner |
| English | Over 2.5 | `P6.eq5.away` | 217/342 | 63.45% | 58.68% | 9/11 | Exactly five source goals; follow away side |
| French | Over 2.5 | `P6.ge5.home` | 404/637 | 63.42% | 59.60% | 8/11 | Source >=5 goals; follow home side; P2-O25-03 alias |
| French | Over 2.5 | `P9.last3over` | 745/1180 | 63.14% | 59.60% | 11/11 | Selected team's prior three O2.5; P2-O25-02 alias |
| English | Over 2.5 | `P7.ht00over.away` | 143/229 | 62.45% | 58.68% | 9/11 | 0–0 HT then O2.5; follow away side |
| Spanish | Over 2.5 | `P6.eq5.home` | 223/358 | 62.29% | 57.22% | 9/11 | Exactly five source goals; follow home side |
| Spanish | Over 2.5 | `P3.sh3.loser` | 436/703 | 62.02% | 57.22% | 9/11 | Source >=3 second-half goals; follow loser |
| Spanish | Over 2.5 | `P1.rank1.away` | 321/518 | 61.97% | 57.22% | 8/11 | Max distinct source FT total; follow away side; P2-O25-04 alias |
| Spanish | Over 2.5 | `P13.rank3.home` | 483/784 | 61.61% | 57.22% | 8/11 | Third-highest distinct FT total; follow home side |
| Spanish | Over 2.5 | `P11.bothover` | 713/1161 | 61.41% | 57.22% | 8/11 | Both target teams had prior O2.5 |
| Spanish | Over 2.5 | `P8.conceded4` | 309/505 | 61.19% | 57.22% | 9/11 | Follow a team that conceded >=4 |
| Italian | Over 2.5 | `P7.ht00over.home` | 174/287 | 60.63% | 56.56% | 8/11 | 0–0 HT, O2.5 FT; follow source home side; P2-O25-05 alias |
| Spanish | Over 2.5 | `P9.last3over` | 752/1242 | 60.55% | 57.22% | 10/11 | Team's previous 3 fixtures O2.5 |

## Exploratory, not deployed
- Dutch Over 3.5 after rank-1 source home: **217/478 = 45.40%**, 10/11 positive relative to its 42.21% baseline; below 60% floor.
- English three-season highest-goal match followed by next-matchday O2.5: include ties/both teams 161/265 (60.75%); original winner/include 98/155 (63.23%). These are **different selection rules** and cannot be combined as one rate.
- English CHE–TOT: Over 2.5 was **72.2%** with Chelsea home and **72.2%** with Tottenham home in the 21-season archived pairing check; home and away directions must be separately tracked.
- English AST–CRY: Over 2.5 was **68.8%** when AST hosted CRY versus **38.9%** when CRY hosted AST in the same archive.
