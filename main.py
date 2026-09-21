from __future__ import annotations

from typing import List

from BacktestEngine import BacktestEngine
from DataProcessor import DataProcessor
from Multi_Indicator_Algorithm import Multi_Indicator_Algorithm as MIA
from RiskManagement import RiskManagement

# All universe/window configuration lives here, never inside the classes.
TICKERS: List[str] = ["AAPL", "MSFT", "NVDA", "TSLA"]
START_DATE = "2022-01-01"
END_DATE = "2025-01-01"
INITIAL_CASH = 10_000.0


def run_one(ticker: str, show_plots: bool = False) -> dict:
    """Run the full pipeline for one ticker and return its results dict."""
    # `processor` and `data` are separate names: the original code rebound the
    # DataProcessor instance to its own return value, which worked only because
    # the instance was never needed again.
    processor = DataProcessor()
    data = processor.gather_data(ticker, start_date=START_DATE, end_date=END_DATE)

    strategy = MIA()
    risk = RiskManagement(risk_per_trade=0.02)
    engine = BacktestEngine(initial_cash=INITIAL_CASH, slippage_bps=5, commission=1.0)

    engine.run_backtest(data, strategy, risk, ticker=ticker)
    engine.print_metrics()
    engine.print_trade_log()
    engine.plot_equity_curve(save_path=f"equity_{ticker}.png", show=show_plots)

    return engine.results


def main() -> None:
    """Backtest every configured ticker over the configured window."""
    for ticker in TICKERS:
        run_one(ticker)


if __name__ == "__main__":
    main()
