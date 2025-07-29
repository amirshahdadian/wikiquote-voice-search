import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file first
load_dotenv()

def get_env_var(key: str, default: Optional[str] = None) -> str:
    """Get environment variable with optional default value."""
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Environment variable {key} is required but not set")
    return value

class Config:
    """Configuration class for the Wikiquote Voice Search application."""
    
    # Neo4j Configuration
    NEO4J_URI: str = get_env_var("NEO4J_URI", "neo4j://127.0.0.1:7687")
    NEO4J_USERNAME: str = get_env_var("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD: str = get_env_var("NEO4J_PASSWORD")
    
    # Application Settings
    QUOTES_FILE: str = get_env_var("QUOTES_FILE", "extracted_quotes.json")
    BATCH_SIZE: int = int(get_env_var("BATCH_SIZE", "1000"))
    SEARCH_LIMIT: int = int(get_env_var("SEARCH_LIMIT", "5"))
    LOG_LEVEL: str = get_env_var("LOG_LEVEL", "INFO")
    
    # File paths
    XML_FILE: str = get_env_var("XML_FILE", "enwikiquote-20250601-pages-articles.xml")