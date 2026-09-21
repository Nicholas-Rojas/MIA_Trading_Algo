import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from DataProcessor import DataProcessor
from Multi_Indicator_Algorithm import Multi_Indicator_Algorithm as MIA
from RiskManagement import RiskManagement

def main():

    data = DataProcessor()

    data = data.gather_data('AAPL', start_date='2022-01-01', end_date='2025-01-01')

    strategy = MIA()

    signal = strategy.generate_signal(data)

    risk = RiskManagement()

    


    print(data)

main()