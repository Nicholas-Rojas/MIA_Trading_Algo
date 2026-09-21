from __future__ import annotations

import pandas as pd

from TradeSignal import TradeSignal


class Multi_Indicator_Algorithm:
    """Stateless weighted-score strategy. Frame slice in, TradeSignal out.

    Design note (this is the part that has to be defensible): a moving-average
    crossover is a *state*, not an event. Scoring it as an event means only the
    single crossover bar can ever trade, which over three years is one or two
    samples. So the crossover is demoted to a regime gate, and the thing that
    actually times entries is an RSI pullback that resolves upward.
    """

    def __init__(
        self,
        rsi_entry_level: float = 40.0,
        rsi_exit_level: float = 70.0,
        buy_threshold: float = 60.0,
        trend_strength_min: float = 0.01,
        w_pullback: float = 50.0,
        w_volume: float = 20.0,
        w_trend_strength: float = 15.0,
        w_above_sma50: float = 15.0,
    ) -> None:
        """Configure levels and component weights.

        Weights are set so the pullback trigger is necessary but not sufficient:
        every non-trigger component summed is 50, below the 60 threshold, so no
        bar can buy without the trigger, and a trigger bar still needs at least
        one confirmation to clear the bar. That is what makes the threshold
        discriminating rather than decorative.
        """
        self.rsi_entry_level = rsi_entry_level
        self.rsi_exit_level = rsi_exit_level
        self.buy_threshold = buy_threshold
        self.trend_strength_min = trend_strength_min
        self.w_pullback = w_pullback
        self.w_volume = w_volume
        self.w_trend_strength = w_trend_strength
        self.w_above_sma50 = w_above_sma50

    # ---------- regime gate ----------

    def check_regime(self, data: pd.DataFrame) -> bool:
        """Return True when SMA_50 > SMA_200, i.e. longs are permitted.

        This is a filter on *whether* we may be long, never a reason to buy.
        """
        return bool(data["SMA_50"].iloc[-1] > data["SMA_200"].iloc[-1])

    def check_death_cross(self, data: pd.DataFrame) -> bool:
        """Return True if SMA_50 crossed below SMA_200 on the current bar."""
        return bool(
            data["SMA_50"].iloc[-1] < data["SMA_200"].iloc[-1]
            and data["SMA_50"].iloc[-2] >= data["SMA_200"].iloc[-2]
        )

    # ---------- entry trigger ----------

    def check_rsi_pullback_cross(self, data: pd.DataFrame) -> float:
        """Score the RSI cross up through the entry level. Returns weight or 0.

        Previous bar below the level and current bar at or above it. Buying the
        *recovery* from an oversold dip rather than the dip itself avoids
        adding to a decline that has not yet turned.
        """
        prev_rsi = data["RSI"].iloc[-2]
        curr_rsi = data["RSI"].iloc[-1]
        if prev_rsi < self.rsi_entry_level <= curr_rsi:
            return self.w_pullback
        return 0.0

    # ---------- confirmations ----------

    def check_VMA(self, data: pd.DataFrame) -> float:
        """Score above-average volume as confirmation. Returns weight or 0.

        Confirmation only: heavy volume means the move has participation, but
        heavy volume on its own is as common in selloffs as in rallies.
        """
        if data["Volume"].iloc[-1] > data["VMA_50"].iloc[-1]:
            return self.w_volume
        return 0.0

    def check_trend_strength(self, data: pd.DataFrame) -> float:
        """Score the SMA_50/SMA_200 separation. Returns weight or 0.

        Distinguishes a decisive uptrend from two averages sitting on top of
        each other, where the regime flag is technically on but meaningless.
        """
        sma50 = data["SMA_50"].iloc[-1]
        sma200 = data["SMA_200"].iloc[-1]
        if sma200 <= 0:
            return 0.0
        if (sma50 - sma200) / sma200 >= self.trend_strength_min:
            return self.w_trend_strength
        return 0.0

    def check_price_above_sma50(self, data: pd.DataFrame) -> float:
        """Score price holding above SMA_50. Returns weight or 0.

        A pullback that never lost the intermediate trend is a shallower, and
        historically better, continuation setup than one that broke it.
        """
        if data["Close"].iloc[-1] > data["SMA_50"].iloc[-1]:
            return self.w_above_sma50
        return 0.0

    # ---------- exit ----------

    def check_exit_conditions(self, data: pd.DataFrame) -> dict:
        """Return the exit reasons true on the current bar as a flag dict."""
        return {
            "rsi_overbought": bool(data["RSI"].iloc[-1] > self.rsi_exit_level),
            "death_cross": self.check_death_cross(data),
        }

    # ---------- public API ----------

    def generate_signal(self, data: pd.DataFrame) -> TradeSignal:
        """Evaluate the last bar of `data` and return a BUY, SELL or HOLD signal.

        `data` must end at the bar being evaluated; the strategy only ever reads
        iloc[-1] and iloc[-2], so it cannot see the future. It is stateless and
        does not know whether a position is open — the engine decides which of
        BUY/SELL is actionable.
        """
        # Needs a prior bar for both cross checks.
        if len(data) < 2:
            return TradeSignal("HOLD", 0.0, {"reason": "insufficient_history"})

        required = ["SMA_50", "SMA_200", "VMA_50", "RSI", "ATR_14"]
        if data[required].iloc[-2:].isna().any().any():
            return TradeSignal("HOLD", 0.0, {"reason": "indicator_warmup"})

        # Exits are evaluated first and unconditionally: an exhausted or
        # regime-broken trade should be released on the same bar the condition
        # appears, regardless of what the entry score happens to read.
        exits = self.check_exit_conditions(data)
        if any(exits.values()):
            return TradeSignal("SELL", 100.0, {**exits, "rsi": float(data["RSI"].iloc[-1])})

        pullback = self.check_rsi_pullback_cross(data)
        volume = self.check_VMA(data)
        trend_strength = self.check_trend_strength(data)
        above_sma50 = self.check_price_above_sma50(data)
        regime_ok = self.check_regime(data)

        score = pullback + volume + trend_strength + above_sma50

        conditions = {
            "regime_sma50_above_sma200": regime_ok,
            "rsi_pullback_cross": pullback,
            "volume_above_vma50": volume,
            "trend_strength": trend_strength,
            "price_above_sma50": above_sma50,
            "score": score,
            "rsi": float(data["RSI"].iloc[-1]),
        }

        # The regime gate is absolute: a high score in a downtrend is still no.
        if regime_ok and score >= self.buy_threshold:
            return TradeSignal("BUY", score, conditions)

        return TradeSignal("HOLD", score, conditions)
