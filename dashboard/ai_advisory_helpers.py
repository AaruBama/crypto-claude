"""
AI Advisory Tab Rendering Functions
Separate file for cleaner organization
"""
import streamlit as st
import json
from data.ai_bridge import AIBridge


from data.strategy_router import StrategyRouter
from data.trade_state_manager import TradeStateManager

def render_active_trade_card(active_trade, current_price):
    """
    Renders the Active Position Card
    """
    if not active_trade:
        return

    st.markdown("### 🛡️ Active Position Monitor")
    
    # Calculate PnL
    entry = active_trade['entry_price']
    side = active_trade['side']
    
    if side == "BUY":
        pnl_pct = ((current_price - entry) / entry) * 100
    else:
        pnl_pct = ((entry - current_price) / entry) * 100
        
    pnl_color = "green" if pnl_pct >= 0 else "red"
    
    # Card Container
    with st.container():
        st.info(f"**STRATEGY ACTIVE:** {active_trade.get('strategy_id', 'Unknown')} ({side})")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Entry Price", f"${entry:,.2f}")
        c2.metric("Current Price", f"${current_price:,.2f}")
        c3.metric("PnL %", f"{pnl_pct:+.2f}%", delta=f"{pnl_pct:+.2f}%")
        c4.metric("Stop Loss", f"${active_trade.get('stop_loss', 0):,.2f}")
        
        # Management Actions
        ac1, ac2 = st.columns(2)
        if ac1.button("🛑 Close Trade Now", key="btn_close_trade"):
            TradeStateManager.close_trade(current_price, reason="Manual Dashboard Close")
            st.success("Trade Closed!")
            st.rerun()
            
        if ac2.button("🔧 Tighten Stop Loss (Trailing)", key="btn_update_sl"):
            # Simple simulation: Move SL to Break Even or 1% below current
            # This is a placeholder for more complex logic
            new_sl = entry * 1.001 if side == "BUY" else entry * 0.999
            TradeStateManager.update_stop_loss(new_sl, reason="Manual Tighten")
            st.toast("Stop Loss Updated to Break Even!", icon="🛡️")
            st.rerun()


def render_strategy_signals(df):
    """
    Renders the Strategy Signal Panel (Compact View)
    """
    st.markdown("### 📡 Strategy Signals")
    
    status_list = StrategyRouter.get_strategy_status_for_ui(df)
    
    if not status_list:
        st.info("No sufficient data for strategy signals.")
        return

    # Create a nice summary dataframe
    summary_data = []
    for item in status_list:
        sig = item['signal']
        icon = "🟢" if sig == "bullish" else "🔴" if sig == "bearish" else "⚪"
        summary_data.append({
            "Strategy": item['name'],
            "Signal": f"{icon} {sig.upper()}",
            "Time Ago": item['time_ago'],
            "Description": item['description']
        })
        
    st.dataframe(
        summary_data, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "Strategy": st.column_config.TextColumn("Strategy", width="medium"),
            "Signal": st.column_config.TextColumn("Signal", width="small"),
            "Time Ago": st.column_config.TextColumn("Time", width="small"),
            "Description": st.column_config.TextColumn("Condition", width="large"),
        }
    )

def render_market_context_card(payload):
    """
    Display the market context (Compact)
    """
    if not payload:
        return
    
    st.markdown("### 📊 Market Regime")
    metrics = payload.get("metrics", {})
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Regime", metrics.get("volatility_type", "N/A"))
    c2.metric("Trend", metrics.get("trend", "N/A"))
    c3.metric("ADX", metrics.get("adx", "N/A"))
    
    with st.expander("View Full Context JSON"):
        st.json(payload)

def render_llm_column(llm_name, history_key, unique_key, orchestrator, market_payload):
    """
    Render a single LLM's chat interface in a column
    
    Args:
        llm_name: Name of the LLM ('Claude', 'Gemini', 'Grok')
        history_key: Session state key for this LLM's history
        unique_key: Unique key prefix for widgets
        orchestrator: MultiLLMOrchestrator instance
        market_payload: Current market data
    """
    # Get service and check configuration
    service = orchestrator.get_service(llm_name)
    is_configured = service.is_configured() if service else False
    
    # Header with status
    if is_configured:
        status_icon = "🟢"
        status_text = "Ready"
    else:
        status_icon = "🔴"
        status_text = "Not Configured"
    
    st.markdown(f"### {status_icon} {llm_name}")
    st.caption(f"Status: {status_text}")
    
    if not is_configured:
        st.info(f"💡 To enable {llm_name}, add `{llm_name.upper()}_API_KEY` to your `.env` file and restart the dashboard.")
        return
    
    # Display chat history
    history = st.session_state.get(history_key, [])
    
    for i, message in enumerate(history):
        with st.chat_message(message["role"]):
            # Try to extract and render strategy card
            strategy = service.extract_json(message["content"])
            if strategy and isinstance(strategy, dict) and 'strategy_name' in strategy:
                from dashboard.app import render_strategy_card
                render_strategy_card(strategy, unique_id=f"{unique_key}_{i}")
            else:
                st.markdown(message["content"])
    
    # Chat input for this specific LLM
    if prompt := st.chat_input(f"Ask {llm_name}...", key=f"{unique_key}_input"):
        # Add user message to history
        history.append({"role": "user", "content": prompt})
        st.session_state[history_key] = history
        
        # Query this LLM
        with st.spinner(f"{llm_name} is thinking..."):
            result = orchestrator.query_single(
                llm_name,
                market_payload,
                chat_history=history[:-1],  # Don't include the message we just added
                user_message=prompt
            )
            
            if result["success"]:
                history.append({"role": "assistant", "content": result["response"]})
                st.session_state[history_key] = history
            else:
                # Show error
                error_msg = result.get("error", "Unknown error")
                history.append({"role": "assistant", "content": f"❌ Error: {error_msg}"})
                st.session_state[history_key] = history
        
        st.rerun()


def render_ai_advisory_tab(df, symbol, collector):
    """
    Main AI Advisory tab - queries multiple LLMs in parallel
    """
    st.markdown("## 🤖 AI Advisory")
    
    # Get orchestrator
    if 'llm_orchestrator' not in st.session_state:
         st.error("LLM Orchestrator not initialized")
         return
         
    orchestrator = st.session_state.llm_orchestrator
    
    # Get market payload
    payload = AIBridge.get_market_payload(df, symbol, collector)
    
    if not payload:
        st.error("Unable to generate market data payload")
        return
    
    # 🟢 ACTIVE TRADE CHECK - Full Width Banner
    active_trade = TradeStateManager.get_active_trade()
    if active_trade:
        current_price = df.iloc[-1]['close']
        render_active_trade_card(active_trade, current_price)
        st.markdown("---")

    # 🧠 DYNAMIC INJECTION
    strategy_context = StrategyRouter.get_strategy_context(df)
    payload["_strategy_context_text"] = strategy_context
    
    # Layout: Split Market Context & Signals
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        # Market Context
        render_market_context_card(payload)
        
    with col_right:
        # Signals Table
        render_strategy_signals(df)
        
        # Dev Tools (Compact)
        with st.expander("🛠️ Dev Tools"):
            if st.button("Simulate Long Trade"):
                current_p = df.iloc[-1]['close']
                TradeStateManager.start_trade("9_20_EMA", "BTC/USDT", "BUY", current_p, current_p*0.98, current_p*1.05)
                st.rerun()

    st.markdown("---")
    
    # Check Providers
    configured = orchestrator.get_configured_providers()
    
    if not configured:
        st.warning("⚠️ No AI providers configured. Check .env file.")
        return
    
    # "Ask All Advisors" button
    if st.button("🚀 Ask All Advisors", type="primary", use_container_width=True):
            with st.spinner("Querying all advisors in parallel..."):
                results = orchestrator.query_all(
                    market_payload=payload,
                    chat_histories={
                        "Claude": st.session_state.claude_history,
                        "Gemini": st.session_state.gemini_advisory_history
                    },
                    user_message=None,
                    enabled_providers=configured
                )
                
                # Add responses
                for provider, result in results.items():
                    if provider == "Claude":
                        target_history = st.session_state.claude_history
                    elif provider == "Gemini":
                        target_history = st.session_state.gemini_advisory_history
                    else:
                        continue
                        
                    if result["success"]:
                        target_history.append({"role": "assistant", "content": result["response"]})
                        st.toast(f"✅ {provider} responded", icon="🎯")
                    else:
                        error_msg = result.get("error", "Unknown error")
                        target_history.append({"role": "assistant", "content": f"❌ Error: {error_msg}"})
                
                st.rerun()

    # Clear History Button
    if st.button("🗑️ Clear All Histories"):
        st.session_state.claude_history = []
        st.session_state.gemini_advisory_history = []
        st.rerun()
    
    st.markdown("---")
    
    # Two-column layout for LLM responses
    st.markdown("### 💬 Individual Advisors")
    
    col1, col2 = st.columns(2)
    
    with col1:
        render_llm_column("Claude", "claude_history", "claude_adv", orchestrator, payload)
        
    with col2:
        render_llm_column("Gemini", "gemini_advisory_history", "gemini_adv", orchestrator, payload)
