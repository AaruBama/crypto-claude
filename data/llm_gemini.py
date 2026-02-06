"""
Gemini (Google) LLM Service Integration
Refactored from existing ai_bridge.py implementation
"""
import os
import time
from typing import Dict, List, Optional, Any
from data.llm_base import BaseLLMService


class GeminiLLMService(BaseLLMService):
    """
    Gemini AI service implementation using Google Generative AI.
    """
    
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize Gemini service.
        
        Args:
            api_key: Google API key (defaults to GEMINI_API_KEY env var)
            model_name: Model to use (defaults to gemini-2.0-flash-exp)
        """
        if api_key is None:
            api_key = os.getenv("GEMINI_API_KEY")
        
        if model_name is None:
            model_name = "gemini-3-pro-preview"
        
        super().__init__(api_key, model_name)
        
        # Initialize Gemini client if configured
        self.client = None
        if self.is_configured():
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.client = genai.GenerativeModel(self.model_name)
            except ImportError:
                pass  # Will be caught in query method
    
    def _get_provider_name(self) -> str:
        """Return provider name"""
        return "Gemini"
    
    def _format_chat_history(self, chat_history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Convert generic chat history to Gemini's message format.
        
        Args:
            chat_history: List of {role: 'user'|'assistant', content: str}
            
        Returns:
            Gemini-formatted message list
        """
        messages = []
        for msg in chat_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Gemini uses 'user' and 'model' roles
            gemini_role = "model" if role == "assistant" else "user"
            messages.append({
                "role": gemini_role,
                "parts": [content]
            })
        
        return messages
    
    def query(
        self, 
        market_payload: Dict[str, Any],
        chat_history: Optional[List[Dict[str, str]]] = None,
        user_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query Gemini with market data and chat history.
        
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
                "error": "⚠️ Gemini API Key not configured. Please add GEMINI_API_KEY to your .env file.",
                "response_time": 0.0
            }
        
        # Check if client initialized
        if self.client is None:
            return {
                "success": False,
                "response": "",
                "error": "❌ Google Generative AI library not installed. Run: pip install google-generativeai",
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
            
            # Build current instruction
            current_instruction = f"{system_prompt}\n\n{market_context}"
            if user_message:
                current_instruction += f"\n\nUSER'S QUESTION: {user_message}"
            else:
                current_instruction += "\n\nPlease provide a full strategy analysis based on the current data."
            
            # Start chat with history
            chat = self.client.start_chat(history=messages)
            response = chat.send_message(current_instruction)
            
            response_time = time.time() - start_time
            
            return {
                "success": True,
                "response": response.text,
                "error": None,
                "response_time": response_time
            }
            
        except Exception as e:
            response_time = time.time() - start_time
            return {
                "success": False,
                "response": "",
                "error": f"❌ Gemini Error: {str(e)}",
                "response_time": response_time
            }
