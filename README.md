# Multi-Indicator Trading Strategy Backtester

A Python backtesting system for a long-only equity strategy that combines a moving-average trend filter with volume and RSI confirmation, using a **weighted signal score** instead of nested if/else rules. It includes risk-based position sizing, fixed stop-loss / take-profit exits, and a buy-and-hold benchmark for every run.

Tested on **NVDA, TSLA, and MSFT**, daily bars, Oct 2021 – Dec 2024. The period covers both the **2022 bear market** and the 2023–2024 recovery.

---

## Results

$10,000 starting capital per ticker. Data starts on 2021-01-01, and the first 200 bars warm up the 200-day moving average, so trading runs from roughly **Oct 2021 to Dec 2024**. Buy-and-hold is measured over the same bars.

| Ticker | Return (Strategy / B&H) | Max Drawdown (Strategy / B&H) | Sharpe (Strategy / B&H) | Trades | Win Rate |
|---|---|---|---|---|---|
| NVDA | 52.8% / 503.5% | **−12.8%** / −66.3% | **1.41** / 1.29 | 72 | 48.6% |
| TSLA | −4.2% / 40.2% | **−19.4%** / −73.6% | −0.11 / 0.48 | 53 | 28.3% |
| MSFT | 8.7% / 40.6% | **−6.5%** / −37.2% | **0.62** / 0.53 | 28 | 64.3% |

*Sharpe uses daily returns, annualized with √252, risk-free rate = 0.*

### How to read these results

- **The trend filter sat out the 2022 bear market.** On all three stocks, the 50-day SMA fell below the 200-day in spring 2022, and the strategy stopped trading for 9–13 months:

  | Ticker | Last trade before the downtrend | Next trade |
  |---|---|---|
  | NVDA | Apr 2022 | Jan 2023 |
  | TSLA | May 2022 | Jun 2023 |
  | MSFT | Mar 2022 | Mar 2023 |

  That's why the strategy's max drawdown is **one-quarter to one-sixth** of buy-and-hold's (e.g., −12.8% vs. −66.3% on NVDA).
- **The strategy loses to buy-and-hold on total return.** That's expected, because the strategy is in cash much of the time.
- **Position sizing caps exposure at 25% of equity.** With a 2% risk budget and a 5% stop, the risk formula asks for a 40% position, so the 25% concentration cap always applies. Roughly three-quarters of the account is in cash at all times. That alone explains most of the return gap, and it also accounts for part of the lower drawdowns.
- **Sharpe ratio is the fairer comparison** because it measures return per unit of volatility, which holding cash doesn't distort. On that basis the strategy **beats buy-and-hold on NVDA and MSFT** and **underperforms on TSLA**.
- **TSLA lost money.** Its win rate (28.3%) was barely above the ~25% breakeven implied by the 3:1 take-profit-to-stop ratio. TSLA's volatility means its 5% stop gets hit by ordinary daily noise, a sign that a fixed-percentage stop doesn't suit every stock.

---

## Strategy

Each day, three checks each contribute points to a score:

| Check | Condition | Points |
|---|---|---|
| Trend filter | 50-day SMA > 200-day SMA (uptrend) | 40 |
| Volume confirmation | Today's volume > 50-day volume average | 20 |
| RSI pullback | 14-day RSI < 40 | 25 |

- **BUY** when the score is **≥ 60**. That means an uptrend *plus* at least one confirmation: volume or a pullback. Neither confirmation alone can trigger a buy outside an uptrend.
- **SELL** (checked first, overriding the score) when the trend breaks (50-day SMA < 200-day SMA) or the stock is overbought (RSI > 70).
- **HOLD** otherwise.

Every signal carries a breakdown of each check's score, so any trade can be audited after the fact.

### Risk management

- **Stop-loss:** 5% below entry. **Take-profit:** 15% above entry (3:1 reward-to-risk).
- **Position sizing:** sized so that hitting the stop loses 2% of equity, then capped at 25% of equity and at available cash. No leverage, one position at a time.
- **Gap handling:** if a bar opens below the stop (an overnight gap down), the stop fills at the open, not at the stop price.
- **Ambiguous bars:** if one daily bar touches both the stop and the target, the stop is assumed to fill first, since daily OHLC data can't show which happened first. This is the conservative choice.

---

## Architecture

```
main.py                      Runs the backtest for each ticker and prints results
DataProcessor.py             Downloads OHLCV data (yfinance) and adds SMA, volume MA, RSI
Multi_Indicator_Algorithm.py Scores the three checks and returns a BUY / SELL / HOLD signal
TradeSignal.py               Signal object: type, score, per-check breakdown
Position.py                  Open position: shares, entry, stop, target
RiskManagement.py            Stop/target prices, position sizing, exit checks
BacktestEngine.py            Day-by-day simulation, cash/equity tracking, metrics, trade log
```

Each class has one job. The strategy only sees data up to the current bar, so there's **no lookahead**, and it doesn't know whether a position is open. The engine owns all state: cash, the open position, closed trades, and the equity curve.

---

## Design decisions

These came from bugs found in earlier versions:

- **Golden cross as a regime filter, not a one-time event.** Originally the trend check scored only on the exact day the 50-day crossed above the 200-day. That happened once or twice in three years, and since no other combination of checks reaches 60, it was effectively the only day a BUY could occur. Treating it as "is the trend up?" fixed this.
- **RSI < 40 instead of RSI < 70.** The original RSI check was true on about 85% of days, so it added points almost unconditionally and carried no information. Requiring a pullback makes it a real signal.
- **Stops fill at the open on gap-downs.** An earlier version always filled stops exactly at the stop price, which made every loss exactly −5%. On TSLA's January 2024 post-earnings gap, that understated the real loss by about half. Fixing it lowered TSLA's Sharpe from 0.46 to 0.24 on the original test window, a more honest number.
- **Extended the test window to include the 2022 bear market.** The first version downloaded data starting in 2022. Because of the 200-day warm-up, trading didn't begin until October 2022, so the test skipped the crash entirely and covered only a bull market. Starting the download in 2021 puts the full downturn inside the test.

---

## Limitations

- **Same-bar execution.** Entries fill at the close of the day the signal fires. In practice the signal isn't known until the close, so a real fill would be the next day's open. This makes results slightly optimistic.
- **No transaction costs or slippage.**
- **The trend filter reacts slowly.** The 200-day SMA is a lagging indicator. From late 2021 to spring 2022 the stocks were already falling but the 50-day SMA was still above the 200-day, so the strategy kept buying dips and stopped out repeatedly. NVDA hit its stop 16 times in that stretch before the filter turned off trading.
- **Whipsaw in choppy markets.** In sideways periods (e.g., NVDA Aug 2024, TSLA Jan 2024) the strategy repeatedly stops out and re-enters, sometimes on the same day.
- **Small sample.** Three large-cap tech stocks over about three years. The period includes a bear market and a bull market, but not a long sideways market or other asset classes.
- **Fixed parameters.** Weights, thresholds, and stop/target levels were set by reasoning, not optimized, and not tested out of sample.

---

## How to run

```bash
pip install -r requirements.txt
python main.py
```

Tickers and the date range are set in `main.py`. Output is a metrics table versus buy-and-hold, plus a full trade log for each ticker.

**Requirements:** Python 3.13.9 (replace with your `python --version`), `yfinance`, `pandas`, `numpy`, `ta`