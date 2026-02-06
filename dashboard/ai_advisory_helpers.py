"""
AI Advisory Tab Rendering Functions
Separate file for cleaner organization
"""
import streamlit as st
import json
from data.ai_bridge import AIBridge


def render_market_context_card(payload):
    """
    Display the market context being sent to LLMs
    """
    if not payload:
        st.warning("No market data available")
        return
    
    st.markdown("### 📊 Current Market Context")
    st.caption("This data is being sent to all AI advisors")
    
    with st.expander("View Market Data JSON", expanded=False):
        st.json(payload)
    
    # Quick summary
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Pair", payload.get("pair", "N/A"))
    with col2:
        st.metric("Price", f"${payload.get('price', 0):,.2f}")
    with col3:
        metrics = payload.get("metrics", {})
        st.metric("RSI", metrics.get("RSI", "N/A"))
    with col4:
        st.metric("Trend", metrics.get("trend", "N/A"))


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
    st.markdown("## 🤖 Multi-LLM Advisory System")
    st.caption("Get diverse perspectives from multiple AI models on the same market data")
    
    # Get orchestrator
    orchestrator = st.session_state.llm_orchestrator
    
    # Get market payload
    payload = AIBridge.get_market_payload(df, symbol, collector)
    
    if not payload:
        st.error("Unable to generate market data payload")
        return
    
    # Show market context
    render_market_context_card(payload)
    
    st.markdown("---")
    
    # Check which providers are configured
    configured = orchestrator.get_configured_providers()
    
    if not configured:
        st.warning("⚠️ No AI providers are configured. Please add API keys to your `.env` file:")
        st.code("""
# Add to .env file:
CLAUDE_API_KEY=your_claude_key_here
GEMINI_API_KEY=your_gemini_key_here
GROK_API_KEY=your_grok_key_here  # Optional
        """)
        return
    
    st.success(f"✅ Configured providers: {', '.join(configured)}")
    
    # "Ask All Advisors" button
    col_btn1, col_btn2, col_spacer = st.columns([2, 2, 6])
    
    with col_btn1:
        if st.button("🚀 Ask All Advisors", type="primary", use_container_width=True):
            with st.spinner("Querying all advisors in parallel..."):
                # Query all configured LLMs
                results = orchestrator.query_all(
                    market_payload=payload,
                    chat_histories={
                        "Claude": st.session_state.claude_history,
                        "Gemini": st.session_state.gemini_advisory_history,
                        "Grok": st.session_state.grok_history
                    },
                    user_message=None,  # No specific question, just analyze
                    enabled_providers=configured
                )
                
                # Add responses to histories
                for provider, result in results.items():
                    if provider == "Claude":
                        history_key = "claude_history"
                    elif provider == "Gemini":
                        history_key = "gemini_advisory_history"
                    elif provider == "Grok":
                        history_key = "grok_history"
                    else:
                        continue
                    
                    if result["success"]:
                        st.session_state[history_key].append({
                            "role": "assistant",
                            "content": result["response"]
                        })
                        st.toast(f"✅ {provider} responded in {result['response_time']:.1f}s", icon="🎯")
                    else:
                        error_msg = result.get("error", "Unknown error")
                        st.session_state[history_key].append({
                            "role": "assistant",
                            "content": f"❌ Error: {error_msg}"
                        })
                
                st.rerun()
    
    with col_btn2:
        if st.button("🗑️ Clear All Histories", use_container_width=True):
            st.session_state.claude_history = []
            st.session_state.gemini_advisory_history = []
            st.session_state.grok_history = []
            st.rerun()
    
    st.markdown("---")
    
    # Three-column layout for LLM responses
    st.markdown("### 💬 Individual Advisors")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        render_llm_column("Claude", "claude_history", "claude", orchestrator, payload)
    
    with col2:
        render_llm_column("Gemini", "gemini_advisory_history", "gemini_adv", orchestrator, payload)
    
    with col3:
        render_llm_column("Grok", "grok_history", "grok", orchestrator, payload)
