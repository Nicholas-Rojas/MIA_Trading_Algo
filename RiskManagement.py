from __future__ import annotations

import math
from typing import Optional, Tuple

import pandas as pd

from Position import Position


class RiskManagement:
    """Stateless sizing and stop logic. Pure functions of their arguments.

    Deliberately performs no market-data lookups: everything it needs is passed
    in, so it cannot accidentally read a bar the caller has not reached yet.
    """

    def __init__(
        self,
        risk_per_trade: float = 0.02,
        atr_stop_mult: float = 2.0,
        atr_target_mult: float = 3.0,
        max_position_pct: float = 0.25,
        trail_atr_mult: float = 3.0,
    ) -> None:
        """Configure risk parameters.

        risk_per_trade: fraction of equity lost if the stop fills as placed.
        atr_stop_mult / atr_target_mult: stop and target distance in ATRs.
        max_position_pct: hard cap on one name's share of equity.
        trail_atr_mult: chandelier trail distance, wider than the initial stop
            so a winner is not shaken out by ordinary noise.
        """
        self.risk_per_trade = risk_per_trade
        self.atr_stop_mult = atr_stop_mult
        self.atr_target_mult = atr_target_mult
        self.max_position_pct = max_position_pct
        self.trail_atr_mult = trail_atr_mult

    def get_stop_price(self, entry_price: float, atr: float) -> float:
        """Return the initial stop: entry minus atr_stop_mult ATRs.

        Volatility-scaled rather than a fixed percentage, so the stop sits
        outside the instrument's normal daily range instead of at an arbitrary
        round number that noise alone would reach.
        """
        return entry_price - self.atr_stop_mult * atr

    def get_take_profit(self, entry_price: float, atr: float) -> float:
        """Return the static take-profit: entry plus atr_target_mult ATRs."""
        return entry_price + self.atr_target_mult * atr

    def calculate_shares(
        self,
        equity: float,
        cash: float,
        entry_price: float,
        stop_price: float,
    ) -> int:
        """Return whole shares to buy. May legitimately return 0.

        Zero is a valid answer, not an error: if the stop is so wide that the
        risk budget buys less than one share, the correct action is to skip the
        trade rather than to take more risk than the budget allows.
        """
        risk_per_share = entry_price - stop_price
        if risk_per_share <= 0 or entry_price <= 0:
            return 0

        risk_dollars = equity * self.risk_per_trade
        shares_by_risk = risk_dollars / risk_per_share

        # Concentration cap: even a tight stop must not put the book into one name.
        shares_by_exposure = (self.max_position_pct * equity) / entry_price

        # Cash cap: long only, no leverage, so the fill must be fully funded.
        shares_by_cash = cash / entry_price

        shares = min(shares_by_risk, shares_by_exposure, shares_by_cash)
        if shares < 0:
            return 0
        return int(math.floor(shares))

    def update_trailing_stop(self, position: Position, bar: pd.Series, atr: float) -> float:
        """Return the updated chandelier stop. Ratchets upward only.

        Mutates position.highest_close_since_entry as a side effect, since the
        running high is what the trail is anchored to. Uses closes rather than
        intraday highs so a single spike wick cannot pull the stop up to a
        level the stock never actually held.
        """
        close = float(bar["Close"])
        if close > position.highest_close_since_entry:
            position.highest_close_since_entry = close

        chandelier = position.highest_close_since_entry - self.trail_atr_mult * atr

        # max() enforces the ratchet: a stop never loosens, so realised risk on
        # an open trade is monotonically non-increasing.
        return max(position.stop_price, chandelier)

    def check_exit(self, position: Position, bar: pd.Series) -> Optional[Tuple[str, float]]:
        """Return ('STOP'|'TARGET', fill_price) if the bar touched a level, else None.

        Same-bar ambiguity: when one daily bar's Low <= stop and High >= target,
        OHLC does not record which was reached first. We assume the STOP filled.
        That is the conservative read — the alternative flatters every ambiguous
        bar into a win and is the single easiest way to fake a good backtest.
        """
        if float(bar["Low"]) <= position.stop_price:
            return ("STOP", position.stop_price)

        if position.target_price is not None and float(bar["High"]) >= position.target_price:
            return ("TARGET", position.target_price)

        return None
