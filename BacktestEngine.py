from __future__ import annotations

import math
from typing import List, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from Multi_Indicator_Algorithm import Multi_Indicator_Algorithm as MIA
from Position import Position
from RiskManagement import RiskManagement

TRADING_DAYS = 252


class BacktestEngine:
    """Event loop and the single owner of all mutable state.

    Cash, the open position, the closed-trade log and the equity curve live
    here and nowhere else; the strategy and the risk model stay pure so they
    can be reasoned about and tested in isolation.
    """

    def __init__(
        self,
        initial_cash: float = 10_000.0,
        slippage_bps: float = 5.0,
        commission: float = 1.0,
        apply_commission: bool = True,
    ) -> None:
        """Configure the execution model.

        slippage_bps: applied adverse to the trade direction on every fill.
        commission: flat currency amount charged per fill (entry and exit).
        """
        self.initial_cash = initial_cash
        self.slippage_bps = slippage_bps
        self.commission = commission
        self.apply_commission = apply_commission
        self._reset()

    def _reset(self) -> None:
        """Clear all run state so an engine instance can be reused."""
        self.cash: float = self.initial_cash
        self.position: Optional[Position] = None
        self.trades: List[dict] = []
        self.equity_curve: List[float] = []
        self.equity_dates: List[pd.Timestamp] = []
        self.bars_in_market: int = 0
        self.data: Optional[pd.DataFrame] = None
        self.ticker: str = ""
        self._buy_hold_curve: Optional[pd.Series] = None

    # ---------- execution helpers ----------

    def _fill_price(self, price: float, side: str) -> float:
        """Return `price` adjusted for slippage, adverse to `side`.

        Buys fill a touch higher and sells a touch lower than the quoted level:
        a backtest that fills at the exact printed price is claiming free
        liquidity it would not get live.
        """
        slip = self.slippage_bps / 10_000.0
        return price * (1.0 + slip) if side == "BUY" else price * (1.0 - slip)

    def _commission_cost(self) -> float:
        """Return the commission charged on a single fill."""
        return self.commission if self.apply_commission else 0.0

    def _open_position(self, price: float, date: pd.Timestamp, atr: float, risk: RiskManagement) -> None:
        """Size and open a long position at `price`, if size and cash allow."""
        if not np.isfinite(atr) or atr <= 0:
            return

        fill = self._fill_price(price, "BUY")
        stop = risk.get_stop_price(fill, atr)
        target = risk.get_take_profit(fill, atr)
        equity = self.cash  # flat by construction, so equity is all cash here

        # Commission is deducted from the cash available to the sizer so that a
        # fully-funded position cannot overdraw the account by the fee.
        investable = max(0.0, self.cash - self._commission_cost())
        shares = risk.calculate_shares(equity, investable, fill, stop)
        if shares <= 0:
            return

        cost = shares * fill + self._commission_cost()
        if cost > self.cash:
            return

        self.cash -= cost
        self.position = Position(
            shares=shares,
            entry_price=fill,
            entry_date=date,
            stop_price=stop,
            target_price=target,
            highest_close_since_entry=fill,
        )

    def _close_position(self, price: float, date: pd.Timestamp, reason: str) -> None:
        """Close the open position at `price` and append it to the trade log."""
        pos = self.position
        if pos is None:
            return

        fill = self._fill_price(price, "SELL")
        proceeds = pos.shares * fill - self._commission_cost()
        self.cash += proceeds

        risk_per_share = pos.entry_price - pos.initial_stop_price
        pnl = (fill - pos.entry_price) * pos.shares - 2 * self._commission_cost()
        r_multiple = (fill - pos.entry_price) / risk_per_share if risk_per_share > 0 else np.nan

        self.trades.append(
            {
                "entry_date": pos.entry_date,
                "exit_date": date,
                "entry_price": pos.entry_price,
                "exit_price": fill,
                "shares": pos.shares,
                "exit_reason": reason,
                "pnl": pnl,
                "return_pct": (fill / pos.entry_price) - 1.0,
                "r_multiple": r_multiple,
                # Actual bars elapsed, from index positions. busday_count would
                # miscount by every market holiday in the holding period.
                "bars_held": int(
                    self.data.index.get_loc(date) - self.data.index.get_loc(pos.entry_date)
                ),
            }
        )
        self.position = None

    # ---------- main loop ----------

    def run_backtest(
        self,
        data: pd.DataFrame,
        strategy: MIA,
        risk: RiskManagement,
        warmup: int = 1,
        ticker: str = "",
    ) -> dict:
        """Run the event loop over `data` and return the metrics dict.

        warmup: first bar index evaluated. Defaults to 1 because the strategy
            reads iloc[-2] for its cross checks; DataProcessor has already
            removed the indicator warmup rows.
        """
        self._reset()
        self.data = data
        self.ticker = ticker

        # Signals are computed on bar i's close but cannot be acted on until the
        # market next trades. Rather than reaching forward to data.iloc[i+1],
        # which would let bar i's equity reflect a fill that has not happened,
        # orders are queued and executed at the *next* iteration's open. Same
        # economics, and structurally incapable of lookahead.
        pending_entry = False
        pending_exit = False

        for i in range(warmup, len(data)):
            bar = data.iloc[i]
            history = data.iloc[: i + 1]  # information set available at bar i's close
            date = data.index[i]
            atr = float(data["ATR_14"].iloc[i - 1])  # ATR known as of the signal bar

            # 0. Execute orders queued on the previous bar, at this bar's open.
            if pending_exit and self.position is not None:
                self._close_position(float(bar["Open"]), date, "SIGNAL")
            pending_exit = False

            if pending_entry and self.position is None:
                self._open_position(float(bar["Open"]), date, atr, risk)
            pending_entry = False

            # 1. Protective levels are resting orders placed before the bar
            #    opened, so they fill intrabar on this bar, not at the next open.
            if self.position is not None:
                hit = risk.check_exit(self.position, bar)
                if hit is not None:
                    reason, fill_price = hit
                    self._close_position(fill_price, date, reason)

            # 2. Strategy exit: computed on this close, so it fills next open.
            if self.position is not None:
                signal = strategy.generate_signal(history)
                if signal.type == "SELL":
                    pending_exit = True

            # 3. Trail the stop on what is still open.
            if self.position is not None and not pending_exit:
                if np.isfinite(float(bar["ATR_14"])):
                    self.position.stop_price = risk.update_trailing_stop(
                        self.position, bar, float(bar["ATR_14"])
                    )

            # 4. Entries only when flat, and only on the last bar's information.
            if self.position is None and not pending_exit:
                signal = strategy.generate_signal(history)
                if signal.type == "BUY":
                    pending_entry = True

            # 5. Mark to market on this bar's close.
            shares = self.position.shares if self.position is not None else 0
            if shares:
                self.bars_in_market += 1
            self.equity_curve.append(self.cash + shares * float(bar["Close"]))
            self.equity_dates.append(date)

        # Force-close anything still open at the final close so the equity curve
        # and the trade log agree. Flagged END_OF_DATA: it is an accounting
        # close, not a decision the strategy made.
        if self.position is not None:
            last_date = data.index[-1]
            self._close_position(float(data["Close"].iloc[-1]), last_date, "END_OF_DATA")
            self.equity_curve[-1] = self.cash

        self._buy_hold_curve = self._build_buy_hold(data, warmup)
        self.results = self._compute_all_metrics()
        return self.results

    # ---------- benchmark ----------

    def _build_buy_hold(self, data: pd.DataFrame, warmup: int) -> pd.Series:
        """Return the buy-and-hold equity curve over the identical bar range.

        Charged the same slippage and commission as the strategy's first fill,
        so the comparison is not quietly rigged by giving the benchmark a
        frictionless entry.
        """
        window = data.iloc[warmup:]
        entry = self._fill_price(float(window["Open"].iloc[0]), "BUY")
        shares = math.floor((self.initial_cash - self._commission_cost()) / entry)
        residual_cash = self.initial_cash - self._commission_cost() - shares * entry
        return pd.Series(residual_cash + shares * window["Close"].values, index=window.index)

    # ---------- metrics ----------

    def _curve_metrics(self, curve: pd.Series) -> dict:
        """Return return/risk metrics computed from an equity curve."""
        n_bars = len(curve)
        start, end = float(curve.iloc[0]), float(curve.iloc[-1])
        rets = curve.pct_change().dropna()

        years = n_bars / TRADING_DAYS
        total_return = end / start - 1.0
        cagr = (end / start) ** (1.0 / years) - 1.0 if years > 0 and start > 0 and end > 0 else np.nan

        vol = float(rets.std(ddof=1)) * math.sqrt(TRADING_DAYS) if len(rets) > 1 else np.nan
        sharpe = (
            float(rets.mean()) / float(rets.std(ddof=1)) * math.sqrt(TRADING_DAYS)
            if len(rets) > 1 and float(rets.std(ddof=1)) > 0
            else np.nan
        )
        downside = rets[rets < 0]
        sortino = (
            float(rets.mean()) / float(downside.std(ddof=1)) * math.sqrt(TRADING_DAYS)
            if len(downside) > 1 and float(downside.std(ddof=1)) > 0
            else np.nan
        )
        max_dd = float((curve / curve.cummax() - 1.0).min())

        return {
            "final_equity": end,
            "total_return": total_return,
            "cagr": cagr,
            "ann_vol": vol,
            "max_drawdown": max_dd,
            "sharpe": sharpe,
            "sortino": sortino,
        }

    def _trade_metrics(self) -> dict:
        """Return trade-level statistics from the closed-trade log."""
        n = len(self.trades)
        if n == 0:
            return {
                "n_trades": 0, "win_rate": np.nan, "profit_factor": np.nan,
                "avg_win": np.nan, "avg_loss": np.nan, "avg_r": np.nan,
                "expectancy": np.nan, "avg_bars_held": np.nan,
            }

        pnls = np.array([t["pnl"] for t in self.trades], dtype=float)
        rs = np.array([t["r_multiple"] for t in self.trades], dtype=float)
        wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
        gross_win, gross_loss = float(wins.sum()), float(-losses.sum())

        return {
            "n_trades": n,
            "win_rate": len(wins) / n,
            "profit_factor": gross_win / gross_loss if gross_loss > 0 else np.inf,
            "avg_win": float(wins.mean()) if len(wins) else 0.0,
            "avg_loss": float(losses.mean()) if len(losses) else 0.0,
            "avg_r": float(np.nanmean(rs)) if n else np.nan,
            "expectancy": float(pnls.mean()),
            "avg_bars_held": float(np.mean([t["bars_held"] for t in self.trades])),
        }

    def _compute_all_metrics(self) -> dict:
        """Assemble strategy metrics, benchmark metrics and the trade log."""
        curve = pd.Series(self.equity_curve, index=pd.DatetimeIndex(self.equity_dates))
        strat = self._curve_metrics(curve)
        strat.update(self._trade_metrics())
        strat["time_in_market"] = self.bars_in_market / len(curve) if len(curve) else np.nan
        strat["n_bars"] = len(curve)

        bh = self._curve_metrics(self._buy_hold_curve)
        bh["time_in_market"] = 1.0
        bh["n_bars"] = len(self._buy_hold_curve)

        return {
            "ticker": self.ticker,
            "strategy": strat,
            "buy_hold": bh,
            "equity_curve": curve,
            "buy_hold_curve": self._buy_hold_curve,
            "trades": self.trades,
        }

    # ---------- reporting ----------

    def print_trade_log(self) -> None:
        """Print every closed trade with dates, prices, reason and R multiple."""
        print(f"\nTRADE LOG — {self.ticker}  ({len(self.trades)} closed trades)")
        if not self.trades:
            print("  (no trades)")
            return
        header = (f"  {'#':>3} {'Entry':<12}{'Exit':<12}{'EntryPx':>9}{'ExitPx':>9}"
                  f"{'Sh':>5}{'Reason':>12}{'P&L$':>10}{'R':>7}{'Bars':>6}")
        print(header)
        print("  " + "-" * (len(header) - 2))
        for n, t in enumerate(self.trades, 1):
            print(f"  {n:>3} {t['entry_date'].date()!s:<12}{t['exit_date'].date()!s:<12}"
                  f"{t['entry_price']:>9.2f}{t['exit_price']:>9.2f}{t['shares']:>5}"
                  f"{t['exit_reason']:>12}{t['pnl']:>10.2f}{t['r_multiple']:>7.2f}{t['bars_held']:>6}")

    def print_metrics(self) -> None:
        """Print strategy metrics beside buy-and-hold on the same ticker/window."""
        s, b = self.results["strategy"], self.results["buy_hold"]

        def pct(v: float) -> str:
            return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v * 100:,.2f}%"

        def num(v: float) -> str:
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return "—"
            if np.isinf(v):
                return "inf"
            return f"{v:,.2f}"

        rows = [
            ("Final equity ($)", num(s["final_equity"]), num(b["final_equity"])),
            ("Total return", pct(s["total_return"]), pct(b["total_return"])),
            ("CAGR", pct(s["cagr"]), pct(b["cagr"])),
            ("Annualised vol", pct(s["ann_vol"]), pct(b["ann_vol"])),
            ("Max drawdown", pct(s["max_drawdown"]), pct(b["max_drawdown"])),
            ("Sharpe (rf=0)", num(s["sharpe"]), num(b["sharpe"])),
            ("Sortino (rf=0)", num(s["sortino"]), num(b["sortino"])),
            ("Time in market", pct(s["time_in_market"]), pct(b["time_in_market"])),
            ("Number of trades", f"{s['n_trades']:,}", "1"),
            ("Win rate", pct(s["win_rate"]), "—"),
            ("Profit factor", num(s["profit_factor"]), "—"),
            ("Average win ($)", num(s["avg_win"]), "—"),
            ("Average loss ($)", num(s["avg_loss"]), "—"),
            ("Average R multiple", num(s["avg_r"]), "—"),
            ("Expectancy ($/trade)", num(s["expectancy"]), "—"),
            ("Avg holding (bars)", num(s["avg_bars_held"]), f"{b['n_bars']:,}"),
        ]

        title = f"{self.ticker}  —  {s['n_bars']:,} bars"
        print(f"\n{'=' * 66}\n{title}\n{'=' * 66}")
        print(f"{'Metric':<24}{'Strategy':>20}{'Buy & Hold':>20}")
        print("-" * 66)
        for label, sv, bv in rows:
            print(f"{label:<24}{sv:>20}{bv:>20}")
        print("=" * 66)

    def plot_equity_curve(self, save_path: Optional[str] = None, show: bool = True) -> None:
        """Plot strategy equity against buy-and-hold on one axis."""
        curve, bh = self.results["equity_curve"], self.results["buy_hold_curve"]

        fig, ax = plt.subplots(figsize=(11, 6))
        ax.plot(curve.index, curve.values, label="Strategy", linewidth=1.5)
        ax.plot(bh.index, bh.values, label="Buy & Hold", linewidth=1.5, alpha=0.8)
        ax.axhline(self.initial_cash, color="grey", linestyle="--", linewidth=0.8)
        ax.set_title(f"{self.ticker} — Strategy vs Buy & Hold")
        ax.set_xlabel("Date")
        ax.set_ylabel("Equity ($)")
        ax.legend()
        ax.grid(alpha=0.3)
        fig.tight_layout()

        if save_path:
            fig.savefig(save_path, dpi=120)
        if show:
            plt.show()
        plt.close(fig)
