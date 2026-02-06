import pytest
import os
import json
from data.wallet import PaperWallet

@pytest.fixture
def test_wallet():
    """Fixture to provide a fresh wallet for each test"""
    filename = "test_wallet_tmp.json"
    # Ensure starting fresh
    if os.path.exists(f"data/{filename}"):
        os.remove(f"data/{filename}")
        
    wallet = PaperWallet(filename=filename)
    # Set a clean starting balance for tests
    wallet.data["initial_balance"] = 10000.0
    wallet.data["balance_usd"] = 10000.0
    wallet.data["positions"] = {}
    wallet.data["history"] = []
    wallet._save_wallet()
    
    yield wallet
    
    # Cleanup after test
    if os.path.exists(wallet.filepath):
        os.remove(wallet.filepath)

def test_initial_balance(test_wallet):
    """Verify the starting capital is correct"""
    assert test_wallet.get_balance() == 10000.0
    assert test_wallet.data["initial_balance"] == 10000.0

def test_basic_buy(test_wallet):
    """Scenario: Buy BTC at fixed price"""
    success, msg = test_wallet.buy("BTCUSDT", 50000.0, 0.1)
    assert success is True
    assert test_wallet.get_position("BTCUSDT") == 0.1
    assert test_wallet.get_balance() == 5000.0 # 10000 - (0.1 * 50000)

def test_average_price_calculation(test_wallet):
    """Scenario: Multi-stage entry for Average Price check"""
    test_wallet.buy("BTCUSDT", 40000.0, 0.1) # Cost 4000
    test_wallet.buy("BTCUSDT", 60000.0, 0.1) # Cost 6000
    # Total cost 10000 for 0.2 BTC = Avg 50000.0
    pos = test_wallet.data["positions"]["BTCUSDT"]
    assert pos["avg_price"] == 50000.0
    assert pos["amount"] == 0.2

def test_short_selling(test_wallet):
    """Scenario: Open a short position"""
    success, msg = test_wallet.sell("BTCUSDT", 50000.0, 0.1)
    assert success is True
    assert test_wallet.get_position("BTCUSDT") == -0.1
    assert test_wallet.get_balance() == 15000.0 # 10000 + 5000

def test_static_stop_loss_trigger(test_wallet):
    """Scenario: Price hits Stop Loss (Long)"""
    test_wallet.buy("BTCUSDT", 50000.0, 0.1)
    test_wallet.data["positions"]["BTCUSDT"]["stop_loss"] = 49000.0
    
    # Price drops to 48500
    msg = test_wallet.check_automated_orders("BTCUSDT", 48500.0)
    assert "Stop Loss Triggered" in msg
    assert test_wallet.get_position("BTCUSDT") == 0.0
    assert test_wallet.get_balance() == 9850.0 # 5000 (remaining) + (0.1 * 48500)

def test_trailing_stop_loss_long(test_wallet):
    """Scenario: Trailing Stop follows price up then triggers"""
    test_wallet.buy("BTCUSDT", 50000.0, 0.1)
    test_wallet.data["positions"]["BTCUSDT"]["trailing_stop_percent"] = 2.0
    
    # Price goes to 60000 (trailing high updates)
    test_wallet.check_automated_orders("BTCUSDT", 60000.0)
    assert test_wallet.data["positions"]["BTCUSDT"]["highest_price"] == 60000.0
    
    # Exit price is now 60000 * 0.98 = 58800
    # Price drops to 58000
    msg = test_wallet.check_automated_orders("BTCUSDT", 58000.0)
    assert "Trailing Stop Triggered" in msg
    assert test_wallet.get_position("BTCUSDT") == 0.0
    assert test_wallet.get_balance() == 10800.0 # 5000 + (0.1 * 58000)

def test_scaling_out(test_wallet):
    """Scenario: Price hits first scaling target"""
    test_wallet.buy("BTCUSDT", 50000.0, 0.2) # Buy 0.2
    test_wallet.data["positions"]["BTCUSDT"]["scaling_targets"] = [55000.0, 60000.0]
    
    # Price hits 56000 (Target 1)
    msg = test_wallet.check_automated_orders("BTCUSDT", 56000.0)
    assert "Scaled out 50%" in msg
    assert test_wallet.get_position("BTCUSDT") == 0.1 # Half sold
    assert 55000.0 not in test_wallet.data["positions"]["BTCUSDT"]["scaling_targets"]

def test_price_sanitization(test_wallet):
    """Scenario: Input contains $, commas and spaces"""
    strategy = {
        "action": "BUY",
        "trade_params": {
            "symbol": "BTC/USDT",
            "entry_price": " $64,000.50 ",
            "stop_loss": "$60,000"
        }
    }
    # We need to set balance high enough because execute_strategy trades 10%
    test_wallet.data["balance_usd"] = 100000.0 
    
    success, msg = test_wallet.execute_strategy(strategy)
    assert success is True
    pos = test_wallet.data["positions"]["BTCUSDT"]
    assert pos["avg_price"] == pytest.approx(64000.50)
    assert pos["stop_loss"] == pytest.approx(60000.0)

def test_insufficient_balance(test_wallet):
    """Scenario: Trying to buy more than we have cash for"""
    test_wallet.data["balance_usd"] = 100.0
    success, msg = test_wallet.buy("BTCUSDT", 50000.0, 1.0) # Costs 50000
    assert success is False
    assert "Insufficient balance" in msg

def test_dust_cleanup(test_wallet):
    """Scenario: Total position close should force 0.0 amount"""
    test_wallet.buy("BTCUSDT", 50000.0, 0.00000001)
    test_wallet.close_position("BTCUSDT", 50000.0)
    assert test_wallet.data["positions"]["BTCUSDT"]["amount"] == 0.0
