
"""
CONNECTIVITY AUDIT UTILITY
1. Timestamp Sync: Checks drift between local clock and Binance server.
2. API Permissions: Verifies trading is enabled and withdrawals are disabled.
"""
import sys
import os
import ccxt
import time
from datetime import datetime

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from trading_engine.config import API_KEY, API_SECRET

def run_audit():
    print("🔍 RUNNING CONNECTIVITY AUDIT...\n")
    
    if not API_KEY or not API_SECRET:
        print("❌ FAILED: API Credentials missing in .env")
        return

    exchange = ccxt.binance({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit': True,
    })

    # 1. TIMESTAMP SYNC CHECK
    print("--- [1/4] Timestamp Sync Check ---")
    try:
        local_time_ms = int(time.time() * 1000)
        server_time_ms = exchange.fetch_time()
        drift = server_time_ms - local_time_ms
        
        print(f"Local Time:  {local_time_ms}")
        print(f"Server Time: {server_time_ms}")
        print(f"Drift:       {drift}ms")
        
        if abs(drift) < 500:
            print("✅ SUCCESS: Clock is synchronized (Drift < 500ms)")
        else:
            print(f"⚠️ WARNING: Clock drift is {drift}ms. Binance may reject orders.")
            print("Action: Sync your MacOS clock with Apple Time server.")
    except Exception as e:
        print(f"❌ ERROR Checking Time: {e}")

    # 2. API PERMISSION VERIFICATION
    print("\n--- [2/4] API Permission Verification ---")
    try:
        # fetch_api_key_permissions is not available for all exchanges in ccxt, 
        # but for Binance we can check via fetch_balance and fetch_my_trades
        # and looking at exchange.api['get']['account']['permissions']
        # Or more simply, fetch account info
        account_info = exchange.fetch_balance() # This requires 'spot' or 'margin' read
        
        # CCXT abstracts some info, but we can look at the raw response for permissions
        # On Binance, fetch_balance response has 'info' key with raw response
        raw_info = account_info.get('info', {})
        permissions = raw_info.get('permissions', [])
        
        print(f"Account Permissions: {permissions}")
        
        is_spot = "SPOT" in permissions
        is_margin = "MARGIN" in permissions
        
        # For actual specific flags like "enableWithdrawals", we can hit the private account snapshot or specific endpoints
        # Let's use get_api_key_permission if supported or raw
        try:
            # Try binance specific endpoint if needed
            ext_info = exchange.sapi_get_account_apirestrictions()
            print(f"API Restrictions: {ext_info}")
            
            can_trade = ext_info.get('enableSpotAndMarginTrading', False)
            can_withdraw = ext_info.get('enableWithdrawals', False)
            
            if can_trade:
                print("✅ SUCCESS: Spot Trading Enabled.")
            else:
                print("❌ FAILED: Spot Trading is DISABLED.")
                
            if not can_withdraw:
                print("✅ SUCCESS: Withdrawals are DISABLED (Secure).")
            else:
                print("⚠️ SECURITY WARNING: Withdrawals are ENABLED. Disable them on Binance for safety.")
        except Exception as api_err:
             print(f"ℹ️ Could not fetch specific restrictions (maybe API key lacks permission for this info).")
             print(f"Fallback: Basic info check...")
             if is_spot:
                 print("✅ Basic Verification: Spot account access detected.")
             else:
                 print("❌ Basic Verification: Spot account access NOT detected.")

    except Exception as e:
        print(f"❌ FAILED: Could not access account info. Check API Key/Secret. {e}")

    # 3. ASSET & DUST AUDIT
    print("\n--- [3/4] Asset & Dust Audit ---")
    try:
        balance = exchange.fetch_balance()
        usdt_total = balance.get('USDT', {}).get('total', 0.0)
        btc_total = balance.get('BTC', {}).get('total', 0.0)
        bnb_total = balance.get('BNB', {}).get('total', 0.0)

        print(f"💰 USDT Balance: {usdt_total:.2f}")
        print(f"₿ BTC Balance:  {btc_total:.8f}")
        print(f"🟡 BNB Balance:  {bnb_total:.4f}")

        # Validation Logic
        if usdt_total < 10.0 and btc_total == 0:
            print("❌ WARNING: Insufficient USDT for the $100 Micro-Limit.")
        
        if bnb_total == 0:
            print("⚠️ WARNING: No BNB detected. You will pay 25% HIGHER fees.")
        else:
            print("✅ SUCCESS: BNB detected for fee discounts.")

    except Exception as e:
        print(f"❌ FAILED to fetch balances: {e}")

    print("\nAudit Complete.")

if __name__ == "__main__":
    run_audit()
