# Holds the details of the one open trade: shares, entry price and date,
# and the stop-loss and take-profit prices set when it was opened.

class Position:

    def __init__(self, shares, entry_price, entry_date, stop_price, target_price):

        self.shares = shares
        self.entry_price = entry_price
        self.entry_date = entry_date
        self.stop_price = stop_price
        self.target_price = target_price
