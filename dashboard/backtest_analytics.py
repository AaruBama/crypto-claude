
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import os

def render_backtest_analytics():
    st.markdown("# 📉 Comprehensive Backtest Analytics")
    st.info("Chameleon V7 evaluation results across multiple regimes, assets, and exchanges.")

    # 1. KPI Cards Row
    st.markdown("### 🏆 V7.1 Benchmark Performance (BTC Solo 100%)")
    c1, c2, c3, c4 = st.columns(4)
    
    # These are summarized findings from the solo BTC run
    c1.metric("1Y Projected PnL", "+26.33%", delta="Pure BTC Strategy")
    c2.metric("Max Drawdown", "-4.55%", delta="Moderate Risk", delta_color="normal")
    c3.metric("Profit Factor", "21.76", help="Gross Profit / Gross Loss")
    c4.metric("Recovery Factor", "5.79", help="PnL / Max Drawdown")

    st.divider()

    # 2. Asset Contribution (Solo BTC)
    st.markdown("### 🗺️ Asset Analysis (Binance 365D)")
    st.info("Portfolio is now 100% BTC. Performance is strictly driven by Bitcoin's momentum breakout signals.")
    
    col_ast1, col_ast2 = st.columns([1, 1])
    
    with col_ast1:
        st.markdown("#### Performance Matrix")
        st.write("By dropping altcoins and focusing purely on BTC, the engine achieved a significantly higher expectancy and win rate.")
        st.success("✅ 90% Win Rate on Trend Breakouts")
        st.success("✅ 26.33% Annual Return")
        
    with col_ast2:
        df_solo = pd.DataFrame([{"Asset": "BTC", "PnL ($)": 78.99}])
        st.table(df_solo)

    st.divider()

    # 3. Regime Comparison remains as a benchmark section
    st.markdown("### 🔬 Historical Regime A/B Testing")
    st.caption("Benchmark comparison of 1-year performance (BTC/SOL legacy context).")
    
    regime_data = pd.DataFrame({
        "Regime": ["Baseline (Mixed)", "Relaxed MR", "Pure Momentum (Solo BTC)"],
        "CAGR %": [11.47, 13.22, 26.33],
        "Max DD %": [-2.62, -2.61, -4.55],
        "Profit Factor": [1.41, 1.42, 21.76]
    })
    
    fig_regime = px.bar(regime_data, x="Regime", y="CAGR %", color="Regime",
                       text_auto='.2f')
    fig_regime.update_layout(template="plotly_dark", showlegend=False)
    st.plotly_chart(fig_regime, use_container_width=True)

    st.divider()

    # 4. Exchange Comparison
    st.markdown("### 🏦 Exchange Implementation Check")
    ex_data = pd.DataFrame({
        "Exchange": ["Binance (Spot)", "Hyperliquid (Perps)"],
        "Test Duration": ["365 Days", "52 Days"],
        "PnL %": [26.33, 0.43],
        "Max DD %": [-4.55, -0.61]
    })
    st.table(ex_data)

    if st.button("🚀 Re-Run BTC Solo Backtest", use_container_width=True):
        st.warning("Executing 365-day solo simulation...")
        os.system("PYTHONPATH=. ./venv/bin/python trading_engine/multi_asset_vbt_backtest.py")

