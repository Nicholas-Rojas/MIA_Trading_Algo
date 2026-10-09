import yfinance as yf
import ta

# Loads in data of given TICKER and date interval
# Adds in SMAs, VMA, and RSI info to the dataset

class DataProcessor:

    # Downloads daily OHLCV data for one ticker and adds the indicator columns
    # the strategy needs. The first 199 rows have NaN for SMA_200 (not enough history).

    def gather_data(self, ticker, start_date, end_date):

        data = yf.download(ticker, start=start_date, end=end_date, auto_adjust=True)
        data.columns = data.columns.get_level_values(0)  # yfinance returns MultiIndex columns (Price, Ticker) even for one symbol; drop the ticker level

        # Get SMAs (50/200 Day Simple Moving Average)

        data['SMA_50'] = data['Close'].rolling(window=50).mean()
        data['SMA_200'] = data['Close'].rolling(window=200).mean()

        # Get VMA (Volume Moving Average)

        data['VMA_50'] = data['Volume'].rolling(window=50).mean()

        # Get RSI

        data['RSI'] = ta.momentum.rsi(data['Close'], window=14)

        return data
        