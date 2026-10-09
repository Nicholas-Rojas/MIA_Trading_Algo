# Output of the strategy for one day: the signal type ('BUY', 'SELL', 'HOLD'),
# the total score (0-85, stored as confidence), and each check's points so
# every decision can be audited.

class TradeSignal:
    def __init__(self, signal_type, confidence, conditions_met):

        self.type = signal_type
        self.confidence = confidence
        self.conditions_met = conditions_met
        