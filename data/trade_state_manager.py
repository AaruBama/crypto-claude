"""
Trade State Manager
Acts as the 'Memory' for the AI, tracking active trades and closed positions.
"""
import json
import os
from datetime import datetime

STATE_FILE = os.path.join(os.path.dirname(__file__), "storage", "trade_state.json")

class TradeStateManager:
    """
    Manages the persistence of trade state (Open/Closed trades).
    """
    
    @staticmethod
    def _load_state():
        if not os.path.exists(STATE_FILE):
            return {"active_trade": None, "history": []}
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"active_trade": None, "history": []}

    @staticmethod
    def _save_state(state):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)

    @staticmethod
    def get_active_trade():
        """Returns the active trade dictionary or None if no trade is open."""
        state = TradeStateManager._load_state()
        return state.get("active_trade")

    @staticmethod
    def start_trade(strategy_id, symbol, side, entry_price, stop_loss, take_profit):
        """
        Starts a new trade. Overwrites any existing active trade (should check first).
        """
        state = TradeStateManager._load_state()
        
        # Archive existing if any (safety check)
        if state.get("active_trade"):
            state["history"].append(state["active_trade"])
        
        new_trade = {
            "status": "OPEN",
            "strategy_id": strategy_id,
            "symbol": symbol,
            "side": side.upper(),
            "entry_price": float(entry_price),
            "start_time": datetime.utcnow().isoformat(),
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "highest_price": float(entry_price),  # For trailing stop logic
            "updates": [] # Log of AI updates
        }
        
        state["active_trade"] = new_trade
        TradeStateManager._save_state(state)
        return new_trade

    @staticmethod
    def update_trade(current_price):
        """
        Updates the current status of the active trade (PnL, High Watermark).
        Returns the updated trade object.
        """
        state = TradeStateManager._load_state()
        trade = state.get("active_trade")
        
        if not trade:
            return None
            
        current_price = float(current_price)
        entry_price = trade["entry_price"]
        
        # Calculate PnL %
        if trade["side"] == "BUY":
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            if current_price > trade.get("highest_price", 0):
                trade["highest_price"] = current_price
        else: # SELL
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
            # For short, lowest price is "highest watermark" equivalent for trailing logic, but let's stick to standard
            
        trade["current_pnl_pct"] = round(pnl_pct, 2)
        trade["last_update"] = datetime.utcnow().isoformat()
        
        TradeStateManager._save_state(state)
        return trade

    @staticmethod
    def update_stop_loss(new_sl, reason="AI Update"):
        """
        Updates the Stop Loss of the active trade.
        """
        state = TradeStateManager._load_state()
        trade = state.get("active_trade")
        
        if trade:
            old_sl = trade["stop_loss"]
            trade["stop_loss"] = float(new_sl)
            trade["updates"].append({
                "time": datetime.utcnow().isoformat(),
                "action": "UPDATE_SL",
                "old": old_sl,
                "new": new_sl,
                "reason": reason
            })
            TradeStateManager._save_state(state)
            return True
        return False

    @staticmethod
    def close_trade(exit_price, reason="Manual Close"):
        """
        Closes the active trade and moves it to history.
        """
        state = TradeStateManager._load_state()
        trade = state.get("active_trade")
        
        if trade:
            trade["status"] = "CLOSED"
            trade["exit_price"] = float(exit_price)
            trade["end_time"] = datetime.utcnow().isoformat(),
            trade["close_reason"] = reason
            
            # Final PnL
            if trade["side"] == "BUY":
                pnl_pct = ((trade["exit_price"] - trade["entry_price"]) / trade["entry_price"]) * 100
            else:
                pnl_pct = ((trade["entry_price"] - trade["exit_price"]) / trade["entry_price"]) * 100
            
            trade["final_pnl_pct"] = round(pnl_pct, 2)
            
            state["history"].insert(0, trade) # Add to top
            state["active_trade"] = None
            
            TradeStateManager._save_state(state)
            return trade
        return None
