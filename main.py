from DataProcessor import DataProcessor
from Multi_Indicator_Algorithm import Multi_Indicator_Algorithm as MIA
from RiskManagement import RiskManagement
from BacktestEngine import BacktestEngine

def main():

    processor = DataProcessor()
    strategy = MIA()
    risk = RiskManagement()

    for ticker in ['NVDA', 'TSLA', 'MSFT']:

        print('\n\n######## {} ########'.format(ticker))

        data = processor.gather_data(ticker, start_date='2021-01-01', end_date='2025-01-01')

        # Fresh engine per ticker: it stores cash and trades, so reusing one would mix results.

        engine = BacktestEngine(initial_cash=10_000)

        engine.run_backtest(data, strategy, risk)

        engine.print_metrics()

if __name__ == '__main__':

    main()
