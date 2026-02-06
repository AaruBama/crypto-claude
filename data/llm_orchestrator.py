"""
Multi-LLM Orchestrator
Manages parallel queries to multiple LLM providers
"""
import concurrent.futures
from typing import Dict, List, Optional, Any
from data.llm_base import BaseLLMService
from data.llm_claude import ClaudeLLMService
from data.llm_gemini import GeminiLLMService
from data.llm_grok import GrokLLMService


class MultiLLMOrchestrator:
    """
    Orchestrates parallel queries to multiple LLM providers.
    Handles failures gracefully - if one LLM fails, others still return results.
    """
    
    def __init__(self):
        """Initialize orchestrator with all available LLM services"""
        self.services: Dict[str, BaseLLMService] = {
            "Claude": ClaudeLLMService(),
            "Gemini": GeminiLLMService(),
            "Grok": GrokLLMService()
        }
    
    def get_service(self, provider_name: str) -> Optional[BaseLLMService]:
        """
        Get a specific LLM service by name.
        
        Args:
            provider_name: Name of provider ('Claude', 'Gemini', 'Grok')
            
        Returns:
            LLM service instance or None if not found
        """
        return self.services.get(provider_name)
    
    def query_single(
        self,
        provider_name: str,
        market_payload: Dict[str, Any],
        chat_history: Optional[List[Dict[str, str]]] = None,
        user_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query a single LLM provider.
        
        Args:
            provider_name: Name of provider to query
            market_payload: Market data
            chat_history: Chat history for this provider
            user_message: Optional user message
            
        Returns:
            Response dict from the provider
        """
        service = self.get_service(provider_name)
        if service is None:
            return {
                "success": False,
                "response": "",
                "error": f"Unknown provider: {provider_name}",
                "response_time": 0.0
            }
        
        return service.query(market_payload, chat_history, user_message)
    
    def query_all(
        self,
        market_payload: Dict[str, Any],
        chat_histories: Optional[Dict[str, List[Dict[str, str]]]] = None,
        user_message: Optional[str] = None,
        enabled_providers: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Query all enabled LLM providers in parallel.
        
        Args:
            market_payload: Market data to send to all LLMs
            chat_histories: Dict mapping provider name to their chat history
            user_message: Optional user message to send to all
            enabled_providers: List of provider names to query (defaults to all)
            
        Returns:
            Dict mapping provider name to their response dict
        """
        if chat_histories is None:
            chat_histories = {}
        
        if enabled_providers is None:
            enabled_providers = list(self.services.keys())
        
        results = {}
        
        # Use ThreadPoolExecutor for parallel queries
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # Submit all queries
            future_to_provider = {}
            for provider_name in enabled_providers:
                if provider_name in self.services:
                    service = self.services[provider_name]
                    history = chat_histories.get(provider_name, [])
                    
                    future = executor.submit(
                        service.query,
                        market_payload,
                        history,
                        user_message
                    )
                    future_to_provider[future] = provider_name
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_provider):
                provider_name = future_to_provider[future]
                try:
                    result = future.result()
                    results[provider_name] = result
                except Exception as e:
                    # If a provider completely fails, return error result
                    results[provider_name] = {
                        "success": False,
                        "response": "",
                        "error": f"❌ Unexpected error: {str(e)}",
                        "response_time": 0.0
                    }
        
        return results
    
    def get_configured_providers(self) -> List[str]:
        """
        Get list of providers that are properly configured with API keys.
        
        Returns:
            List of provider names that have API keys configured
        """
        configured = []
        for name, service in self.services.items():
            if service.is_configured():
                configured.append(name)
        return configured
    
    def extract_strategy(self, provider_name: str, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Extract strategy JSON from a provider's response.
        
        Args:
            provider_name: Name of the provider
            response_text: Response text to parse
            
        Returns:
            Parsed strategy dict or None
        """
        service = self.get_service(provider_name)
        if service:
            return service.extract_json(response_text)
        return None
