"""
Base class for LLM service integrations.
Provides a common interface for different AI providers.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import json
import re


class BaseLLMService(ABC):
    """
    Abstract base class for LLM service providers.
    Each provider (Claude, Gemini, Grok) implements this interface.
    """
    
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize the LLM service.
        
        Args:
            api_key: API key for the service
            model_name: Specific model to use (provider-specific)
        """
        self.api_key = api_key
        self.model_name = model_name
        self.provider_name = self._get_provider_name()
    
    @abstractmethod
    def _get_provider_name(self) -> str:
        """Return the name of this provider (e.g., 'Claude', 'Gemini', 'Grok')"""
        pass
    
    @abstractmethod
    def query(
        self, 
        market_payload: Dict[str, Any],
        chat_history: Optional[List[Dict[str, str]]] = None,
        user_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query the LLM with market data and optional chat history.
        
        Args:
            market_payload: Market data formatted as JSON
            chat_history: Previous conversation history
            user_message: Optional user question/message
            
        Returns:
            Dict with:
                - success: bool
                - response: str (AI response text)
                - error: Optional[str]
                - response_time: float (seconds)
        """
        pass
    
    def get_system_prompt(self) -> str:
        """
        Get the system prompt for trading analysis.
        Can be overridden by subclasses for provider-specific prompts.
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
    
    def extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSON strategy object from AI response text.
        
        Args:
            text: AI response text that may contain JSON
            
        Returns:
            Parsed JSON dict or None if not found/invalid
        """
        try:
            # Look for JSON block in the text
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            # Try parsing entire text as JSON
            return json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            return None
    
    def format_market_context(self, market_payload: Dict[str, Any]) -> str:
        """
        Format market payload into readable context string.
        
        Args:
            market_payload: Market data dict
            
        Returns:
            Formatted string for LLM context
        """
        return f"CURRENT MARKET DATA:\n{json.dumps(market_payload, indent=2)}"
    
    def is_configured(self) -> bool:
        """
        Check if this service is properly configured with API key.
        
        Returns:
            True if API key is set, False otherwise
        """
        return self.api_key is not None and len(self.api_key) > 0
