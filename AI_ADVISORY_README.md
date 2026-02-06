# Multi-LLM Advisory System

## Quick Start Guide

### What is This?

A new feature that lets you query **multiple AI models simultaneously** (Claude, Gemini, Grok) to get diverse perspectives on crypto trading decisions. Each AI maintains its own conversation history so you can have ongoing discussions with each advisor.

### How to Enable

1. **Add Your Claude API Key**
   
   Edit `.env` file:
   ```bash
   CLAUDE_API_KEY=sk-ant-your-actual-key-here
   ```
   
   Get your key from: https://console.anthropic.com/

2. **Restart the Dashboard**
   ```bash
   # Stop current dashboard (Ctrl+C)
   streamlit run dashboard/app.py
   ```

3. **Navigate to AI Advisory Tab**
   
   Click the **🤖 AI Advisory** tab (third tab in dashboard)

### How to Use

**Ask All Advisors at Once:**
1. Review the market context card (shows current data)
2. Click "🚀 Ask All Advisors"
3. All configured AIs respond in parallel
4. Compare their different perspectives

**Chat with Individual Advisors:**
- Each column has its own chat input
- Ask follow-up questions to specific AIs
- Each maintains separate conversation context

**Execute Strategies:**
- If an AI suggests a trade (JSON format), a strategy card appears
- Edit parameters (entry, stop loss, take profit, etc.)
- Click "🚀 Execute" to place the trade

### Current Status

- ✅ **Gemini**: Already working (your API key is configured)
- ⚠️ **Claude**: Add your API key to enable
- ⚠️ **Grok**: Optional, for future use when X.AI API is available

### Features

- **Parallel Queries**: All AIs respond simultaneously (faster than sequential)
- **Independent Histories**: Each AI remembers its own conversation
- **Strategy Cards**: Auto-render when AIs suggest trades
- **Graceful Errors**: If one AI fails, others still work
- **Market Context**: Shows exactly what data is being sent to AIs

### Architecture

```
Dashboard → Orchestrator → [Claude, Gemini, Grok] → Parallel Responses
                ↓
         Chat Histories (session state)
```

### Files Added

**Backend Services:**
- `data/llm_base.py` - Base class for all LLMs
- `data/llm_claude.py` - Claude integration
- `data/llm_gemini.py` - Gemini integration
- `data/llm_grok.py` - Grok placeholder
- `data/llm_orchestrator.py` - Parallel query manager

**UI:**
- `dashboard/ai_advisory_helpers.py` - Tab rendering

**Config:**
- `.env` - Updated with Claude/Grok placeholders
- `requirements.txt` - Added `anthropic` package

### Troubleshooting

**"Claude not configured" message:**
- Add your Claude API key to `.env`
- Restart the dashboard

**Responses are slow:**
- This is normal for first query (cold start)
- Subsequent queries are faster
- Parallel execution is still faster than asking each AI separately

**Chat history disappeared:**
- Histories persist through auto-refresh (10s interval)
- Manual browser refresh clears histories (expected)
- Click "🗑️ Clear All Histories" to reset intentionally

### Next Steps

See [walkthrough.md](file:///Users/rv/.gemini/antigravity/brain/46e25bf6-80d3-44b0-883b-1ee8820ad04b/walkthrough.md) for detailed implementation documentation.
