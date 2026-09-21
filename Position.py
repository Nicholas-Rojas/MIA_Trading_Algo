from __future__ import annotations

from typing import Optional

import pandas as pd


class Position:
    """Plain data holder for a single open long position. No behaviour."""

    def __init__(
        self,
        shares: int,
        entry_price: float,
        entry_date: pd.Timestamp,
        stop_price: float,
        target_price: Optional[float] = None,
        highest_close_since_entry: Optional[float] = None,
    ) -> None:
        """Create an open position.

        shares: whole shares held (long only, always > 0).
        entry_price: fill price actually paid, slippage included.
        entry_date: timestamp of the bar the fill occurred on.
        stop_price: current protective stop; ratchets up over the trade's life.
        target_price: static take-profit level.
        highest_close_since_entry: running max close, drives the chandelier trail.
        """
        self.shares = shares
        self.entry_price = entry_price
        self.entry_date = entry_date
        self.stop_price = stop_price
        self.target_price = target_price
        self.highest_close_since_entry = (
            highest_close_since_entry if highest_close_since_entry is not None else entry_price
        )
        # The trailing stop overwrites stop_price as the trade matures, so the
        # original risk is captured here. Without it the R multiple of a trade
        # that trailed before exiting would be computed against the wrong
        # denominator and every winner would look larger than it was.
        self.initial_stop_price = stop_price

    def __repr__(self) -> str:
        """Return a short debug representation of the position."""
        return (
            f"Position(shares={self.shares}, entry={self.entry_price:.2f}, "
            f"stop={self.stop_price:.2f}, target={self.target_price})"
        )
