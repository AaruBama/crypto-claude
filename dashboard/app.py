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
from data.ai_bridge import AIBridge
from data.wallet import PaperWallet
from data.llm_orchestrator import MultiLLMOrchestrator
import config

# Import AI Advisory helpers from same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai_advisory_helpers import render_ai_advisory_tab

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
    /* Strategy Card Styling */
    .strategy-card {
        background-color: #1e1e1e;
        border: 1px solid #333;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 10px;
    }
    .strategy-header {
        color: #ffaa00;
        font-weight: bold;
        font-size: 18px;
        margin-bottom: 5px;
    }
    .strategy-param {
        font-family: monospace;
        color: #00ff00;
    }
    /* Style for sidebar chat */
    .stChatFloatingInputContainer {
        padding-bottom: 20px;
    }
    /* Profile Header Styling */
    .header-profile {
        background: linear-gradient(90deg, #1e1e1e 0%, #2d2d2d 100%);
        padding: 15px 25px;
        border-radius: 15px;
        border: 1px solid #333;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 25px;
    }
    .profile-item {
        text-align: right;
    }
    .profile-label {
        font-size: 12px;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .profile-value {
        font-size: 20px;
        font-weight: bold;
        color: #ffaa00;
    }
    /* Facebook-style Chat Widget */
    .chat-widget {
        position: fixed;
        bottom: 20px;
        right: 20px;
        z-index: 9999;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    .chat-widget-minimized {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 12px 20px;
        border-radius: 25px;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        transition: all 0.3s ease;
    }
    .chat-widget-minimized:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(0,0,0,0.4);
    }
    .chat-widget-expanded {
        background: #1e1e1e;
        border: 1px solid #333;
        border-radius: 15px;
        width: 350px;
        height: 500px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.5);
        display: flex;
        flex-direction: column;
    }
    .chat-widget-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 15px;
        border-radius: 15px 15px 0 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-weight: bold;
    }
    .chat-widget-body {
        flex: 1;
        overflow-y: auto;
        padding: 10px;
    }
    /* Force full opacity during all states */
    .stApp, .stApp > *, [data-testid="stAppViewContainer"], 
    [data-testid="stVerticalBlock"], .main, .block-container {
        opacity: 1 !important;
    }
    /* Remove any dimming overlays */
    .stApp[data-test-script-state="running"]::before,
    .stApp[data-test-script-state="running"]::after {
        display: none !important;
    }
    /* Hide spinner overlay background */
    .stSpinner > div {
        background-color: transparent !important;
    }
    /* Keep spinner visible but small */
    .stSpinner {
        position: fixed !important;
        top: 10px !important;
        right: 150px !important;
        z-index: 999999 !important;
    }
</style>

<script>
// JavaScript to forcefully prevent dimming of main content area
(function() {
    // Monitor for any opacity changes on the main content container
    const observer = new MutationObserver(function(mutations) {
        // Target the main content block that Streamlit dims
        const mainBlock = document.querySelector('.main .block-container');
        const stBlock = document.querySelector('[data-testid="stVerticalBlock"]');
        const appView = document.querySelector('[data-testid="stAppViewContainer"]');
        
        // Force opacity to 1 on main content
        if (mainBlock && mainBlock.style.opacity !== '1' && mainBlock.style.opacity !== '') {
            mainBlock.style.setProperty('opacity', '1', 'important');
        }
        if (stBlock && stBlock.style.opacity !== '1' && stBlock.style.opacity !== '') {
            stBlock.style.setProperty('opacity', '1', 'important');
        }
        if (appView && appView.style.opacity !== '1' && appView.style.opacity !== '') {
            appView.style.setProperty('opacity', '1', 'important');
        }
    });
    
    // Start observing the document body for changes
    observer.observe(document.body, {
        attributes: true,
        attributeFilter: ['style'],
        subtree: true,
        childList: true
    });
    
    // Backup interval to force opacity
    setInterval(function() {
        const mainBlock = document.querySelector('.main .block-container');
        if (mainBlock && mainBlock.style.opacity && mainBlock.style.opacity !== '1') {
            mainBlock.style.setProperty('opacity', '1', 'important');
        }
        const stBlock = document.querySelector('[data-testid="stVerticalBlock"]');
        if (stBlock && stBlock.style.opacity && stBlock.style.opacity !== '1') {
            stBlock.style.setProperty('opacity', '1', 'important');
        }
    }, 50);
})();
</script>
""", unsafe_allow_html=True)

# Initialize session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'wallet' not in st.session_state:
    st.session_state.wallet = PaperWallet()

# Multi-LLM session state
if 'claude_history' not in st.session_state:
    st.session_state.claude_history = []
if 'gemini_advisory_history' not in st.session_state:
    st.session_state.gemini_advisory_history = []
if 'grok_history' not in st.session_state:
    st.session_state.grok_history = []
if 'llm_orchestrator' not in st.session_state:
    st.session_state.llm_orchestrator = MultiLLMOrchestrator()

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
    
    # AI Contextual Analysis for Market Overview
    if btc_stats and eth_stats:
        btc_change = btc_stats['change_24h']
        eth_change = eth_stats['change_24h']
        btc_dom = market_cap.get('btc_dominance', 0) if market_cap else 0
        
        # Generate contextual explanation
        market_mood = ""
        if btc_change > 5 and eth_change > 5:
            market_mood = "🚀 **Strong Bull Market**: Both BTC and ETH are rallying hard. Risk appetite is high across the board."
        elif btc_change < -5 and eth_change < -5:
            market_mood = "🔴 **Market Correction**: Both majors are down significantly. Risk-off sentiment is dominating."
        elif btc_change > 2 and btc_dom > 50:
            market_mood = "🛡️ **Bitcoin Dominance**: BTC is leading while alts lag. Investors are rotating to safety."
        elif eth_change > btc_change + 3:
            market_mood = "🌈 **Alt Season Vibes**: ETH is outperforming BTC. Risk appetite for altcoins is increasing."
        elif abs(btc_change) < 2 and abs(eth_change) < 2:
            market_mood = "😴 **Quiet Market**: Low volatility across majors. Waiting for a catalyst."
        else:
            market_mood = "📊 **Mixed Signals**: Market is showing divergent behavior between BTC and ETH."
        
        st.info(f"**Current Market Situation:** {market_mood}")
    
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
    
    # AI Contextual Analysis for Volatility & Momentum
    rsi = latest.get('rsi', 50)
    volume_ratio = latest.get('volume_ratio', 1)
    vwap_dist = latest.get('vwap_distance_pct', 0)
    atr = latest.get('atr', 0)
    
    volatility_analysis = ""
    if rsi > 70 and vwap_dist > 5:
        volatility_analysis = "⚠️ **Overbought & Stretched**: Price is extended above fair value with high RSI. Expect potential mean reversion."
    elif rsi < 30 and vwap_dist < -5:
        volatility_analysis = "💎 **Oversold & Discounted**: Price is below fair value with low RSI. Potential bounce opportunity."
    elif volume_ratio > 2:
        volatility_analysis = "🔥 **High Volume Surge**: Exceptional trading activity detected. This move has strong conviction behind it."
    elif volume_ratio < 0.7:
        volatility_analysis = "😴 **Low Conviction**: Volume is weak. Current price action may lack follow-through."
    elif abs(vwap_dist) < 2 and 40 < rsi < 60:
        volatility_analysis = "⚖️ **Balanced Market**: Price is near fair value with neutral momentum. Good for range trading."
    else:
        volatility_analysis = "📊 **Normal Activity**: Market is showing typical volatility and momentum patterns."
    
    st.info(f"**Current Momentum Situation:** {volatility_analysis}")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("ATR (Volatility)", f"${atr:.2f}")
        if config.DASHBOARD['show_tooltips']:
            st.caption("💡 Average True Range - how much price moves")
    
    with col2:
        rsi_color = "🔴" if rsi > 70 else "🟢" if rsi < 30 else "🟡"
        st.metric("RSI", f"{rsi_color} {rsi:.1f}")
        if config.DASHBOARD['show_tooltips']:
            st.caption("💡 >70 = overbought, <30 = oversold")
    
    with col3:
        volume_spike = volume_ratio > config.ALERTS['volume_spike_multiplier']
        volume_icon = "🚨" if volume_spike else "📊"
        st.metric("Volume vs Avg", f"{volume_icon} {volume_ratio:.1f}x")
        if config.DASHBOARD['show_tooltips']:
            st.caption("💡 Current volume vs average")
    
    with col4:
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
    latest = df.iloc[-1]
    adx = latest.get('adx', 0)
    
    # AI Contextual Analysis for Trend & Regime
    regime_analysis = ""
    if regime == 'trending' and adx > 40:
        if trend == 'up':
            regime_analysis = "🚀 **Strong Uptrend Confirmed**: High ADX with upward bias. Trend-following strategies (buy dips, ride momentum) are ideal."
        elif trend == 'down':
            regime_analysis = "📉 **Strong Downtrend Confirmed**: High ADX with downward bias. Consider shorting rallies or staying in cash."
        else:
            regime_analysis = "⚡ **High Momentum, Unclear Direction**: Strong trend strength but mixed signals. Wait for clarity."
    elif regime == 'trending' and adx > 25:
        regime_analysis = f"📈 **Moderate {trend.capitalize()} Trend**: Market has directional bias. Trend strategies can work with proper risk management."
    elif regime == 'ranging':
        regime_analysis = "⚖️ **Ranging Market**: Price is choppy without clear direction. Mean reversion strategies (buy support, sell resistance) work best."
    elif regime == 'volatile':
        regime_analysis = "🔴 **High Volatility Warning**: Market is erratic and unpredictable. Reduce position sizes or stay on the sidelines."
    else:
        regime_analysis = "📊 **Neutral Market**: No strong trend or range. Wait for a clearer setup before entering positions."
    
    st.info(f"**Current Regime Situation:** {regime_analysis}")
    
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
            spot_price = gen.get_current_price(symbol)
            perp_price = gen.get_futures_price(futures_symbol)
        else:
            funding = collector.get_funding_rate(futures_symbol)
            oi = collector.get_open_interest(futures_symbol)
            spot_price = collector.get_current_price(symbol)
            perp_price = collector.get_futures_price(futures_symbol)
        
        # AI Contextual Analysis for Derivatives
        if funding and perp_price and spot_price:
            rate = funding['funding_rate'] * 100
            spread = perp_price - spot_price
            spread_pct = (spread / spot_price) * 100
            
            derivatives_analysis = ""
            if rate > 0.01 and spread_pct > 0.1:
                derivatives_analysis = "🔴 **Extreme Long Crowding**: High positive funding + premium suggests overleveraged longs. Risk of liquidation cascade."
            elif rate < -0.01 and spread_pct < -0.1:
                derivatives_analysis = "🟢 **Extreme Short Crowding**: Negative funding + discount suggests overleveraged shorts. Potential short squeeze setup."
            elif abs(rate) > 0.01:
                side = "Longs" if rate > 0 else "Shorts"
                derivatives_analysis = f"⚠️ **{side} Overcrowded**: High funding rate indicates one-sided positioning. Watch for reversals."
            elif abs(spread_pct) > 0.1:
                if spread_pct > 0:
                    derivatives_analysis = "📈 **Bullish Futures Premium**: Perps trading above spot suggests strong demand for leverage. Market optimism."
                else:
                    derivatives_analysis = "📉 **Bearish Futures Discount**: Perps trading below spot suggests fear or heavy shorting."
            else:
                derivatives_analysis = "⚖️ **Balanced Derivatives**: Funding and spread are neutral. No extreme positioning detected."
            
            st.info(f"**Current Derivatives Situation:** {derivatives_analysis}")
        
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
            if perp_price and spot_price:
                spread = perp_price - spot_price
                spread_pct = (spread / spot_price) * 100
                
                label = "Premium" if spread > 0 else "Discount"
                color = "green" if spread > 0 else "red"
                
                st.metric("Perp-Spot Spread", f"${spread:,.2f}", delta=f"{spread_pct:.3f}% ({label})")
                if config.DASHBOARD['show_tooltips']:
                    st.caption(f"💡 Perp: ${perp_price:,.2f} vs Spot: ${spot_price:,.2f}")
                    if spread_pct > 0.1:
                        st.caption("⚠️ High Premium: Market is getting frothy")
                    elif spread_pct < -0.1:
                        st.caption("⚠️ High Discount: Possible panic or heavy shorting")
            else:
                st.info("Spread calculation unavailable")
    
    except Exception as e:
        # If live futures data is geoblocked/unavailable, use demo data as a fallback
        # so the user can still see how the spread works.
        try:
            gen = get_demo_collector(symbol)
            funding = gen.get_funding_rate(futures_symbol)
            oi = gen.get_open_interest(futures_symbol)
            spot_price = gen.get_current_price(symbol)
            perp_price = gen.get_futures_price(futures_symbol)
            
            st.warning(f"⚠️ Live Futures data restricted ({futures_symbol}). Using estimated market signals.")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                rate = funding['funding_rate'] * 100
                st.metric("Funding Rate (Est)", f"🟡 {rate:.4f}%")
            with col2:
                st.metric("Open Interest (Est)", f"${oi['open_interest']/1e6:.1f}M")
            with col3:
                spread = perp_price - spot_price
                spread_pct = (spread / spot_price) * 100
                label = "Premium" if spread > 0 else "Discount"
                st.metric("Spread (Est)", f"${spread:,.2f}", delta=f"{spread_pct:.3f}% ({label})")
        except:
            st.info(f"Derivatives data unavailable for {futures_symbol}")
            if config.DASHBOARD['show_tooltips']:
                st.caption("💡 Only available for perpetual futures pairs")

def render_strategy_card(strategy_json, unique_id="0"):
    """Renders the editable strategy card (The 'Handshake')"""
    if not strategy_json:
        return
        
    name = strategy_json.get('strategy_name', 'Untitled Strategy')
    action = strategy_json.get('action', 'WAIT')
    rationale = strategy_json.get('rationale', '')
    params = strategy_json.get('trade_params', {})
    
    # Extract defaults
    wallet = st.session_state.wallet
    default_price = wallet._sanitize_price(params.get('entry_price', 0))
    default_sl = wallet._sanitize_price(params.get('stop_loss', 0))
    default_tp = wallet._sanitize_price(params.get('take_profit', 0))
    default_tsl = float(params.get('trailing_stop_percent') or 0)
    default_usd = round(wallet.get_balance() * 0.1, 2)
    scaling_list = params.get('scaling_targets', [])
    
    action_color = "🟢" if "BUY" in action.upper() else "🔴" if "SELL" in action.upper() else "⚖️"
    
    with st.container():
        st.markdown(f"""
        <div class="strategy-card">
            <div class="strategy-header">{action_color} Draft Strategy: {name}</div>
            <p style="font-size: 0.9em; opacity: 0.8;">{rationale}</p>
        </div>
        """, unsafe_allow_html=True)
        
        if action == "WAIT":
            st.info("The AI suggests staying on the sidelines for now.")
            return

        # Interactive Form
        with st.expander("🛠️ Edit Trade Parameters", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                final_price = st.number_input("Entry Price ($)", value=float(default_price), step=0.1, key=f"p_{unique_id}")
                final_sl = st.number_input("Stop Loss ($)", value=float(default_sl), step=0.1, key=f"sl_{unique_id}")
                final_usd = st.number_input("Trade Size (USD)", value=float(default_usd), step=10.0, key=f"usd_{unique_id}")
            with c2:
                final_tp = st.number_input("Take Profit ($)", value=float(default_tp), step=0.1, key=f"tp_{unique_id}")
                final_tsl = st.slider("Trailing Stop (%)", 0.0, 10.0, float(default_tsl), key=f"tsl_{unique_id}")
            
            # Update strategy_json with edited values for execution
            strategy_json['trade_params']['entry_price'] = final_price
            strategy_json['trade_params']['stop_loss'] = final_sl
            strategy_json['trade_params']['take_profit'] = final_tp
            strategy_json['trade_params']['trailing_stop_percent'] = final_tsl
            
            btn_key = f"approve_{unique_id}_{name}_{params.get('symbol', 'trade')}".replace(' ', '_')
            if st.button(f"🚀 Execute {action.upper()} Position", key=btn_key, use_container_width=True, type="primary"):
                success, msg = wallet.execute_strategy(strategy_json, override_usd=final_usd)
                if success:
                    st.success(msg)
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)

def render_orders_page(df=None, selected_symbol="BTC/USDT"):
    """
    Renders the Order Book and Portfolio page.
    Shows active positions with live PnL and close buttons.
    """
    st.markdown("## 📋 Portfolio & Order Book")
    
    wallet = st.session_state.wallet
    collector = st.session_state.collector
    
    # 1. Active Positions
    st.markdown("### 🏹 Active Positions")
    positions_data = wallet.data.get("positions", {})
    
    active_cols = st.columns(3) # Fix to 3 columns for better spacing
    
    has_positions = False
    for i, (symbol, pos) in enumerate(positions_data.items()):
        amount = pos.get("amount", 0)
        avg_price = pos.get("avg_price", 0)
        
        if abs(amount) > 1e-8: # Filter dust
            has_positions = True
            with active_cols[i % 3]:
                # Get current price
                try:
                    ticker = collector.get_24h_stats(symbol)
                    current_price = ticker['price'] if ticker else avg_price
                except:
                    current_price = avg_price
                
                # Calculate PnL
                if amount > 0: # Long
                    pnl = (current_price - avg_price) * amount
                    pnl_pct = ((current_price / avg_price) - 1) * 100 if avg_price > 0 else 0
                    pos_type = "LONG"
                    color = "#00ff00"
                else: # Short
                    pnl = (avg_price - current_price) * abs(amount)
                    pnl_pct = ((avg_price / current_price) - 1) * 100 if current_price > 0 else 0
                    pos_type = "SHORT"
                    color = "#ff4b4b"
                
                st.markdown(f"""
                <div style="padding:15px; border-radius:10px; border:1px solid #333; background-color:#111; margin-bottom:10px;">
                    <h4 style="margin:0; color:{color};">{symbol} {pos_type}</h4>
                    <p style="margin:5px 0; font-family:monospace; font-size:18px;">Amt: {amount:.6f}</p>
                    <p style="margin:2px 0; font-size:14px; color:#888;">Avg Entry: ${avg_price:,.2f}</p>
                    <p style="margin:10px 0 5px 0; font-size:20px; font-weight:bold; color:{'#00ff00' if pnl >= 0 else '#ff4b4b'}">
                        PnL: ${pnl:,.2f} ({pnl_pct:+.2f}%)
                    </p>
                </div>
                """, unsafe_allow_html=True)
                
                # Close button
                if st.button(f"Close {symbol}", key=f"close_{symbol}"):
                    success, msg = wallet.close_position(symbol, current_price)
                    if success:
                        st.success(msg)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
                
    if not has_positions:
        st.info("No active positions. The market is waiting for your next move!")

    st.markdown("---")

    # 2. Order History & Filtering
    st.markdown("### 📜 Order History")
    
    history = wallet.get_history()
    if not history:
        st.info("No trade history yet.")
        return

    # Convert to DataFrame for easy filtering
    history_df = pd.DataFrame(history)
    history_df['time'] = pd.to_datetime(history_df['time'])
    
    # Filter Controls
    f_col1, f_col2, f_col3 = st.columns(3)
    
    with f_col1:
        symbols = ["All"] + list(history_df['pair'].unique())
        f_symbol = st.selectbox("Filter Symbol", symbols)
        
    with f_col2:
        types = ["All"] + list(history_df['type'].unique())
        f_type = st.selectbox("Filter Type", types)
        
    with f_col3:
        # Date filter
        min_date = history_df['time'].min().date()
        max_date = history_df['time'].max().date()
        f_date = st.date_input("Date Range", [min_date, max_date])

    # Apply Filters
    filtered_df = history_df.copy()
    if f_symbol != "All":
        filtered_df = filtered_df[filtered_df['pair'] == f_symbol]
    if f_type != "All":
        filtered_df = filtered_df[filtered_df['type'] == f_type]
    if len(f_date) == 2:
        filtered_df = filtered_df[(filtered_df['time'].dt.date >= f_date[0]) & 
                                 (filtered_df['time'].dt.date <= f_date[1])]

    # Display Table
    st.dataframe(
        filtered_df.sort_values('time', ascending=False),
        use_container_width=True,
        hide_index=True
    )
    
    # Summary Metrics
    st.markdown("#### Stats Summary")
    s_col1, s_col2, s_col3 = st.columns(3)
    s_col1.metric("Total Trades", len(filtered_df))
    s_col2.metric("Total Volume (USD)", f"${filtered_df['total_usd'].sum():,.2f}")
    
    # Calculate Total Equity (Cash + Market Value of Positions)
    cash_balance = wallet.get_balance()
    unrealized_value = 0
    for sym, pos in wallet.data.get("positions", {}).items():
        amount = pos.get("amount", 0)
        if abs(amount) > 1e-8:
            try:
                ticker = st.session_state.collector.get_24h_stats(sym)
                price = ticker['price'] if ticker else pos.get("avg_price", 0)
            except:
                price = pos.get("avg_price", 0)
            unrealized_value += (amount * price)
    
    total_equity = cash_balance + unrealized_value
    initial_balance = wallet.data.get("initial_balance", 10000.0)
    total_pnl = total_equity - initial_balance
    
    s_col3.metric("Total Account PnL", f"${total_pnl:,.2f}", delta=f"{total_pnl:,.2f}")
    st.caption(f"Net Equity: ${total_equity:,.2f} | Starting: ${initial_balance:,.2f}")

def render_header(selected_symbol):
    """Renders the top header with a compact profile button"""
    wallet = st.session_state.wallet
    
    col1, col_spacer, col2 = st.columns([5, 1, 1])
    
    with col1:
        st.title("🚀 Crypto Trading Dashboard")
    
    with col2:
        # Compact Profile Button
        with st.popover("👤 Profile", use_container_width=True):
            st.markdown("### 🏦 Wallet Summary")
            st.metric("Total Balance", f"${wallet.get_balance():,.2f}")
            st.divider()
            st.markdown("**Holdings**")
            current_pos = wallet.get_position(selected_symbol)
            st.write(f"{selected_symbol}: `{current_pos:.6f}`")
            
            if st.button("📋 View Full Portfolio"):
                st.session_state.active_tab = 1
                st.rerun()



def main():
    """Main dashboard application"""
    
    # Init show_chat state
    if 'show_chat' not in st.session_state:
        st.session_state.show_chat = True

    # --- AUTO-UPGRADE WALLET (Session State Fix) ---
    if 'wallet' in st.session_state:
        if not hasattr(st.session_state.wallet, 'check_automated_orders'):
            st.session_state.wallet = PaperWallet()
            
    # Sidebar remains for controls
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
    
    # Toggle tooltips
    config.DASHBOARD['show_tooltips'] = st.sidebar.checkbox(
        "🧠 Show Learning Tooltips",
        value=True
    )
    
    # Auto-refresh
    auto_refresh = st.sidebar.checkbox("Auto-refresh", value=True)
    if auto_refresh:
        refresh_interval = st.sidebar.slider("Refresh interval (seconds)", 5, 60, 10)
    
    # Manual refresh button
    if st.sidebar.button("🔄 Refresh Now"):
        st.session_state.data_cache = {}
        st.rerun()
    
    # Pre-fetch data...
    cache_key = f"{selected_symbol}_{timeframe}_{candle_limit}"
    df = None
    
    if cache_key in st.session_state.data_cache and \
       not (st.session_state.last_update and 
            (datetime.now() - st.session_state.last_update).seconds > 60):
        df = st.session_state.data_cache.get(cache_key)
    else:
        with st.spinner(f"Fetching {selected_symbol} data..."):
            if st.session_state.get('demo_mode', False):
                gen = get_demo_collector(selected_symbol)
                df = gen.generate_klines(selected_symbol, timeframe, limit=candle_limit)
            else:
                df = st.session_state.collector.get_klines(selected_symbol, timeframe, limit=candle_limit)
            
            if df is not None:
                df = IndicatorCalculator.calculate_all(df)
                st.session_state.data_cache[cache_key] = df
                st.session_state.last_update = datetime.now()
                
    # --- AUTOMATION HEARTBEAT ---
    if df is not None:
        wallet = st.session_state.wallet
        for sym in list(wallet.data["positions"].keys()):
            amount = wallet.data["positions"][sym].get("amount", 0)
            if abs(amount) > 1e-8:
                if sym.replace('USDT', '') in selected_symbol:
                    curr_p = df.iloc[-1]['close']
                else:
                    try:
                        ticker = st.session_state.collector.get_24h_stats(sym)
                        curr_p = ticker['price'] if ticker else None
                    except: curr_p = None
                
                if curr_p:
                    trigger_msg = wallet.check_automated_orders(sym, curr_p)
                    if trigger_msg:
                        st.balloons()
                        st.toast(trigger_msg, icon="💰")
                        time.sleep(1)
                        st.rerun()
    
    st.sidebar.caption("⚡ Automation Heartbeat: Active")
    
    # --- AI Trading Mentor in Sidebar ---
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 👨‍🏫 AI Trading Mentor")
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("🔍 Analyze", use_container_width=True, type="primary", key="sidebar_analyze"):
            payload = AIBridge.get_market_payload(df, selected_symbol, st.session_state.collector)
            if payload:
                with st.spinner("Drafting Strategy..."):
                    response = AIBridge.consult_mentor(payload, chat_history=st.session_state.chat_history)
                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                    st.rerun()
    with col2:
        if st.button("🗑️ Clear", use_container_width=True, key="sidebar_clear"):
            st.session_state.chat_history = []
            st.rerun()
    
    # Chat History in sidebar
    for i, message in enumerate(st.session_state.chat_history):
        with st.sidebar.chat_message(message["role"]):
            strategy = AIBridge.extract_json(message["content"])
            if strategy and isinstance(strategy, dict) and 'strategy_name' in strategy:
                render_strategy_card(strategy, unique_id=f"sidebar_{i}")
            else:
                st.markdown(message["content"])
    
    if prompt := st.sidebar.chat_input("Ask your mentor...", key="sidebar_input"):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        payload = AIBridge.get_market_payload(df, selected_symbol, st.session_state.collector)
        with st.spinner("Mentor is thinking..."):
            response = AIBridge.consult_mentor(payload, chat_history=st.session_state.chat_history[:-1], user_message=prompt)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.rerun()

    # --- Header Render ---
    render_header(selected_symbol)
    
    # Main dashboard content as a fragment (auto-refreshes without dimming whole page)
    @st.fragment(run_every=refresh_interval if auto_refresh else None)
    def dashboard_content():
        """Main dashboard content that can refresh independently"""
        if 'active_tab' not in st.session_state:
            st.session_state.active_tab = 0

        # Fetch fresh data for this fragment
        df = None
        if st.session_state.get('demo_mode', False):
            from data.demo_data import get_demo_collector
            demo_collector = get_demo_collector(selected_symbol)
            df = demo_collector.get_klines(selected_symbol, timeframe, limit=candle_limit)
        else:
            if st.session_state.collector:
                df = st.session_state.collector.get_klines(selected_symbol, timeframe, limit=candle_limit)
            if df is not None:
                df = IndicatorCalculator.calculate_all(df)

        # Tab Navigation
        tab_list = ["🚀 Market Analysis", "📋 Order Book & Portfolio", "🤖 AI Advisory"]
        tabs = st.tabs(tab_list)
        
        # Tab 0: Market Analysis
        with tabs[0]:
            # Each section now has its own contextual analysis
            if st.session_state.get('demo_mode', False):
                st.info("📊 Running in DEMO MODE - Using simulated data for demonstration")
            st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 1️⃣ Market Overview
            render_market_overview(st.session_state.collector)
            
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
                st.error("Failed to load market data.")

        # Tab 1: Order Book & Portfolio
        with tabs[1]:
            render_orders_page(df, selected_symbol)
        
        # Tab 2: AI Advisory
        with tabs[2]:
            render_ai_advisory_tab(df, selected_symbol, st.session_state.collector)
    
    # Render the fragment
    dashboard_content()

if __name__ == "__main__":
    main()
