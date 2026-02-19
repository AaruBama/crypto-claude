"""
Strategy Router & Injection Engine
"""
import pandas as pd
from data.indicators import IndicatorCalculator
import config
from data.trade_state_manager import TradeStateManager

class StrategyRouter:
    """
    Decides which strategy to inject into the AI prompt based on market regime.
    Treats the AI as a Modular Decision Engine.
    """
    
    @staticmethod
    def get_market_regime(df):
        """
        Determine the current market regime (Trending, Ranging, Volatile)
        """
        # We can reuse the IndicatorCalculator logic or enhance it here
        return IndicatorCalculator.calculate_market_regime(df)

    @staticmethod
    def _get_primary_strategy(df, regime):
        """
        Selects the best strategy based on market conditions (ADX, Volatility).
        Returns: (strategy_key, reason) or (None, reason)
        """
        # Default to None
        latest = df.iloc[-1]
        adx = latest.get('adx', 0)
        atr_pct = (df['atr'].rank(pct=True).iloc[-1]) * 100
        
        # 1. High Volatility Squeeze -> BB Breakout
        # If bb_width is low (squeeze) and sudden move -> Breakout
        if latest.get('bb_width', 100) < 5 and regime == 'volatile':
            return "BB_BREAKOUT", "Volatility Squeeze Detected (Breakout Imminent)"

        # 2. Strong Trend -> 9-20 EMA or Golden Cross
        if regime == "trending":
            if adx > 40:
                return "9_20_EMA", "Strong Trend (High Momentum)"
            else:
                return "8_30_EMA", "Stable Trend (Trend Riding)"
            
        # 3. Ranging / Sideways -> Bollinger + RSI Scalper
        if regime == "ranging":
            rsi = latest.get('rsi', 50)
            if rsi < 35 or rsi > 65:
                return "MEAN_REVERSION", "Mean Reversion Opportunity: Price hitting BB extremes with RSI confirmation."
            else:
                 # If RSI is neutral in range, maybe look for VWAP mean reversion?
                return "VWAP_PULLBACK", "Ranging around Fair Value (VWAP)"
                
        # 4. Volatile but not squeeze -> 9-20 Scalp
        if regime == "volatile":
            return "9_20_EMA", "High Volatility Scalping"

        return None, "Market condition unclear"

    @staticmethod
    def get_strategy_context(df):
        """
        Generates the dynamic context block for the AI prompt.
        Handles both 'Hunt Mode' (looking for entries) and 'Management Mode' (managing active trades).
        """
        if df is None or len(df) < 50:
            return "Market data insufficient for strategy analysis."
            
        # 🟢 CHECK ACTIVE TRADE STATE (Persistence Layer)
        active_trade = TradeStateManager.get_active_trade()
        
        if active_trade and active_trade.get("status") == "OPEN":
            # --- MANAGEMENT MODE ---
            latest_price = df.iloc[-1]['close']
            entry_price = active_trade['entry_price']
            side = active_trade['side']
            
            # Calculate current PnL
            if side == "BUY":
                pnl_pct = ((latest_price - entry_price) / entry_price) * 100
            else:
                pnl_pct = ((entry_price - latest_price) / entry_price) * 100
                
            strat_name = config.STRATEGIES.get(active_trade['strategy_id'], {}).get('name', 'Unknown Strategy')
            
            lines = []
            lines.append(f"### 🛡️ ACTIVE TRADE MANAGEMENT MODE")
            lines.append(f"**Strategy:** {strat_name} ({side})")
            lines.append(f"**Entry:** ${entry_price:,.2f} | **Current:** ${latest_price:,.2f}")
            lines.append(f"**PnL:** {pnl_pct:+.2f}%")
            lines.append(f"**Stop Loss:** ${active_trade.get('stop_loss', 0):,.2f}")
            lines.append(f"**Take Profit:** ${active_trade.get('take_profit', 0):,.2f}")
            
            lines.append("\n**YOUR TASK (Proprietary AI Manager):**")
            lines.append("1. Analyze the current price action against the open trade.")
            lines.append("2. Advise on the specific action: HOLD, CLOSE NOW (Take Profit), or CLOSE NOW (Stop Loss).")
            lines.append("3. If holding, suggest if we should TIGHTEN the Stop Loss to lock in profits.")
            
            return "\n".join(lines)
            
        # --- HUNT MODE (Default) ---
        regime = StrategyRouter.get_market_regime(df)
        signals = IndicatorCalculator.detect_all_signals(df)
        
        # 1. Determine Primary Strategy for this Regime
        primary_key, primary_reason = StrategyRouter._get_primary_strategy(df, regime)
        
        # Build the injected text
        lines = []
        lines.append(f"### 🧠 DYNAMIC STRATEGY INJECTION")
        lines.append(f"**Status:** NO ACTIVE TRADES (Scanning Mode)")
        lines.append(f"**Detected Market Regime:** {regime.upper()} (ADX: {round(df.iloc[-1].get('adx', 0), 1)})")
        
        if primary_key and primary_key in config.STRATEGIES:
            strat = config.STRATEGIES[primary_key]
            lines.append(f"**🎯 PRIMARY STRATEGY:** {strat['name']}")
            lines.append(f"**Reason:** {primary_reason}")
            lines.append(f"**Logic:** {strat['logic']}")
        else:
            lines.append(f"**🎯 PRIMARY STRATEGY:** WAIT / OBSERVATION")
            lines.append(f"**Reason:** {primary_reason}")
            
        # 2. Add Active Signals (Confidence Tiers)
        lines.append("\n**🔎 SIGNAL CHECK:**")
        
        active_signals = []
        for key, signal_obj in signals.items():
            if signal_obj.get("signal") in ["bullish", "bearish"]:
                strat_name = config.STRATEGIES.get(key, {}).get("name", key)
                time_ago = signal_obj.get('time_ago', 'N/A')
                desc = signal_obj.get('description', '')
                active_signals.append(f"- {strat_name}: {signal_obj['signal'].upper()} ({time_ago}) - {desc}")
        
        if active_signals:
            lines.append("The following strategies have active signals:")
            lines.extend(active_signals)
            
            # Confidence Logic
            if len(active_signals) >= 2:
                 lines.append("✨ **HIGH CONFIDENCE:** Multiple strategies are aligned!")
        else:
            lines.append("No active crossover signals detected at this moment.")
            
        return "\n".join(lines)

    @staticmethod
    def get_strategy_status_for_ui(df):
        """
        Returns a list of dicts for the UI Signals Panel
        """
        if df is None: 
            return []
            
        signals = IndicatorCalculator.detect_all_signals(df)
        status_list = []
        
        for key, strat in config.STRATEGIES.items():
            signal_obj = signals.get(key, {})
            
            # Basic formatting
            item = {
                "id": strat['id'],
                "name": strat['name'],
                "description": strat['description'],
                "logic": strat['logic'],
                "signal": signal_obj.get("signal", "neutral"),
                "time_ago": signal_obj.get("time_ago", "N/A"),
                "value": signal_obj.get("value", 0),
                "threshold": signal_obj.get("threshold", 0)
            }
            status_list.append(item)
            
        return status_list
