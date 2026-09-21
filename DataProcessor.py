from __future__ import annotations

import pandas as pd
import ta
import yfinance as yf


class DataProcessor:
    """Raw OHLCV download -> indicator-enriched frame. Holds no caller state."""

    def gather_data(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        warmup_calendar_days: int = 400,
        drop_warmup: bool = True,
    ) -> pd.DataFrame:
        """Download OHLCV and attach SMA_50, SMA_200, VMA_50, RSI and ATR_14.

        Returns a DataFrame indexed by date covering [start_date, end_date),
        with indicators already warm on the first row when enough history
        exists before start_date.

        warmup_calendar_days: extra calendar history fetched *before* start_date
            purely to warm the 200-day SMA. It is trimmed off before returning,
            so it never widens the backtest window and, being strictly past
            data, introduces no lookahead.
        drop_warmup: if True, drop any leading rows where SMA_200 is still NaN
            (happens when the ticker has less history than the warmup needs).
            If False, the caller must handle the NaN warmup rows itself.
        """
        # Fetch earlier than requested so SMA_200 is defined on the first bar of
        # the actual test window. 400 calendar days is ~275 trading days, a
        # comfortable margin over the 200 bars the slowest indicator needs.
        fetch_start = (
            pd.Timestamp(start_date) - pd.Timedelta(days=warmup_calendar_days)
        ).strftime("%Y-%m-%d")

        # auto_adjust=True is explicit and load-bearing: it back-adjusts for
        # splits and dividends. On an unadjusted series a 4:1 split (AAPL, Aug
        # 2020) is a 75% overnight price drop, which drags SMA_50 through
        # SMA_200 and manufactures phantom golden/death crosses that never
        # happened economically.
        data = yf.download(
            ticker,
            start=fetch_start,
            end=end_date,
            auto_adjust=True,
            progress=False,
        )

        if data.empty:
            raise ValueError(f"No price data returned for {ticker} in the requested window.")

        # yfinance returns MultiIndex columns (Price, Ticker) even for one symbol.
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        # Get SMAs (50/200 Day Simple Moving Average)
        data["SMA_50"] = data["Close"].rolling(window=50).mean()
        data["SMA_200"] = data["Close"].rolling(window=200).mean()

        # Get VMA (Volume Moving Average)
        data["VMA_50"] = data["Volume"].rolling(window=50).mean()

        # Get RSI
        data["RSI"] = ta.momentum.rsi(data["Close"], window=14)

        # Get ATR — the volatility unit that stops and position sizes are
        # expressed in, so that a fixed dollar risk buys fewer shares of a
        # volatile name than of a quiet one.
        data["ATR_14"] = ta.volatility.average_true_range(
            high=data["High"], low=data["Low"], close=data["Close"], window=14
        )

        # Trim the warmup prefix back off: the caller asked for [start, end).
        data = data.loc[data.index >= pd.Timestamp(start_date)]

        if drop_warmup:
            data = data.dropna(subset=["SMA_200", "SMA_50", "VMA_50", "RSI", "ATR_14"])

        return data
