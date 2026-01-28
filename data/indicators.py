
"""
Technical Indicators Calculator
"""
import pandas as pd
import numpy as np
import ta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

class IndicatorCalculator:
    """Calculate all technical indicators for the dashboard"""
    
    @staticmethod
    def calculate_all(df):
        """
        Calculate all indicators on a dataframe with OHLCV data
        
        Args:
            df: DataFrame with columns [open, high, low, close, volume]
        
        Returns:
            DataFrame with all indicators added
        """
        if df is None or len(df) < 50:
            return df
        
        df = df.copy()
        
        # Moving Averages using ta library
        df['ema_50'] = ta.trend.ema_indicator(df['close'], window=config.INDICATORS['ema_short'])
        df['ema_200'] = ta.trend.ema_indicator(df['close'], window=config.INDICATORS['ema_long'])
        
        # RSI
        df['rsi'] = ta.momentum.rsi(df['close'], window=config.INDICATORS['rsi_period'])
        
        # ATR (Average True Range - volatility)
        df['atr'] = ta.volatility.average_true_range(
            df['high'], df['low'], df['close'], 
            window=config.INDICATORS['atr_period']
        )
        
        # ADX (trend strength)
        df['adx'] = ta.trend.adx(df['high'], df['low'], df['close'], window=config.INDICATORS['adx_period'])
        df['dmp'] = ta.trend.adx_pos(df['high'], df['low'], df['close'], window=config.INDICATORS['adx_period'])
        df['dmn'] = ta.trend.adx_neg(df['high'], df['low'], df['close'], window=config.INDICATORS['adx_period'])
        
        # Bollinger Bands
        bollinger = ta.volatility.BollingerBands(
            df['close'], 
            window=config.INDICATORS['bollinger_period'],
            window_dev=config.INDICATORS['bollinger_std']
        )
        df['bb_upper'] = bollinger.bollinger_hband()
        df['bb_middle'] = bollinger.bollinger_mavg()
        df['bb_lower'] = bollinger.bollinger_lband()
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle'] * 100
        
        # Volume indicators
        df['volume_ma'] = df['volume'].rolling(window=config.INDICATORS['volume_ma_period']).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # VWAP (Volume Weighted Average Price)
        df = IndicatorCalculator._calculate_vwap(df)
        
        # Price distance from VWAP
        df['vwap_distance_pct'] = ((df['close'] - df['vwap']) / df['vwap']) * 100
        
        # Z-score (for mean reversion)
        df['z_score'] = IndicatorCalculator._calculate_zscore(df['close'], window=20)
        
        # Range metrics
        df['daily_range_pct'] = ((df['high'] - df['low']) / df['close']) * 100
        
        # Wick analysis
        df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']
        df['body'] = abs(df['close'] - df['open'])
        df['wick_ratio'] = (df['upper_wick'] + df['lower_wick']) / (df['body'] + 0.0001)
        
        return df
    
    @staticmethod
    def _calculate_vwap(df):
        """Calculate VWAP (Volume Weighted Average Price)"""
        df = df.copy()
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['vwap_sum'] = (df['typical_price'] * df['volume']).cumsum()
        df['volume_sum'] = df['volume'].cumsum()
        df['vwap'] = df['vwap_sum'] / df['volume_sum']
        df.drop(['typical_price', 'vwap_sum', 'volume_sum'], axis=1, inplace=True)
        return df
    
    @staticmethod
    def _calculate_zscore(series, window=20):
        """Calculate rolling z-score"""
        rolling_mean = series.rolling(window=window).mean()
        rolling_std = series.rolling(window=window).std()
        z_score = (series - rolling_mean) / rolling_std
        return z_score
    
    @staticmethod
    def calculate_market_regime(df):
        """Determine market regime: Trending, Ranging, or Volatile"""
        if df is None or len(df) < 50:
            return 'unknown'
        
        latest = df.iloc[-1]
        adx = latest.get('adx', 0)
        atr_percentile = (df['atr'].rank(pct=True).iloc[-1]) * 100
        recent_high = df['high'].tail(20).max()
        recent_low = df['low'].tail(20).min()
        range_pct = ((recent_high - recent_low) / latest['close']) * 100
        
        if atr_percentile > config.REGIME_THRESHOLDS['atr_high_percentile']:
            return 'volatile'
        elif adx > config.REGIME_THRESHOLDS['adx_trending']:
            return 'trending'
        else:
            return 'ranging'
    
    @staticmethod
    def calculate_trend_direction(df):
        """Determine trend direction: up, down, or neutral"""
        if df is None or len(df) < 50:
            return 'neutral'
        
        latest = df.iloc[-1]
        ema_50 = latest.get('ema_50', 0)
        ema_200 = latest.get('ema_200', 0)
        price = latest['close']
        dmp = latest.get('dmp', 0)
        dmn = latest.get('dmn', 0)
        
        if price > ema_50 > ema_200 and dmp > dmn:
            return 'up'
        elif price < ema_50 < ema_200 and dmn > dmp:
            return 'down'
        else:
            return 'neutral'
    
    @staticmethod
    def detect_volume_spike(df):
        """Detect if current volume is abnormally high"""
        if df is None or len(df) < 20:
            return False, 0
        
        latest = df.iloc[-1]
        volume_ratio = latest.get('volume_ratio', 1)
        is_spike = volume_ratio > config.ALERTS['volume_spike_multiplier']
        return is_spike, volume_ratio
    
    @staticmethod
    def check_price_stretch(df):
        """Check if price is stretched from VWAP"""
        if df is None or len(df) < 1:
            return False, 0
        
        latest = df.iloc[-1]
        vwap_distance = abs(latest.get('vwap_distance_pct', 0))
        is_stretched = vwap_distance > config.ALERTS['price_stretch_percent']
        return is_stretched, vwap_distance
    
    @staticmethod
    def get_support_resistance(df, window=20):
        """Identify key support and resistance levels"""
        if df is None or len(df) < window:
            return []
        
        recent = df.tail(window)
        resistance_levels = []
        support_levels = []
        
        for i in range(1, len(recent) - 1):
            if recent.iloc[i]['high'] > recent.iloc[i-1]['high'] and recent.iloc[i]['high'] > recent.iloc[i+1]['high']:
                resistance_levels.append(recent.iloc[i]['high'])
            
            if recent.iloc[i]['low'] < recent.iloc[i-1]['low'] and recent.iloc[i]['low'] < recent.iloc[i+1]['low']:
                support_levels.append(recent.iloc[i]['low'])
        
        return {
            'support': sorted(support_levels)[-3:] if support_levels else [],
            'resistance': sorted(resistance_levels, reverse=True)[:3] if resistance_levels else []
        }
    
    @staticmethod
    def calculate_session_levels(df):
        """Calculate session open/high/low levels"""
        if df is None or len(df) < 1:
            return {}
        
        yesterday = df.tail(96).head(96) if len(df) >= 96 else df
        
        return {
            'prev_high': yesterday['high'].max(),
            'prev_low': yesterday['low'].min(),
            'prev_close': yesterday['close'].iloc[-1] if len(yesterday) > 0 else df['close'].iloc[-1]
        }