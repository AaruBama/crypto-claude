import json
import os
import google.generativeai as genai
from data.indicators import IndicatorCalculator
from dotenv import load_dotenv

# Load environment variables (for API key)
load_dotenv()

class AIBridge:
    """
    Phase 1: The 'Translator' & Connector
    Connects dashboard data to real AI models (Gemini).
    """
    VERSION = "2.1"
    
    @staticmethod
    def get_market_payload(df, symbol, collector=None):
        """
        Grabs current values and formats them into a JSON object.
        """
        if df is None or len(df) == 0:
            return None
            
        latest = df.iloc[-1]
        regime = IndicatorCalculator.calculate_market_regime(df)
        trend = IndicatorCalculator.calculate_trend_direction(df)
        
        payload = {
            "pair": symbol,
            "price": round(float(latest['close']), 2),
            "metrics": {
                "RSI": round(float(latest.get('rsi', 50)), 1),
                "volatility_type": regime.capitalize(),
                "trend": trend.upper(),
                "adx": round(float(latest.get('adx', 0)), 1),
                "volume_vs_avg": f"{latest.get('volume_ratio', 1):.1f}x",
            }
        }
        
        # Add funding from collector if available
        if collector:
            try:
                futures_symbol = symbol.replace('USDT', '') + 'USDT'
                funding_data = collector.get_funding_rate(futures_symbol)
                if funding_data:
                    payload["metrics"]["funding_rate"] = f"{funding_data['funding_rate'] * 100:.4f}%"
            except:
                pass
                
        return payload

    @staticmethod
    def get_system_prompt():
        """
        The 'Handshake' System Prompt (Blueprint Edition)
        Now with Automated Profit Booking logic.
        """
        return (
            "You are an expert Crypto Trading Mentor and Algorithmic Architect. Your goal is to analyze "
            "market data and generate safe, logical trading strategies for a user.\n\n"
            "### YOUR INPUTS:\n"
            "You will receive a JSON object containing technical indicators (RSI, Volatility, Trend, Funding Rate, etc.) for a specific crypto asset.\n\n"
            "### YOUR OUTPUT:\n"
            "If a trade strategy is appropriate, you must include a strictly formatted JSON object matching the schema below within your message. "
            "You are encouraged to provide a brief, conversational introduction or explanation *before* the JSON block. "
            "If the user is just asking a question or the situation is too dangerous, you can respond with just text (no JSON).\n\n"
            "### GUIDELINES:\n"
            "1. **Analyze First:** Look at Volatility (ATR) and Trend (ADX).\n"
            "   - If Volatility is HIGH and Trend is WEAK -> Suggest 'Mean Reversion' (Buy low, Sell high).\n"
            "   - If Volatility is LOW and Trend is STRONG -> Suggest 'Trend Following' (Ride the wave).\n\n"
            "2. **Risk Management & Profit Booking:**\n"
            "   - ALWAYS set a **Stop Loss**.\n"
            "   - **Take Profit (Static):** Set a specific target price.\n"
            "   - **Trailing Stop (%):** (Optional) Set a % (e.g. 2.5) that follows the price up.\n"
            "   - **Scaling Out:** (Optional) Provide a list of prices to sell 50% / 25% etc.\n\n"
            "3. **Speak Human:**\n"
            "   - In the 'rationale' field, explain your logic in plain English. Avoid raw jargon.\n\n"
            "### JSON FORMAT:\n"
            "{\n"
            "  \"strategy_name\": \"Name of Strategy\",\n"
            "  \"action\": \"BUY/SELL/WAIT\",\n"
            "  \"confidence_score\": 7,\n"
            "  \"rationale\": \"Plain English explanation...\",\n"
            "  \"trade_params\": {\n"
            "    \"symbol\": \"BTC/USDT\",\n"
            "    \"entry_price\": 64000,\n"
            "    \"stop_loss\": 62500,\n"
            "    \"take_profit\": 67000,\n"
            "    \"trailing_stop_percent\": 2.5,\n"
            "    \"scaling_targets\": [66000, 68000]\n"
            "  }\n"
            "}\n"
        )

    @staticmethod
    def consult_mentor(payload, chat_history=None, user_message=None):
        """
        Consults the actual Gemini AI model with full conversational context.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return "⚠️ Gemini API Key not found."

        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-3-pro-preview')
            
            system_prompt = AIBridge.get_system_prompt()
            market_context = f"CURRENT MARKET DATA:\n{json.dumps(payload, indent=2)}"
            
            messages = []
            if chat_history:
                for msg in chat_history:
                    # Filter out purely structural JSON from history if needed, 
                    # but usually, keeping it helps the AI see past decisions
                    role = "user" if msg["role"] == "user" else "model"
                    messages.append({"role": role, "parts": [msg["content"]]})

            current_instruction = f"{system_prompt}\n\n{market_context}"
            if user_message:
                current_instruction += f"\n\nUSER'S QUESTION: {user_message}"
            else:
                current_instruction += "\n\nPlease provide a full strategy analysis based on the current data."

            chat = model.start_chat(history=messages)
            response = chat.send_message(current_instruction)
            
            return response.text
        except Exception as e:
            return f"❌ Error: {str(e)}"

    @staticmethod
    def extract_json(text):
        """
        Helper to pull JSON out of AI text responses
        """
        try:
            # Look for JSON block
            import re
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return json.loads(text)
        except:
            return None
