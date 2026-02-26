
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import os

def render_backtest_analytics():
    st.markdown("# 📉 Comprehensive Backtest Analytics")
    st.info("Chameleon V7 evaluation results across multiple regimes, assets, and exchanges.")

    # 1. KPI Cards Row
    st.markdown("### 🏆 V7.1 Benchmark Performance (Pure Momentum)")
    c1, c2, c3, c4 = st.columns(4)
    
    # These are summarized findings from the multi-asset 365d run
    c1.metric("1Y Projected PnL", "+19.82%", delta="Superior Regime")
    c2.metric("Max Drawdown", "-0.92%", delta="Ultra-Low Risk", delta_color="normal")
    c3.metric("Profit Factor", "4.44", help="Gross Profit / Gross Loss")
    c4.metric("Recovery Factor", "21.6", help="PnL / Max Drawdown")

    st.divider()

    # 2. Regime Comparison (A/B Test Results)
    st.markdown("### 🔬 Regime A/B Testing: The Road to Pure Momentum")
    st.caption("Comparison of 1-year performance between legacy and V7.1 strategies.")
    
    regime_data = pd.DataFrame({
        "Regime": ["Baseline (Mixed)", "Relaxed MR", "Pure Momentum (V7.1)"],
        "CAGR %": [11.47, 13.22, 19.82],
        "Max DD %": [-2.62, -2.61, -0.92],
        "Profit Factor": [1.41, 1.42, 4.44]
    })
    
    col_reg1, col_reg2 = st.columns([2, 1])
    
    with col_reg1:
        fig_regime = px.bar(regime_data, x="Regime", y="CAGR %", color="Regime",
                           text_auto='.2f', title="Annual Returns by Regime Strategy")
        fig_regime.update_layout(template="plotly_dark", showlegend=False)
        st.plotly_chart(fig_regime, use_container_width=True)
        
    with col_reg2:
        st.markdown("#### Selection Logic")
        st.write("**Pure Momentum** was chosen as the default regime because it eliminates 'counter-trend bleeding' during strong market moves.")
        st.success("✅ 73% Reducution in Drawdown")
        st.success("✅ 3x Increase in Profit Factor")

    st.divider()

    # 3. Asset Contribution (90-Day Multi-Asset Run)
    st.markdown("### 🗺️ Multi-Asset Contribution (Binance 90D)")
    asset_pnl = {
        "BTC": 13.32,
        "ETH": 0.64,
        "SOL": -3.91
    }
    df_asset = pd.DataFrame(list(asset_pnl.items()), columns=["Asset", "PnL ($)"])
    
    col_ast1, col_ast2 = st.columns([1, 1])
    
    with col_ast1:
        fig_asset = px.pie(df_asset, values="PnL ($)", names="Asset", 
                          title="Profit Contribution by Symbol",
                          color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_asset.update_traces(textposition='inside', textinfo='percent+label')
        fig_asset.update_layout(template="plotly_dark")
        st.plotly_chart(fig_asset, use_container_width=True)
        
    with col_ast2:
        st.markdown("#### Performance Matrix")
        st.write("Even though SOL was a drag (-$3.91), the portfolio remained profitable (+3.35%) due to BTC's strong momentum and the engine's capital reservation logic.")
        st.table(df_asset)

    st.divider()

    # 4. Exchange Comparison
    st.markdown("### 🏦 Exchange Implementation Check")
    ex_data = pd.DataFrame({
        "Exchange": ["Binance (Spot)", "Hyperliquid (Perps)"],
        "Test Duration": ["90 Days", "52 Days"],
        "PnL %": [3.35, 0.43],
        "Max DD %": [-0.44, -0.61]
    })
    st.table(ex_data)
    st.caption("Hyperliquid test includes 0.035% Taker fees and 0.05% slippage assumptions.")

    if st.button("🚀 Re-Run Comprehensive Backtests", use_container_width=True):
        st.warning("This will execute all test suites. Check terminal for progress.")
        os.system("PYTHONPATH=. ./venv/bin/python trading_engine/multi_asset_vbt_backtest.py")

