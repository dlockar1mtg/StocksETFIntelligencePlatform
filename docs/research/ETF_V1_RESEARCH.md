# ETF v1 research (October 2026)

**Question.** For the ETFs Devon holds, does any simple rule for *when* to put in new money beat plain monthly buying over the primary three-year horizon? And what, if anything, should change the guidance?

**Data.** Daily closes, distributions and splits from the Yahoo chart feed (tier 4), with total return rebuilt with distributions reinvested at the ex-date close (`return_standard.json`). The rebuilt series matched the provider's adjusted close within 0.03% over three years for every fund. Latest closes matched Nasdaq exactly. Histories:

| Fund | From |
|---|---|
| SPY (VOO's proxy) | 1993 |
| DIA | 1998 |
| QQQ (QQQM's proxy) | 1999 |
| IWM, IYY | 2000 |
| SCHD | 2011 |
| EDOW | 2017 |

BIL (since 2007) is the cash that paused money earns.

**Method.** The gate and the rule grids were registered in `config/market/etf_v1_model.json` before any result was seen.
- Each start month, $100 is contributed for 36 months.
- A rule may hold contributions in cash and invest the pile later (at the latest after 12 months of waiting).
- The baseline invests every month.
- The parameter for each rule family is chosen walk-forward: for each test start from 2013-01, the parameter with the best mean edge on backtests whose 36-month window had already ended, pooled across funds.
- 848 out-of-sample starts per family (2013-01 to 2023-09, seven funds). These overlap heavily: only about three to four independent three-year periods per fund.

## Results: no timing rule passes

| Rule family | Beat monthly buying | Median edge | Worst | Gate |
|---|---|---|---|---|
| Pause below the 200-day average | 5% of starts | -0.8% | -4.0% | fail |
| Buy only below the 200-day average | 41% | 0.0% | -3.1% | fail |
| Pause when stretched (vs 5-year average) | 8% | 0.0% | -8.6% | fail |
| Wait for a dip from the peak | 18% | -3.6% | -15.5% | fail |

Waiting for dips was the costliest. Its median edge was negative in every fund, from -1.2% (EDOW) to -5.6% (QQQ).

## What does carry information: stretch

Stretch is the total-return index against its own five-year average.
- Its pooled rank correlation with the next three years' return was **-0.23** (1,331 month-ends).
- By fund: SPY -0.36, IYY -0.45, IWM -0.65, DIA -0.30, SCHD -0.71 (only two independent periods), QQQ +0.02.
- For SPY, the most stretched fifth of months (1.45 to 1.82) was followed by a median **7.5%** a year over three years, against 11.0% for all months.
- Those returns were still mostly above cash, so pausing did not pay.
- Stretch is therefore shown as **context** ("expect lower than usual"), not as a call.

## Choosing between funds: momentum is too weak to use

Ranking SPY, QQQ, DIA and IWM by 12-month momentum gave the following rank correlations with the following period:

| Next period | Mean rank correlation | Months positive |
|---|---|---|
| 12 months | +0.08 | 51% |
| 36 months | +0.18 | 61% |

This is mostly one regime, the Nasdaq-100's long lead, so momentum isn't used.

## What the guidance is

- **Steady monthly buying** for every fund, with stretch, trend, drawdown, income and risk shown as readings.
- **Redirect new money** where two held funds are the same exposure and one is cheaper *and* tracked at least as well over three years. Shares already held can stay.
  - QQQ → QQQM: same Nasdaq-100 index, 0.15% vs 0.18%, +0.07% a year.
  - IYY → VOO: 0.997 correlation, 0.03% vs 0.20%, +0.47% a year.
- DIA and EDOW hold the same 30 stocks weighted differently (0.956 correlation). They are shown as an overlap, not a duplicate.

## Limits

- Free tier-4 data, so everything is **provisional**, not certified.
- There are few independent three-year periods. Results are robust in sign across funds but not precise.
- Before 2007 there is no cash series, so timing rules are only simulated from 2007, which includes 2008, 2020 and 2022.
- Valuation (P/E, yield spreads) and holdings-level overlap are not yet in the data. They are the next research step.
- Re-running `scripts/research_etf_v1.py` reproduces the evidence file `data/curated/etf/research/etf_v1_research.json`.
