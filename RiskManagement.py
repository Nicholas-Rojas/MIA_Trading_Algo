import math

# Sets the stop-loss and take-profit for each trade, decides how many shares
# to buy, and checks each day whether the stop or target was hit.

class RiskManagement:

    def __init__(self, risk_per_trade=0.02, stop_loss_pct=0.05,
                 take_profit_pct=0.15, max_position_pct=0.25):

        self.risk_per_trade = risk_per_trade
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_position_pct = max_position_pct

    # Calculates and returns stop-price

    def get_stop_price(self, entry_price):

        return entry_price * (1 - self.stop_loss_pct)

    # Calculates and returns take-profit price

    def get_take_profit(self, entry_price):

        return entry_price * (1 + self.take_profit_pct)

    # Returns how many shares to buy. Starts from the risk rule (lose at most 2% of
    # equity if the stop hits), then caps at 25% of equity and at available cash.
    # The smallest of the three wins.

    def calculate_shares(self, equity, cash, entry_price, stop_price):

        risk_per_share = entry_price - stop_price

        if risk_per_share <= 0 or entry_price <= 0:

            return 0

        # Size so that being stopped out costs exactly risk_per_trade of equity.
        risk_dollars = equity * self.risk_per_trade
        shares_by_risk = risk_dollars / risk_per_share

        # Concentration cap: never put more than max_position_pct of the book in
        # one name, however tight the stop is.
        shares_by_exposure = (self.max_position_pct * equity) / entry_price

        # Cash cap: long only and no leverage, so the position must be fully funded.
        shares_by_cash = cash / entry_price

        shares = min(shares_by_risk, shares_by_exposure, shares_by_cash)

        # 0 is a valid answer: if the risk budget can't fund one whole share, the
        # correct action is to skip the trade, not to take more risk than allowed.
        return max(0, int(math.floor(shares)))

    # Checks today's bar against the open position's stop and target.
    # Returns ('STOP', price), ('TARGET', price), or None to stay in.

    def check_exit(self, position, bar):

        # Stop is checked first on purpose. If one daily bar touches both the stop
        # and the target, OHLC doesn't record which came first, so we assume the
        # STOP filled. That's the conservative read — assuming the target filled
        # would turn every ambiguous bar into a win and flatter the backtest.

        if bar['Low'] <= position.stop_price:

            # If the day opened below the stop (gap down), the sell fills at the open, not the stop.
            fill_price = min(position.stop_price, bar['Open'])

            return ('STOP', fill_price)

        if bar['High'] >= position.target_price:

            return ('TARGET', position.target_price)

        return None
