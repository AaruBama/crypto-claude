"""
Claude (Anthropic) LLM Service Integration
"""
import os
import time
from typing import Dict, List, Optional, Any
from data.llm_base import BaseLLMService


class ClaudeLLMService(BaseLLMService):
    """
    Claude AI service implementation using Anthropic API.
    Supports Claude 3.5 Sonnet for trading analysis.
    """
    
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize Claude service.
        
        Args:
            api_key: Anthropic API key (defaults to CLAUDE_API_KEY env var)
            model_name: Model to use (defaults to claude-3-5-sonnet-20241022)
        """
        if api_key is None:
            api_key = os.getenv("CLAUDE_API_KEY")
        
        if model_name is None:
            model_name = "claude-sonnet-4-5"
        
        super().__init__(api_key, model_name)
        
        # Initialize Anthropic client if configured
        self.client = None
        if self.is_configured():
            try:
                from anthropic import Anthropic
                self.client = Anthropic(api_key=self.api_key)
            except ImportError:
                pass  # Will be caught in query method
    
    def _get_provider_name(self) -> str:
        """Return provider name"""
        return "Claude"
    
    def _format_chat_history(self, chat_history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Convert generic chat history to Claude's message format.
        
        Args:
            chat_history: List of {role: 'user'|'assistant', content: str}
            
        Returns:
            Claude-formatted message list
        """
        messages = []
        for msg in chat_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Claude uses 'user' and 'assistant' roles
            if role in ["user", "assistant"]:
                messages.append({
                    "role": role,
                    "content": content
                })
        
        return messages
    
    def query(
        self, 
        market_payload: Dict[str, Any],
        chat_history: Optional[List[Dict[str, str]]] = None,
        user_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query Claude with market data and chat history.
        
        Args:
            market_payload: Market data as dict
            chat_history: Previous conversation
            user_message: Optional user question
            
        Returns:
            Response dict with success, response, error, response_time
        """
        start_time = time.time()
        
        # Check if configured
        if not self.is_configured():
            return {
                "success": False,
                "response": "",
                "error": "⚠️ Claude API Key not configured. Please add CLAUDE_API_KEY to your .env file.",
                "response_time": 0.0
            }
        
        # Check if client initialized
        if self.client is None:
            return {
                "success": False,
                "response": "",
                "error": "❌ Anthropic library not installed. Run: pip install anthropic",
                "response_time": 0.0
            }
        
        try:
            # Build message context
            system_prompt = self.get_system_prompt()
            market_context = self.format_market_context(market_payload)
            
            # Format chat history
            messages = []
            if chat_history:
                messages = self._format_chat_history(chat_history)
            
            # Build current user message
            current_message = market_context
            if user_message:
                current_message += f"\n\nUSER'S QUESTION: {user_message}"
            else:
                current_message += "\n\nPlease provide a full strategy analysis based on the current data."
            
            messages.append({
                "role": "user",
                "content": current_message
            })
            
            # Call Claude API
            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=2048,
                system=system_prompt,
                messages=messages
            )
            
            # Extract response text
            response_text = response.content[0].text
            
            response_time = time.time() - start_time
            
            return {
                "success": True,
                "response": response_text,
                "error": None,
                "response_time": response_time
            }
            
        except Exception as e:
            response_time = time.time() - start_time
            return {
                "success": False,
                "response": "",
                "error": f"❌ Claude Error: {str(e)}",
                "response_time": response_time
            }
