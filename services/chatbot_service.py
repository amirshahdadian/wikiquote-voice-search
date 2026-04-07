"""
Chatbot Service for conversational quote search
"""

import logging
import re
from typing import Any, Dict, List, Optional
from src.wikiquote_voice.search.service import QuoteSearchService
from src.wikiquote_voice.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatbotService:
    """
    Conversational chatbot for searching quotes
    Uses natural language understanding to extract search intent
    """
    
    def __init__(self):
        """Initialize chatbot with search service and warmup hook."""
        logger.info("Initializing Chatbot service...")
        self.search_service = QuoteSearchService(
            Config.NEO4J_URI,
            Config.NEO4J_USERNAME,
            Config.NEO4J_PASSWORD
        )
        self.search_service.connect()
        
        # Placeholder warmup hook; no semantic index is built in current service.
        logger.info("🔨 Running search warmup for chatbot...")
        self.search_service.build_semantic_index(sample_size=10000)
        logger.info("✅ Chatbot service initialized")
    
    def extract_intent(self, message: str) -> Dict[str, Any]:
        """
        Extract search intent from user message
        
        Args:
            message: User's message
            
        Returns:
            dict with intent type and parameters
        """
        message_lower = message.lower().strip()

        quote_lookup_match = re.search(r'who (?:said|wrote)\s+(.+)', message_lower)
        if quote_lookup_match:
            quote_fragment = quote_lookup_match.group(1).strip()
            quote_fragment = re.sub(r'[?.!,;]+$', '', quote_fragment).strip()
            if quote_fragment:
                logger.info(f"Extracted quote lookup fragment: '{quote_fragment}' from message: '{message}'")
                return {
                    'type': 'topic_search',
                    'query': quote_fragment,
                    'limit': 5
                }
        
        # Check for topic search first (more specific patterns)
        topic_patterns = [
            # "something/anything about X"
            r'(?:something|anything|quotes?)\s+(?:about|on|regarding)\s+(.+)',
            # "what did X say" / "what has X said" — author pattern handled below; topic fallback
            r'(?:find|search|show|get|give me|looking for|want|need)\s+(?:some\s+)?quotes?\s+(?:about|on|regarding)\s+(.+)',
            r'(?:please\s+)?(?:find|get|show)\s+(?:me\s+)?(?:some\s+)?quotes?\s+(?:about|on|regarding)\s+(.+)',
            r'quotes?\s+(?:about|on|regarding)\s+(.+)',
            r'(?:what are|tell me)\s+(?:some\s+)?quotes?\s+(?:about|on|regarding)\s+(.+)',
            # bare "about X" / "on X"
            r'^(?:about|on)\s+(.+)',
        ]
        
        for pattern in topic_patterns:
            match = re.search(pattern, message_lower)
            if match:
                topic = match.group(1).strip()
                # Remove trailing punctuation and common words
                topic = re.sub(r'[?.!,;]+$', '', topic).strip()
                topic = re.sub(r'\b(quotes?|please)\b', '', topic).strip()
                if topic and len(topic) > 1:
                    logger.info(f"Extracted topic: '{topic}' from message: '{message}'")
                    return {
                        'type': 'topic_search',
                        'query': topic,
                        'limit': 5
                    }
        
        # Check for author search (only if no "about" keyword)
        if 'about' not in message_lower and 'regarding' not in message_lower:
            author_patterns = [
                # "what did Einstein say/write" / "what has X said"
                r'what\s+(?:did|has|have)\s+(.+?)\s+(?:say|said|write|written|wrote)',
                r'(?:show me|find|get)\s+(.+?)(?:\'s)?\s+quotes?',
                r'(.+?)(?:\'s)?\s+quotes?$',
                r'quotes?\s+(?:by|from)\s+(.+)',
            ]
            
            for pattern in author_patterns:
                match = re.search(pattern, message_lower)
                if match:
                    author_name = match.group(1).strip()
                    # Clean up common words
                    author_name = re.sub(r'\b(quotes?|the|some|me)\b', '', author_name).strip()
                    # Check if it's likely an author name (contains letters and possibly spaces)
                    if author_name and len(author_name) > 2 and not any(word in author_name for word in ['about', 'on', 'regarding']):
                        logger.info(f"Extracted author: '{author_name}' from message: '{message}'")
                        return {
                            'type': 'author_search',
                            'author': author_name.title(),
                            'limit': 5
                        }
        
        # Default to keyword search with the whole message
        logger.info(f"Using default keyword search for: '{message}'")
        return {
            'type': 'topic_search',
            'query': message,
            'limit': 5
        }
    
    def format_quote_response(self, quotes: List[Dict], query_type: str = "quote") -> str:
        """
        Format quotes into a readable response
        
        Args:
            quotes: List of quote dictionaries
            query_type: Type of query (for response formatting)
            
        Returns:
            Formatted response string
        """
        if not quotes:
            return "I couldn't find any quotes matching your request. Try asking about a different topic or author!"
        
        response_parts = []
        
        if len(quotes) == 1:
            response_parts.append("Here you go. Here's a quote")
        else:
            response_parts.append(f"Here are {len(quotes)} quotes")
        
        if query_type == "author":
            response_parts.append(f"by {quotes[0].get('author_name', 'this author')}")
        elif query_type == "topic":
            response_parts.append("for that topic")
        
        response = " ".join(response_parts) + ":\n\n"
        
        for i, quote in enumerate(quotes, 1):
            quote_text = quote.get('quote_text', 'N/A')
            author_name = quote.get('author_name', 'Unknown')
            source_title = quote.get('source_title', 'Unknown source')
            
            response += f"{i}. \"{quote_text}\" — {author_name}"
            if source_title and source_title != 'Unknown source':
                response += f" ({source_title})"
            response += "\n\n"
        
        return response.strip()
    
    def process_message(self, message: str) -> str:
        """
        Process user message and return chatbot response
        
        Args:
            message: User's input message
            
        Returns:
            Chatbot's response
        """
        logger.info(f"Processing message: '{message}'")
        
        try:
            # Extract intent
            intent = self.extract_intent(message)
            logger.info(f"Extracted intent: {intent}")
            
            # Search based on intent
            if intent['type'] == 'author_search':
                quotes = self.search_service.search_by_author(
                    intent['author'],
                    limit=intent['limit']
                )
                response = self.format_quote_response(quotes, query_type="author")
            else:  # topic_search
                # USE VOICE_SEARCH which applies hybrid similarity + filters long text
                quotes = self.search_service.voice_search(
                    intent['query'],
                    limit=intent['limit']
                )
                response = self.format_quote_response(quotes, query_type="topic")
            
            logger.info(f"Response: {response[:100]}...")
            return response
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return f"Sorry, I encountered an error while searching: {str(e)}"
    
    def close(self):
        """Close search service connection"""
        if self.search_service:
            self.search_service.close()
