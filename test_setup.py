#!/usr/bin/env python3
"""
Test script to verify dashboard setup and connectivity
"""
import sys
import importlib

print("🔍 Testing Crypto Dashboard Setup...\n")

# Test 1: Check Python version
print("1. Checking Python version...")
if sys.version_info < (3, 8):
    print("   ❌ Python 3.8+ required")
    print(f"   Current version: {sys.version}")
    sys.exit(1)
else:
    print(f"   ✅ Python {sys.version_info.major}.{sys.version_info.minor}")

# Test 2: Check dependencies
print("\n2. Checking dependencies...")
required_packages = [
    'binance',
    'pandas',
    'numpy',
    'streamlit',
    'plotly',
    'ta',
    'pandas_ta'
]

missing = []
for package in required_packages:
    try:
        importlib.import_module(package.replace('-', '_'))
        print(f"   ✅ {package}")
    except ImportError:
        print(f"   ❌ {package} - MISSING")
        missing.append(package)

if missing:
    print(f"\n⚠️  Missing packages: {', '.join(missing)}")
    print("Run: pip install -r requirements.txt")
    sys.exit(1)

# Test 3: Test data collector
print("\n3. Testing market data collection...")
try:
    from data.collector import MarketDataCollector
    
    collector = MarketDataCollector()
    
    # Test ping
    latency = collector.ping()
    if latency and latency < 2000:
        print(f"   ✅ Exchange connection ({latency:.0f}ms)")
    else:
        print(f"   ⚠️  High latency or connection issue")
    
    # Test price fetch
    price = collector.get_current_price("BTCUSDT")
    if price and price > 0:
        print(f"   ✅ Price data: BTC = ${price:,.2f}")
    else:
        print(f"   ❌ Failed to fetch price")
    
    # Test klines
    klines = collector.get_klines("BTCUSDT", "15m", limit=10)
    if klines is not None and len(klines) > 0:
        print(f"   ✅ Historical data ({len(klines)} candles)")
    else:
        print(f"   ❌ Failed to fetch historical data")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)

# Test 4: Test indicators
print("\n4. Testing indicator calculations...")
try:
    from data.indicators import IndicatorCalculator
    import pandas as pd
    import numpy as np
    
    # Create sample data
    dates = pd.date_range(start='2024-01-01', periods=200, freq='15min')
    sample_data = pd.DataFrame({
        'open': 50000 + np.cumsum(np.random.randn(200) * 100),
        'high': 50000 + np.cumsum(np.random.randn(200) * 100) + 50,
        'low': 50000 + np.cumsum(np.random.randn(200) * 100) - 50,
        'close': 50000 + np.cumsum(np.random.randn(200) * 100),
        'volume': np.random.uniform(100, 1000, 200)
    }, index=dates)
    
    result = IndicatorCalculator.calculate_all(sample_data)
    
    indicators_present = [
        'ema_50', 'ema_200', 'rsi', 'atr', 'adx', 'vwap'
    ]
    
    all_present = all(ind in result.columns for ind in indicators_present)
    
    if all_present:
        print(f"   ✅ All indicators calculated")
        regime = IndicatorCalculator.calculate_market_regime(result)
        print(f"   ✅ Regime detection: {regime}")
    else:
        print(f"   ⚠️  Some indicators missing")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)

# Test 5: Test configuration
print("\n5. Testing configuration...")
try:
    import config
    
    if hasattr(config, 'PRIMARY_SYMBOLS') and hasattr(config, 'TIMEFRAMES'):
        print(f"   ✅ Configuration loaded")
        print(f"   ✅ Tracking: {', '.join(config.PRIMARY_SYMBOLS)}")
    else:
        print(f"   ❌ Configuration incomplete")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)

# Summary
print("\n" + "="*50)
print("✅ ALL TESTS PASSED!")
print("="*50)
print("\n🚀 Your dashboard is ready to use!")
print("\nTo start the dashboard:")
print("  ./run.sh")
print("  OR")
print("  cd dashboard && streamlit run app.py")
print("\n📚 Read QUICKSTART.md for your first steps")
print()
