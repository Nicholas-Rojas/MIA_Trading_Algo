import yfinance as yf
import pandas as pd
import numpy as np

from DataProcessor import DataProcessor
from Multi_Indicator_Algorithm import Multi_Indicator_Algorithm as MIA
from RiskManagement import RiskManagement

class BacktestEngine:

    def run_backtest(self, data, strategy: MIA):

        for i in range(200, len(data)):

            current_data = data.iloc[:i+1] #Current data only contains 2 days at first

            signal = strategy.generate_signal(current_data)

            if signal.type == 'BUY':

                pass
