"""
Crypto Trading Dashboard - Main Application
Built with your mental model in mind
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.collector import MarketDataCollector
from data.indicators import IndicatorCalculator
from data.demo_data import get_demo_collector
import config

# Try to use real data, fall back to demo if network unavailable
USE_DEMO_MODE = False

def get_collector():
    """Get data collector - real or demo"""
    global USE_DEMO_MODE
    if USE_DEMO_MODE:
        return None  # We'll use demo generators per-symbol
    return MarketDataCollector()

# Page config
st.set_page_config(
    page_title="Crypto Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-metric {
        font-size: 24px;
        font-weight: bold;
    }
    .regime-trending {
        color: #00ff00;
        font-weight: bold;
    }
    .regime-ranging {
        color: #ffaa00;
        font-weight: bold;
    }
    .regime-volatile {
        color: #ff0000;
        font-weight: bold;
    }
    .tooltip-text {
        font-size: 12px;
        color: #888;
        font-style: italic;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'collector' not in st.session_state:
    try:
        st.session_state.collector = MarketDataCollector()
        # Test connection
        st.session_state.collector.ping()
        USE_DEMO_MODE = False
    except:
        st.warning("⚠️ Network unavailable - Running in DEMO MODE with simulated data")
        USE_DEMO_MODE = True
        st.session_state.collector = None
        
if 'last_update' not in st.session_state:
    st.session_state.last_update = None
if 'data_cache' not in st.session_state:
    st.session_state.data_cache = {}
if 'demo_mode' not in st.session_state:
    st.session_state.demo_mode = USE_DEMO_MODE

def get_regime_emoji(regime):
    """Return emoji and color for regime"""
    regimes = {
        'trending': ('🟢', 'regime-trending', 'Trending'),
        'ranging': ('🟡', 'regime-ranging', 'Ranging'),
        'volatile': ('🔴', 'regime-volatile', 'High Volatility'),
        'unknown': ('⚪', '', 'Unknown')
    }
    return regimes.get(regime, regimes['unknown'])

def create_main_chart(df, symbol):
    """
    Create the main price chart with all overlays
    This is your core "what is the market doing" chart
    """
    if df is None or len(df) == 0:
        return None
    
    # Create subplot with candlestick and volume
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
        subplot_titles=(f'{symbol} Price Chart', 'Volume')
    )
    
    # Candlestick chart
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Price',
            increasing_line_color='#00ff00',
            decreasing_line_color='#ff0000'
        ),
        row=1, col=1
    )
    
    # VWAP - THE MOST IMPORTANT LINE
    if 'vwap' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['vwap'],
                mode='lines',
                name='VWAP',
                line=dict(color='#ffaa00', width=2, dash='solid'),
                hovertemplate='VWAP: $%{y:,.2f}<extra></extra>'
            ),
            row=1, col=1
        )
    
    # EMAs
    if 'ema_50' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df['ema_50'],
                mode='lines', name='EMA 50',
                line=dict(color='cyan', width=1),
                hovertemplate='EMA 50: $%{y:,.2f}<extra></extra>'
            ),
            row=1, col=1
        )
    
    if 'ema_200' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df['ema_200'],
                mode='lines', name='EMA 200',
                line=dict(color='magenta', width=1),
                hovertemplate='EMA 200: $%{y:,.2f}<extra></extra>'
            ),
            row=1, col=1
        )
    
    # Bollinger Bands
    if 'bb_upper' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df['bb_upper'],
                mode='lines', name='BB Upper',
                line=dict(color='rgba(100,100,100,0.3)', width=1),
                showlegend=False
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df['bb_lower'],
                mode='lines', name='BB Lower',
                line=dict(color='rgba(100,100,100,0.3)', width=1),
                fill='tonexty',
                fillcolor='rgba(100,100,100,0.1)',
                showlegend=False
            ),
            row=1, col=1
        )
    
    # Volume bars
    colors = ['#00ff00' if df['close'].iloc[i] >= df['open'].iloc[i] else '#ff0000' 
              for i in range(len(df))]
    
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df['volume'],
            name='Volume',
            marker_color=colors,
            showlegend=False
        ),
        row=2, col=1
    )
    
    # Volume MA line
    if 'volume_ma' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['volume_ma'],
                mode='lines',
                name='Volume MA',
                line=dict(color='yellow', width=1),
                showlegend=False
            ),
            row=2, col=1
        )
    
    # Update layout
    fig.update_layout(
        height=config.DASHBOARD['chart_height'],
        template='plotly_dark',
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    fig.update_xaxes(title_text="Time", row=2, col=1)
    fig.update_yaxes(title_text="Price (USD)", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    
    return fig

def render_market_overview(collector):
    """
    1️⃣ Market Overview - Top bar
    Answers: "Is the market awake or asleep?"
    """
    st.markdown("### 📊 Market Overview")
    
    # Use demo data if in demo mode
    if st.session_state.get('demo_mode', False):
        btc_gen = get_demo_collector('BTCUSDT')
        eth_gen = get_demo_collector('ETHUSDT')
        btc_stats = btc_gen.get_24h_stats('BTCUSDT')
        eth_stats = eth_gen.get_24h_stats('ETHUSDT')
        market_cap = btc_gen.get_market_cap_data()
        latency = btc_gen.ping()
    else:
        # Get data for BTC and ETH
        btc_stats = collector.get_24h_stats('BTCUSDT')
        eth_stats = collector.get_24h_stats('ETHUSDT')
        market_cap = collector.get_market_cap_data()
        latency = collector.ping()
    
    if btc_stats and eth_stats:
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric(
                "BTC",
                f"${btc_stats['price']:,.2f}",
                f"{btc_stats['change_24h']:.2f}%",
                delta_color="normal"
            )
            if config.DASHBOARD['show_tooltips']:
                st.caption("💡 Bitcoin price - market leader")
        
        with col2:
            st.metric(
                "ETH",
                f"${eth_stats['price']:,.2f}",
                f"{eth_stats['change_24h']:.2f}%",
                delta_color="normal"
            )
            if config.DASHBOARD['show_tooltips']:
                st.caption("💡 Ethereum price - alt leader")
        
        with col3:
            if market_cap:
                st.metric(
                    "Total Market Cap",
                    f"${market_cap['total_market_cap']/1e9:.1f}B",
                    help="Estimated total crypto market capitalization"
                )
                if config.DASHBOARD['show_tooltips']:
                    st.caption("💡 Size of entire crypto market")
        
        with col4:
            if market_cap:
                st.metric(
                    "BTC Dominance",
                    f"{market_cap['btc_dominance']:.1f}%",
                    help="Bitcoin's share of total market cap"
                )
                if config.DASHBOARD['show_tooltips']:
                    st.caption("💡 BTC↑ + Dom↑ = risk-off")
        
        with col5:
            if latency:
                latency_color = "🟢" if latency < 100 else "🟡" if latency < 500 else "🔴"
                latency_label = "Demo Latency" if st.session_state.get('demo_mode') else "Exchange Ping"
                st.metric(
                    latency_label,
                    f"{latency_color} {latency:.0f}ms"
                )
                if config.DASHBOARD['show_tooltips']:
                    st.caption("💡 Connection speed to exchange")
    
    st.markdown("---")

def render_volatility_momentum(df):
    """
    3️⃣ Volatility & Momentum
    Answers: "Should I even pay attention?"
    """
    st.markdown("### ⚡ Volatility & Momentum")
    
    if df is None or len(df) < 1:
        st.warning("Not enough data")
        return
    
    latest = df.iloc[-1]
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        atr = latest.get('atr', 0)
        st.metric("ATR (Volatility)", f"${atr:.2f}")
        if config.DASHBOARD['show_tooltips']:
            st.caption("💡 Average True Range - how much price moves")
    
    with col2:
        rsi = latest.get('rsi', 50)
        rsi_color = "🔴" if rsi > 70 else "🟢" if rsi < 30 else "🟡"
        st.metric("RSI", f"{rsi_color} {rsi:.1f}")
        if config.DASHBOARD['show_tooltips']:
            st.caption("💡 >70 = overbought, <30 = oversold")
    
    with col3:
        volume_ratio = latest.get('volume_ratio', 1)
        volume_spike = volume_ratio > config.ALERTS['volume_spike_multiplier']
        volume_icon = "🚨" if volume_spike else "📊"
        st.metric("Volume vs Avg", f"{volume_icon} {volume_ratio:.1f}x")
        if config.DASHBOARD['show_tooltips']:
            st.caption("💡 Current volume vs average")
    
    with col4:
        vwap_dist = latest.get('vwap_distance_pct', 0)
        stretched = abs(vwap_dist) > config.ALERTS['price_stretch_percent']
        stretch_icon = "⚠️" if stretched else "✅"
        st.metric("Distance from VWAP", f"{stretch_icon} {vwap_dist:.2f}%")
        if config.DASHBOARD['show_tooltips']:
            st.caption("💡 How far price is from fair value")

def render_trend_regime(df):
    """
    4️⃣ Trend & Regime
    Answers: "What type of market is this?"
    """
    st.markdown("### 🎯 Market Regime & Trend")
    
    if df is None or len(df) < 50:
        st.warning("Not enough data for regime analysis")
        return
    
    regime = IndicatorCalculator.calculate_market_regime(df)
    trend = IndicatorCalculator.calculate_trend_direction(df)
    
    emoji, css_class, label = get_regime_emoji(regime)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"### {emoji} {label}")
        if config.DASHBOARD['show_tooltips']:
            if regime == 'trending':
                st.caption("💡 Market has clear direction - trend strategies work")
            elif regime == 'ranging':
                st.caption("💡 Market is choppy - mean reversion works")
            else:
                st.caption("💡 High volatility - be cautious")
    
    with col2:
        trend_emoji = "📈" if trend == 'up' else "📉" if trend == 'down' else "➡️"
        st.markdown(f"### {trend_emoji} Trend: {trend.upper()}")
        if config.DASHBOARD['show_tooltips']:
            st.caption("💡 Current directional bias")
    
    with col3:
        latest = df.iloc[-1]
        adx = latest.get('adx', 0)
        strength = "Strong" if adx > 40 else "Moderate" if adx > 25 else "Weak"
        st.metric("Trend Strength (ADX)", f"{adx:.1f} - {strength}")
        if config.DASHBOARD['show_tooltips']:
            st.caption("💡 ADX >25 = trending, <25 = ranging")

def render_derivatives_data(symbol, collector):
    """
    5️⃣ Derivatives Reality Check
    This is crypto-specific and CRUCIAL
    """
    st.markdown("### 📈 Derivatives (Futures/Perps)")
    
    # Remove 'USDT' and add it back for futures symbol
    base_symbol = symbol.replace('USDT', '')
    futures_symbol = base_symbol + 'USDT'
    
    try:
        # Use demo data if in demo mode
        if st.session_state.get('demo_mode', False):
            gen = get_demo_collector(symbol)
            funding = gen.get_funding_rate(futures_symbol)
            oi = gen.get_open_interest(futures_symbol)
        else:
            funding = collector.get_funding_rate(futures_symbol)
            oi = collector.get_open_interest(futures_symbol)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if funding:
                rate = funding['funding_rate'] * 100
                rate_color = "🔴" if abs(rate) > 0.01 else "🟡" if abs(rate) > 0.005 else "🟢"
                st.metric("Funding Rate", f"{rate_color} {rate:.4f}%")
                if config.DASHBOARD['show_tooltips']:
                    st.caption("💡 Fee longs pay shorts (or vice versa)")
                    if rate > 0.01:
                        st.caption("⚠️ Longs overcrowded - possible reversal")
                    elif rate < -0.01:
                        st.caption("⚠️ Shorts overcrowded - possible squeeze")
        
        with col2:
            if oi:
                st.metric("Open Interest", f"${oi['open_interest']/1e6:.1f}M")
                if config.DASHBOARD['show_tooltips']:
                    st.caption("💡 Total outstanding contracts")
        
        with col3:
            st.info("Perp-Spot spread coming soon")
            if config.DASHBOARD['show_tooltips']:
                st.caption("💡 Premium = bullish bias")
    
    except Exception as e:
        st.info(f"Derivatives data unavailable for {futures_symbol}")
        if config.DASHBOARD['show_tooltips']:
            st.caption("💡 Only available for perpetual futures pairs")

def main():
    """Main dashboard application"""
    
    # Sidebar controls
    st.sidebar.title("⚙️ Dashboard Controls")
    
    # Symbol selection
    all_symbols = config.PRIMARY_SYMBOLS + config.ALT_SYMBOLS
    selected_symbol = st.sidebar.selectbox(
        "Select Trading Pair",
        all_symbols,
        index=0
    )
    
    # Timeframe selection
    timeframe = st.sidebar.selectbox(
        "Timeframe",
        list(config.TIMEFRAMES.keys()),
        index=list(config.TIMEFRAMES.keys()).index(config.DEFAULT_TIMEFRAME)
    )
    
    # Data amount
    candle_limit = st.sidebar.slider(
        "Number of Candles",
        min_value=50,
        max_value=1000,
        value=500,
        step=50
    )
    
    # Toggle tooltips (beginner mode)
    config.DASHBOARD['show_tooltips'] = st.sidebar.checkbox(
        "🧠 Show Learning Tooltips",
        value=True,
        help="Show explanations for each metric"
    )
    
    # Auto-refresh
    auto_refresh = st.sidebar.checkbox("Auto-refresh", value=True)
    if auto_refresh:
        refresh_interval = st.sidebar.slider("Refresh interval (seconds)", 5, 60, 10)
    
    # Manual refresh button
    if st.sidebar.button("🔄 Refresh Now"):
        st.session_state.data_cache = {}
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📚 Quick Guide")
    st.sidebar.markdown("""
    **Your Dashboard Answers:**
    1. What's the market doing? → Overview
    2. Is it calm or wild? → Volatility
    3. Fair or stretched? → VWAP distance
    4. Good to trade? → Regime
    """)
    
    # Main content
    st.title("🚀 Crypto Trading Dashboard")
    if st.session_state.get('demo_mode', False):
        st.info("📊 Running in DEMO MODE - Using simulated data for demonstration")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1️⃣ Market Overview
    render_market_overview(st.session_state.collector)
    
    # Fetch main data
    with st.spinner(f"Loading {selected_symbol} data..."):
        # Check cache
        cache_key = f"{selected_symbol}_{timeframe}_{candle_limit}"
        
        if cache_key not in st.session_state.data_cache or \
           (st.session_state.last_update and 
            (datetime.now() - st.session_state.last_update).seconds > 60):
            
            # Fetch fresh data - use demo if in demo mode
            if st.session_state.get('demo_mode', False):
                gen = get_demo_collector(selected_symbol)
                df = gen.generate_klines(selected_symbol, timeframe, limit=candle_limit)
            else:
                df = st.session_state.collector.get_klines(
                    selected_symbol,
                    timeframe,
                    limit=candle_limit
                )
            
            if df is not None:
                # Calculate indicators
                df = IndicatorCalculator.calculate_all(df)
                st.session_state.data_cache[cache_key] = df
                st.session_state.last_update = datetime.now()
        else:
            df = st.session_state.data_cache.get(cache_key)
    
    if df is not None and len(df) > 0:
        # 2️⃣ Main Chart
        st.markdown("### 📈 Price & Structure")
        chart = create_main_chart(df, selected_symbol)
        if chart:
            st.plotly_chart(chart, use_container_width=True)
        
        # 3️⃣ Volatility & Momentum
        render_volatility_momentum(df)
        st.markdown("---")
        
        # 4️⃣ Trend & Regime
        render_trend_regime(df)
        st.markdown("---")
        
        # 5️⃣ Derivatives
        render_derivatives_data(selected_symbol, st.session_state.collector)
        st.markdown("---")
        
        # 6️⃣ Raw Data (expandable)
        with st.expander("📊 View Raw Data"):
            st.dataframe(df.tail(20))
    
    else:
        st.error("Failed to load market data. Please check your connection.")
    
    # Auto-refresh logic
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()

if __name__ == "__main__":
    main()
