from __future__ import annotations

from typing import Optional


class TradeSignal:
    """Immutable result of one strategy evaluation on one bar."""

    def __init__(
        self,
        signal_type: str,
        confidence: float,
        conditions_met: Optional[dict] = None,
    ) -> None:
        """Store a signal.

        signal_type: one of 'BUY', 'SELL', 'HOLD'.
        confidence: weighted score for the bar (0-100 for longs).
        conditions_met: component -> score/flag breakdown, so a signal can be
            audited after the fact instead of being a bare number.
        """
        self.type = signal_type
        self.confidence = confidence
        self.conditions_met = conditions_met if conditions_met is not None else {}

    def __repr__(self) -> str:
        """Return a short debug representation of the signal."""
        return f"TradeSignal({self.type}, score={self.confidence}, {self.conditions_met})"
