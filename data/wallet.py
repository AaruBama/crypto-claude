import json
import os
from datetime import datetime

class PaperWallet:
    """A smarter mock engine for paper trading with automated profit booking"""
    
    def __init__(self, filename="paper_wallet.json"):
        self.filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", filename)
        self.data = self._load_wallet()

    def _load_wallet(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    data = json.load(f)
                    # Migrating schema if needed
                    if "positions" in data:
                        for sym in data["positions"]:
                            pos = data["positions"][sym]
                            if "highest_price" not in pos: pos["highest_price"] = pos.get("avg_price", 0)
                            if "lowest_price" not in pos: pos["lowest_price"] = pos.get("avg_price", 0)
                            if "take_profit" not in pos: pos["take_profit"] = None
                            if "stop_loss" not in pos: pos["stop_loss"] = None
                            if "trailing_stop_percent" not in pos: pos["trailing_stop_percent"] = None
                            if "scaling_targets" not in pos: pos["scaling_targets"] = []
                    
                    # Migration for existing wallets missing initial_balance
                    if "initial_balance" not in data:
                        data["initial_balance"] = data.get("balance_usd", 10000.0)
                        self._save_wallet(data) # Save the migrated data
                    
                    return data
            except:
                pass
        
        # Default starting state
        default_data = {
            "initial_balance": 10000.0,
            "balance_usd": 10000.0,
            "positions": {}, 
            "history": []   
        }
        self._save_wallet(default_data)
        return default_data

    def _save_wallet(self, data=None):
        if data is None: data = self.data
        with open(self.filepath, 'w') as f:
            json.dump(data, f, indent=4)

    def get_balance(self): return self.data["balance_usd"]

    def get_position(self, symbol):
        clean_symbol = symbol.replace('/', '')
        return self.data["positions"].get(clean_symbol, {"amount": 0.0})["amount"]

    def _sanitize_price(self, price_val):
        """Helper to convert string prices like '$76,877.00' to float"""
        if isinstance(price_val, (int, float)):
            return float(price_val)
        if isinstance(price_val, str):
            try:
                # Remove $, commas, and whitespace
                clean = price_val.replace('$', '').replace(',', '').strip()
                return float(clean)
            except:
                return 0.0
        return 0.0

    def execute_strategy(self, strategy, override_usd=None):
        """Executes a strategy and attaches automated orders"""
        action_raw = str(strategy.get('action', 'WAIT')).upper()
        params = strategy.get('trade_params', {})
        symbol = params.get('symbol', 'BTCUSDT').replace('/', '')
        
        # Sanitize prices (AI sometimes outputs strings with $ or commas)
        price = self._sanitize_price(params.get('entry_price', 0))
        
        if price <= 0: 
            return False, f"Invalid entry price: {params.get('entry_price')}. Please ensure it is a positive number."

        balance = self.get_balance()
        if balance <= 0:
            return False, f"Insufficient account balance (${balance:,.2f}) to open a trade."

        # Use override amount if provided, otherwise default to 10%
        usd_amount = override_usd if override_usd is not None else (balance * 0.1)
        
        if usd_amount > balance and "BUY" in action_raw:
             return False, f"Not enough balance (${balance:,.2f}) for a ${usd_amount:,.2f} trade."

        amount = usd_amount / price

        success, msg = False, f"Action '{action_raw}' not recognized. Use BUY or SELL."
        
        if "BUY" in action_raw:
            success, msg = self.buy(symbol, price, amount)
        elif "SELL" in action_raw:
            success, msg = self.sell(symbol, price, amount)
        
        if success:
            # Attach automated params to the position
            if symbol in self.data["positions"]:
                pos = self.data["positions"][symbol]
                pos["stop_loss"] = self._sanitize_price(params.get("stop_loss")) or None
                pos["take_profit"] = self._sanitize_price(params.get("take_profit")) or None
                pos["trailing_stop_percent"] = float(params.get("trailing_stop_percent") or 0) or None
                
                # Sanitize scaling targets
                raw_targets = params.get("scaling_targets", [])
                if isinstance(raw_targets, list):
                    pos["scaling_targets"] = [self._sanitize_price(t) for t in raw_targets if self._sanitize_price(t) > 0]
                else:
                    pos["scaling_targets"] = []
                    
                self._save_wallet()
            
        return success, msg

    def buy(self, symbol, price, amount):
        usd_value = amount * price
        
        # If position doesn't exist or was closed, initialize with fresh price tracking
        is_new_pos = False
        if symbol not in self.data["positions"] or abs(self.data["positions"][symbol].get("amount", 0)) < 1e-8:
            is_new_pos = True
            pos = {"amount": 0.0, "avg_price": 0.0, "highest_price": price, "lowest_price": price}
        else:
            pos = self.data["positions"][symbol]
        
        if pos["amount"] >= 0 and usd_value > self.data["balance_usd"]:
            return False, "Insufficient balance"

        self.data["balance_usd"] -= usd_value
        
        if pos["amount"] >= 0:
            total_amount = pos["amount"] + amount
            pos["avg_price"] = ((pos["amount"] * pos["avg_price"]) + (amount * price)) / total_amount
            pos["amount"] = total_amount
            # Reset/Sync high price for trailing stop
            pos["highest_price"] = max(pos.get("highest_price", price), price) if not is_new_pos else price
        else:
            # Closing a short
            pos["amount"] += amount
        
        self.data["positions"][symbol] = pos
        self._record_trade(symbol, "BUY", price, amount, usd_value)
        return True, f"Bought {amount:.6f} {symbol}"

    def sell(self, symbol, price, amount):
        usd_value = amount * price
        
        # If position doesn't exist or was closed, initialize with fresh price tracking
        is_new_pos = False
        if symbol not in self.data["positions"] or abs(self.data["positions"][symbol].get("amount", 0)) < 1e-8:
            is_new_pos = True
            pos = {"amount": 0.0, "avg_price": 0.0, "highest_price": price, "lowest_price": price}
        else:
            pos = self.data["positions"][symbol]

        self.data["balance_usd"] += usd_value
        
        if pos["amount"] <= 0:
            total_amount = pos["amount"] - amount # increasing short
            pos["avg_price"] = ((abs(pos["amount"]) * pos["avg_price"]) + (amount * price)) / abs(total_amount)
            pos["amount"] = total_amount
            # Reset/Sync low price for trailing stop
            pos["lowest_price"] = min(pos.get("lowest_price", price), price) if not is_new_pos else price
        else:
            # Closing a long
            pos["amount"] -= amount
        
        self.data["positions"][symbol] = pos
        self._record_trade(symbol, "SELL", price, amount, usd_value)
        return True, f"Sold {amount:.6f} {symbol}"

    def check_automated_orders(self, symbol, current_price):
        """The 'Heartbeat' - Checks if any TP/SL/TSL needs to trigger"""
        pos = self.data["positions"].get(symbol)
        if not pos or abs(pos["amount"]) < 1e-8: return None

        amount = pos["amount"]
        
        # 1. Update Trailing Highs/Lows
        if amount > 0: pos["highest_price"] = max(pos.get("highest_price", 0), current_price)
        else: pos["lowest_price"] = min(pos.get("lowest_price", 999999), current_price)

        # 2. Check Static Stop Loss
        sl = pos.get("stop_loss")
        if sl:
            if (amount > 0 and current_price <= sl) or (amount < 0 and current_price >= sl):
                self.close_position(symbol, current_price)
                return f"🚨 Stop Loss Triggered at ${current_price:,.2f}"

        # 3. Check Static Take Profit
        tp = pos.get("take_profit")
        if tp:
            if (amount > 0 and current_price >= tp) or (amount < 0 and current_price <= tp):
                self.close_position(symbol, current_price)
                return f"🎯 Take Profit Hit at ${current_price:,.2f}"

        # 4. Check Trailing Stop
        tsl_pct = pos.get("trailing_stop_percent")
        if tsl_pct:
            if amount > 0: # Long
                exit_price = pos["highest_price"] * (1 - tsl_pct/100)
                if current_price <= exit_price:
                    self.close_position(symbol, current_price)
                    return f"📈 Trailing Stop Triggered at ${current_price:,.2f}"
            else: # Short
                exit_price = pos["lowest_price"] * (1 + tsl_pct/100)
                if current_price >= exit_price:
                    self.close_position(symbol, current_price)
                    return f"📉 Trailing Stop Triggered at ${current_price:,.2f}"

        # 5. Check Scaling Out
        targets = pos.get("scaling_targets", [])
        if targets:
            for target in targets:
                if (amount > 0 and current_price >= target) or (amount < 0 and current_price <= target):
                    # Sell 50% of REMAINING position
                    sell_amount = abs(amount) * 0.5
                    if amount > 0: self.sell(symbol, current_price, sell_amount)
                    else: self.buy(symbol, current_price, sell_amount)
                    pos["scaling_targets"].remove(target) # Remove this target
                    self._save_wallet()
                    return f"💰 Scaled out 50% at ${current_price:,.2f}"

        self._save_wallet()
        return None

    def close_position(self, symbol, current_price):
        amount = self.data["positions"][symbol]["amount"]
        result = None
        if amount > 0: 
            result = self.sell(symbol, current_price, amount)
        else: 
            result = self.buy(symbol, current_price, abs(amount))
            
        # Clear params
        if symbol in self.data["positions"]:
            self.data["positions"][symbol].update({
                "stop_loss": None, 
                "take_profit": None, 
                "trailing_stop_percent": None, 
                "scaling_targets": [],
                "amount": 0.0 # Force zero to avoid dust
            })
        self._save_wallet()
        return result

    def _record_trade(self, symbol, t_type, price, amount, usd_value):
        trade = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "pair": symbol, "type": t_type, 
                  "price": price, "amount": float(f"{amount:.8f}"), "total_usd": float(f"{usd_value:.2f}")}
        self.data["history"].append(trade)
        self._save_wallet()

    def get_history(self): return self.data["history"]
