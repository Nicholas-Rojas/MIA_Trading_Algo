import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from TradeSignal import TradeSignal

class Multi_Indicator_Algorithm:

    def check_golden_cross(self, data):

        if data['SMA_50'].iloc[-1] > data['SMA_200'].iloc[-1]:

            if data['SMA_50'].iloc[-2] <= data['SMA_200'].iloc[-2]: #This checks if the cross happened today

                return 40

        return 0


    def check_VMA(self, data):

        if data['Volume'].iloc[-1] > data['VMA_50'].iloc[-1]:

            return 20
        
        return 0
        

    def check_RSI(self, data):

        current_RSI = data['RSI'].iloc[-1]

        if current_RSI < 70:

            return 25

        return 0


    def generate_signal(self, data):

        score = 0

        score += self.check_golden_cross(data)
        score += self.check_VMA(data)
        score += self.check_RSI(data)

        if score >= 60:

            return TradeSignal('BUY', score, None)

        return TradeSignal('HOLD', score, None)

            





