# BTTS — both teams to score

`BTTS YES` requires home FT goals >=1 and away FT goals >=1. `BTTS NO` requires at least one side to finish on zero. The same source rule can produce different percentages for Over 2.5 and BTTS; these are not interchangeable.

## 14 existing BTTS YES definitions (`backend/private_rules.py`)

| League | Market | Rule | Wins/tests | Historical hit rate | Market baseline | Positive seasons | Notes |
|---|---|---|---:|---:|---:|---|---|
| Dutch | BTTS YES | `P6.ge6.winner` | 218/325 | 67.08% | 63.15% | 8/11 | Source >=6 goals; follow winner; P2-BTTS-01 alias |
| Dutch | BTTS YES | `P1.rank1.home` | 318/478 | 66.53% | 63.15% | 8/11 | Max distinct FT-total source match; follow home team |
| Dutch | BTTS YES | `P3.sh3.winner` | 502/756 | 66.40% | 63.15% | 9/11 | Source >=3 second-half goals; follow winner |
| Spanish | BTTS YES | `P7.ht00over.both` | 288/446 | 64.57% | 58.29% | 9/11 | Source 0–0 HT then O2.5 FT; follow both teams |
| French | BTTS YES | `P2.margin.winner` | 351/548 | 64.05% | 59.72% | 8/11 | Largest winning-margin source match; follow winner; P2-BTTS-02 alias |
| Spanish | BTTS YES | `P6.ge6.away` | 186/291 | 63.92% | 58.29% | 8/11 | Source >=6 total; follow source away team |
| English | BTTS YES | `P7.ht00over.away` | 146/229 | 63.76% | 59.56% | 8/11 | Source HT 0–0 → O2.5; follow away side |
| Spanish | BTTS YES | `P3.sh3.loser` | 444/703 | 63.16% | 58.29% | 10/11 | Source >=3 second-half goals; follow loser |
| Spanish | BTTS YES | `P11.bothover` | 732/1161 | 63.05% | 58.29% | 10/11 | Both target teams had prior O2.5; P2-BTTS-03 alias |
| Italian | BTTS YES | `P6.ge6.winner` | 140/224 | 62.50% | 57.74% | 9/11 | Source >=6 total; follow winner |
| Spanish | BTTS YES | `P8.conceded4` | 315/505 | 62.38% | 58.29% | 9/11 | Follow a team that conceded >=4 |
| Spanish | BTTS YES | `P6.eq4.home` | 352/570 | 61.75% | 58.29% | 9/11 | Exactly four source FT goals; follow home side |
| Spanish | BTTS YES | `P13.rank3.home` | 484/784 | 61.73% | 58.29% | 8/11 | Third-highest distinct source total; follow source home side |
| Spanish | BTTS YES | `P9.last3over` | 764/1242 | 61.51% | 58.29% | 9/11 | Selected team's previous three fixtures all O2.5 |

## Archival BTTS NO candidates — NOT deployed
| League | Market | Rule | Wins/tests | Historical hit rate | Market baseline | Positive seasons | Notes |
|---|---|---|---:|---:|---:|---|---|
| Italian | BTTS NO | `P2.margin.winner` | 270/578 | 46.71% | 42.26% | 8/11 | 46.71%, below 60% floor |
| Spanish | BTTS NO | `P11.bothunder` | 299/647 | 46.21% | 41.71% | 8/11 | 46.21%, below 60% floor |

## English venue-independent exploratory candidate
Across 21 archived seasons, Chelsea vs Tottenham had BTTS YES **14/18 (77.8%)** when `CHE–TOT`, and **14/18 (77.8%)** when `TOT–CHE`. This interesting equality is **not** proof that the future pairing will maintain 77.8%. Check each future venue separately, report both losses and longest drought, and validate on new seasons.

## New independent fixture-pair audit (13 Nov 2026)

See [the market-specific pair verification](PAIR_MARKETS_2026-11-13.md) for AST–CRY, TOT–CRY, CHE–TOT and BRE–SUN in **both home/away directions**, with raw scores and separately computed validation/recent rates. [Same-match overlap audit](../TESTS/PAIR_MARKET_INTERSECTIONS_2026-11-13.md) lists the occasions when BTTS YES, Over 2.5 and a home/away win simultaneously occurred. This cross-reference does **not** merge the separate market patterns, and none was enabled in the live predictor.
