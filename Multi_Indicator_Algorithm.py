from TradeSignal import TradeSignal


# Scores three indicators each day and converts the total into a
# BUY, SELL, or HOLD signal.

class Multi_Indicator_Algorithm:

    # +40 when the 50-day SMA is above the 200-day SMA, i.e. the stock is in an
    # uptrend. Acts as the trend filter: no BUY is possible without it. 

    def check_golden_cross(self, data):

        if data['SMA_50'].iloc[-1] > data['SMA_200'].iloc[-1]:

            return 40

        return 0
    
    # +20 when today's volume is above its 50-day average, meaning more
    # market participation than usual.

    def check_VMA(self, data):

        if data['Volume'].iloc[-1] > data['VMA_50'].iloc[-1]:

            return 20
        
        return 0

    # +25 when RSI < 40: the stock has pulled back, a cheaper entry within the uptrend.

    def check_RSI(self, data):

        current_RSI = data['RSI'].iloc[-1]

        if current_RSI < 40:

            return 25

        return 0

    # Adds up the three scores (max 85). BUY needs 60+, which means the uptrend (40)
    # plus at least one confirmation: volume (20) or RSI pullback (25).
    # SELL overrides everything if the trend breaks or RSI > 70 (overbought).

    def generate_signal(self, data):

        golden_cross = self.check_golden_cross(data)
        vma = self.check_VMA(data)
        rsi = self.check_RSI(data)

        score = golden_cross + vma + rsi

        # Per-check breakdown so a signal can be audited after the fact instead of
        # being a bare number.
        conditions_met = {
            'golden_cross': golden_cross,
            'volume_above_vma50': vma,
            'rsi_below_40': rsi,
            'score': score,
        }

        # Exit first: a broken trend or an overbought reading should release the
        # position regardless of what the entry score happens to read on that bar.
        if data['SMA_50'].iloc[-1] < data['SMA_200'].iloc[-1] or data['RSI'].iloc[-1] > 70:

            return TradeSignal('SELL', score, conditions_met)

        if score >= 60:

            return TradeSignal('BUY', score, conditions_met)

        return TradeSignal('HOLD', score, conditions_met)