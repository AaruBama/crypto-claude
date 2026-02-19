
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def render_strategy_lab():
    st.markdown("## 🧪 Strategy Lab: Optimization & Backtesting")
    st.info("Train on the past, validate on the unknown. This lab uses Walk-Forward Optimization to prevent curve-fitting.")

    # Asset Selector
    selected_asset = st.selectbox("Select Asset to Analyze", ["BTC_USDT", "SOL_USDT"], index=0)

    # 1. Backtest Results Selection
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 📊 Performance Summary")
        equity_file = "data/backtests/equity_curve.csv" 
        
        # Use symbol-specific files for optimization results
        gs_file = f"data/backtests/grid_search_{selected_asset}.csv"
        wf_file = f"data/backtests/walk_forward_{selected_asset}.csv"
        
        if os.path.exists(equity_file):
            df_equity = pd.read_csv(equity_file)
            df_equity['time'] = pd.to_datetime(df_equity['time'])
            
            # Interactive Equity Curve
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_equity['time'], y=df_equity['equity'], mode='lines', name='Equity', line=dict(color='#00ff00')))
            fig.update_layout(title="Equity Growth Curve (Last Run)", template="plotly_dark", height=400, xaxis_title="Time", yaxis_title="Balance ($)")
            st.plotly_chart(fig, use_container_width=True)
            
            # Drawdown Analysis
            df_equity['max_equity'] = df_equity['equity'].cummax()
            df_equity['drawdown'] = (df_equity['equity'] - df_equity['max_equity']) / df_equity['max_equity'] * 100
            
            st.markdown("#### 📉 Top 5 Drawdowns")
            dd_df = df_equity[['time', 'drawdown']].sort_values('drawdown').head(5)
            st.table(dd_df.style.format({'drawdown': '{:.2f}%'}))
        else:
            st.warning("No main backtest data found. Run a backtest first.")

    with col2:
        st.markdown("### 🔍 Parameter Heatmap")
        if os.path.exists(gs_file):
            df_gs = pd.read_csv(gs_file)
            # Heatmap of Risk:Reward vs PnL
            fig_hm = px.bar(df_gs, x='risk_reward', y='final_pnl', color='win_rate', 
                            title=f"R:R Efficiency for {selected_asset}",
                            labels={'final_pnl': 'Net Profit ($)', 'risk_reward': 'Risk:Reward Ratio'},
                            color_continuous_scale='RdYlGn')
            fig_hm.update_layout(template="plotly_dark", height=400)
            st.plotly_chart(fig_hm, use_container_width=True)
        else:
            st.info(f"Run Grid Search for {selected_asset} to see analysis.")

    st.divider()

    # 2. Walk-Forward Visualization
    st.markdown("### 🏃 Walk-Forward Validation Scoreboard")
    if os.path.exists(wf_file):
        df_wf = pd.read_csv(wf_file)
        
        col_wf1, col_wf2 = st.columns([2, 1])
        with col_wf1:
            fig_wf = px.line(df_wf, x='period', y='test_pnl', markers=True, 
                             title="Out-of-Sample Performance (The Truth Test)")
            fig_wf.add_hline(y=0, line_dash="dash", line_color="white")
            fig_wf.update_layout(template="plotly_dark")
            st.plotly_chart(fig_wf, use_container_width=True)
        
        with col_wf2:
            st.markdown("#### Period Insights")
            for i, row in df_wf.iterrows():
                st.write(f"**{row['period']}**")
                st.write(f"Best R:R: `x{row['best_rr']}` | PnL: `${row['test_pnl']:.2f}`")
                st.progress(max(0, min(1.0, (row['test_pnl'] + 100) / 200))) # Normalized feel
    else:
        st.info(f"Run Walk-Forward Optimization for {selected_asset} to see validation results.")

    st.divider()
    
    # 3. Optimization Controls
    st.markdown("### ⚙️ Optimization Controls")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🚀 Run Full Optimization (BTC)", use_container_width=True):
            with st.spinner("Running 90-day Walk-Forward..."):
                os.system("export PYTHONPATH=$PYTHONPATH:. && venv/bin/python3 trading_engine/optimization_engine.py --symbol BTC/USDT")
                st.success("Optimization Complete!")
                st.rerun()
    with c2:
        if st.button("🚀 Run Full Optimization (SOL)", use_container_width=True):
            with st.spinner("Running 90-day Walk-Forward..."):
                os.system("export PYTHONPATH=$PYTHONPATH:. && venv/bin/python3 trading_engine/optimization_engine.py --symbol SOL/USDT")
                st.success("Optimization Complete!")
                st.rerun()
    with c3:
        if st.button("🗑️ Reset All Reports", use_container_width=True):
            # Clean all files in data/backtests
            bt_dir = "data/backtests/"
            for f in os.listdir(bt_dir):
                os.remove(os.path.join(bt_dir, f))
            st.rerun()
