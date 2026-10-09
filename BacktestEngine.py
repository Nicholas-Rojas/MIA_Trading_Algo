import numpy as np
import pandas as pd

from Multi_Indicator_Algorithm import Multi_Indicator_Algorithm as MIA
from Position import Position
from RiskManagement import RiskManagement

# Simulates the strategy day by day: tracks cash, the open position, closed
# trades, and account value, then reports metrics against buy-and-hold.

class BacktestEngine:

    def __init__(self, initial_cash=10_000):

        self.data = None
        self.initial_cash = initial_cash

        self.cash = initial_cash
        self.position = None          # a Position, or None when flat
        self.trades = []              # closed trades
        self.equity_curve = []
        self.equity_dates = []

        self.entry_index = None       # bar index of the open entry, for holding period


    # Replays each day from bar 200 on: check exits, 
    # then the strategy signal, then entries, then record account value.

    def run_backtest(self, data, strategy: MIA, risk: RiskManagement):

        self.data = data

        # Start at 200: SMA_200 is NaN before that, so any earlier bar would be
        # scored on an undefined trend.
        for i in range(200, len(data)):

            bar = data.iloc[i]
            history = data.iloc[:i+1]     # only bars up to and including i — no lookahead

            # The strategy is stateless, so the signal is the same whether or not
            # we hold a position. Computed once and used by both the exit and the
            # entry branch below.
            signal = strategy.generate_signal(history)

            # 1. Stop / target. These are resting orders placed when the trade was
            #    opened, so they fill intrabar on this bar rather than at the close.
            if self.position is not None:

                hit = risk.check_exit(self.position, bar)

                if hit is not None:

                    reason, fill_price = hit
                    self._close(fill_price, data.index[i], i, reason)

            # 2. Strategy exit.
            if self.position is not None and signal.type == 'SELL':

                self._close(bar['Close'], data.index[i], i, 'SIGNAL')

            # 3. Entry, only when flat. Note this can re-enter on the same bar a
            #    stop was hit, since the position is already closed by step 1.
            if self.position is None and signal.type == 'BUY':

                self._open(bar['Close'], data.index[i], i, risk)

            # 4. Mark to market on this bar's close.
            shares = self.position.shares if self.position is not None else 0
            self.equity_curve.append(self.cash + shares * bar['Close'])
            self.equity_dates.append(data.index[i])


    # Buys at today's close using RiskManagement's sizing and stores the Position.

    def _open(self, price, date, index, risk):

        # SIMPLIFICATION: we fill at the same close the signal was computed from.
        # Real execution would be the next bar's open, because the signal isn't
        # known until this bar has already closed. This makes results slightly
        # optimistic.
        stop_price = risk.get_stop_price(price)
        target_price = risk.get_take_profit(price)

        equity = self.cash            # flat here by construction, so equity is all cash
        shares = risk.calculate_shares(equity, self.cash, price, stop_price)

        if shares <= 0:

            return

        self.cash -= shares * price
        self.position = Position(shares, price, date, stop_price, target_price)
        self.entry_index = index


    # Sells the whole position and records the trade.

    def _close(self, price, date, index, reason):

        position = self.position

        self.cash += position.shares * price

        self.trades.append({
            'entry_date': position.entry_date,
            'exit_date': date,
            'entry_price': position.entry_price,
            'exit_price': price,
            'shares': position.shares,
            'exit_reason': reason,
            'pnl': (price - position.entry_price) * position.shares,
            'bars_held': index - self.entry_index,
        })

        self.position = None
        self.entry_index = None

    # ---------- metrics ----------
    # Return per unit of volatility

    def _sharpe(self, curve):

        returns = curve.pct_change().dropna()

        if len(returns) < 2 or returns.std() == 0:

            return float('nan')

        # rf = 0, daily returns scaled to annual by sqrt(252).
        return returns.mean() / returns.std() * np.sqrt(252)
    

    # Largest peak-to-trough drop in account value

    def _max_drawdown(self, curve):

        return (curve / curve.cummax() - 1).min()


    def _buy_hold_curve(self):

        # Same ticker, same bars, same starting cash: buy at the first bar the
        # strategy could have traded and hold to the end.
        closes = self.data['Close'].iloc[200:]

        return self.initial_cash * closes / closes.iloc[0]


    # Prints strategy vs. buy-and-hold metrics, then the trade log.

    def print_metrics(self):

        strategy_curve = pd.Series(self.equity_curve, index=pd.DatetimeIndex(self.equity_dates))
        bh_curve = self._buy_hold_curve()

        n_trades = len(self.trades)
        wins = [t for t in self.trades if t['pnl'] > 0]

        win_rate = len(wins) / n_trades if n_trades else float('nan')
        avg_hold = np.mean([t['bars_held'] for t in self.trades]) if n_trades else float('nan')

        def pct(v):
            return '—' if v is None or (isinstance(v, float) and np.isnan(v)) else '{:,.2f}%'.format(v * 100)

        def num(v):
            return '—' if v is None or (isinstance(v, float) and np.isnan(v)) else '{:,.2f}'.format(v)

        rows = [
            ('Total return', pct(strategy_curve.iloc[-1] / self.initial_cash - 1),
                             pct(bh_curve.iloc[-1] / self.initial_cash - 1)),
            ('Max drawdown', pct(self._max_drawdown(strategy_curve)),
                             pct(self._max_drawdown(bh_curve))),
            ('Win rate', pct(win_rate), '—'),
            ('Sharpe (rf=0)', num(self._sharpe(strategy_curve)), num(self._sharpe(bh_curve))),
            ('Number of trades', '{:,}'.format(n_trades), '1'),
            ('Avg holding (bars)', num(avg_hold), '{:,}'.format(len(bh_curve))),
        ]

        print('\n' + '=' * 60)
        print('{:<22}{:>18}{:>20}'.format('Metric', 'Strategy', 'Buy & Hold'))
        print('-' * 60)

        for label, strategy_value, bh_value in rows:
            print('{:<22}{:>18}{:>20}'.format(label, strategy_value, bh_value))

        print('=' * 60)
        print('Final equity: ${:,.2f}   |   Buy & hold: ${:,.2f}'.format(
            strategy_curve.iloc[-1], bh_curve.iloc[-1]))

        self.print_trade_log()


    # One line per closed trade.

    def print_trade_log(self):

        print('\nTRADE LOG ({} closed trades)'.format(len(self.trades)))

        if not self.trades:

            print('  (no trades)')
            return

        header = '  {:<12}{:<12}{:>10}{:>10}{:>10}{:>12}'.format(
            'Entry', 'Exit', 'EntryPx', 'ExitPx', 'Reason', 'P/L $')
        print(header)
        print('  ' + '-' * (len(header) - 2))

        for t in self.trades:
            print('  {:<12}{:<12}{:>10.2f}{:>10.2f}{:>10}{:>12.2f}'.format(
                str(t['entry_date'].date()), str(t['exit_date'].date()),
                t['entry_price'], t['exit_price'], t['exit_reason'], t['pnl']))
