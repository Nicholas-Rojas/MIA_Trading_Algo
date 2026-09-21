import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

class TradeSignal:
    def __init__(self, signal_type, confidence, conditions_met):

        self.type = signal_type
        self.confidence = confidence
        self.conditions_met = conditions_met


