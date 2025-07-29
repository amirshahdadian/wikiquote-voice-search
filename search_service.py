import logging
from typing import List, Dict, Any
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
from config import Config

# Set up logging
logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL), 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class QuoteSearchService:
    def __init__(self, uri: str, username: str, password: str):
        """Initialize the search service with Neo4j connection."""
        self.uri = uri
        self.username = username
        self.password = password
        self.driver = None
        
    def connect(self):
        """Establish connection to Neo4j database."""
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
            # Test the connection
            with self.driver.session() as session:
                session.run("RETURN 1")
            logger.info("Successfully connected to Neo4j database")
        except AuthError:
            logger.error("Authentication failed. Please check your username and password.")
            raise
        except ServiceUnavailable:
            logger.error("Neo4j service is unavailable. Please check if Neo4j is running.")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise
    
    def close(self):
        """Close the Neo4j connection."""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")
    
    def autocomplete(self, search_term: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for quotes using full-text search with autocomplete functionality.
        
        Args:
            search_term (str): The search term to look for in quotes
            limit (int): Maximum number of results to return (default: 5)
            
        Returns:
            List[Dict[str, Any]]: List of matching quotes with metadata
        """
        if not search_term or not search_term.strip():
            return []
        
        # Clean and prepare the search term for full-text search
        # Add wildcard for prefix matching
        search_query = f"{search_term.strip()}*"
        
        # Cypher query using full-text index
        query = """
        CALL db.index.fulltext.queryNodes('quote_fulltext_index', $search_query)
        YIELD node AS quote, score
        
        // Get the author and source information
        MATCH (author:Author)-[:ATTRIBUTED_TO]->(quote)
        MATCH (quote)-[:APPEARS_IN]->(source:Source)
        
        RETURN quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               score AS relevance_score
        
        ORDER BY score DESC
        LIMIT $limit
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(query, search_query=search_query, limit=limit)
                
                quotes = []
                for record in result:
                    quotes.append({
                        'quote_text': record['quote_text'],
                        'author_name': record['author_name'],
                        'source_title': record['source_title'],
                        'relevance_score': record['relevance_score']
                    })
                
                logger.info(f"Found {len(quotes)} quotes matching '{search_term}'")
                return quotes
                
        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []
    
    def search_by_author(self, author_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for quotes by a specific author.
        
        Args:
            author_name (str): Name of the author to search for
            limit (int): Maximum number of results to return
            
        Returns:
            List[Dict[str, Any]]: List of quotes by the author
        """
        query = """
        MATCH (author:Author)-[:ATTRIBUTED_TO]->(quote:Quote)
        MATCH (quote)-[:APPEARS_IN]->(source:Source)
        WHERE toLower(author.name) CONTAINS toLower($author_name)
        
        RETURN quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title
        
        ORDER BY author.name, quote.text
        LIMIT $limit
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(query, author_name=author_name, limit=limit)
                
                quotes = []
                for record in result:
                    quotes.append({
                        'quote_text': record['quote_text'],
                        'author_name': record['author_name'],
                        'source_title': record['source_title']
                    })
                
                logger.info(f"Found {len(quotes)} quotes by authors matching '{author_name}'")
                return quotes
                
        except Exception as e:
            logger.error(f"Error during author search: {e}")
            return []
    
    def search_by_source(self, source_title: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for quotes from a specific source.
        
        Args:
            source_title (str): Title of the source to search for
            limit (int): Maximum number of results to return
            
        Returns:
            List[Dict[str, Any]]: List of quotes from the source
        """
        query = """
        MATCH (author:Author)-[:ATTRIBUTED_TO]->(quote:Quote)
        MATCH (quote)-[:APPEARS_IN]->(source:Source)
        WHERE toLower(source.title) CONTAINS toLower($source_title)
        
        RETURN quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title
        
        ORDER BY source.title, author.name
        LIMIT $limit
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(query, source_title=source_title, limit=limit)
                
                quotes = []
                for record in result:
                    quotes.append({
                        'quote_text': record['quote_text'],
                        'author_name': record['author_name'],
                        'source_title': record['source_title']
                    })
                
                logger.info(f"Found {len(quotes)} quotes from sources matching '{source_title}'")
                return quotes
                
        except Exception as e:
            logger.error(f"Error during source search: {e}")
            return []

def print_search_results(results: List[Dict[str, Any]], search_term: str):
    """Pretty print search results."""
    if not results:
        print(f"No quotes found for '{search_term}'")
        return
    
    print(f"\n=== SEARCH RESULTS FOR '{search_term}' ===")
    print(f"Found {len(results)} quotes:\n")
    
    for i, quote in enumerate(results, 1):
        print(f"{i}. \"{quote['quote_text']}\"")
        print(f"   - {quote['author_name']} (from {quote['source_title']})")
        if 'relevance_score' in quote:
            print(f"   - Relevance: {quote['relevance_score']:.3f}")
        print()

def main():
    """Demonstration of the search functionality."""
    # Initialize search service using config
    search_service = QuoteSearchService(Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
    
    try:
        # Connect to database
        search_service.connect()
        
        # Example searches
        search_terms = [
            "love",
            "wisdom", 
            "life",
            "imagination",
            "knowledge"
        ]
        
        print("=== WIKIQUOTE SEARCH SERVICE DEMO ===\n")
        
        for term in search_terms:
            results = search_service.autocomplete(term, limit=Config.SEARCH_LIMIT)
            print_search_results(results, term)
            print("-" * 50)
        
        # Example author search
        print("\n=== AUTHOR SEARCH DEMO ===")
        author_results = search_service.search_by_author("Einstein")
        if author_results:
            print(f"\nQuotes by authors matching 'Einstein':")
            for quote in author_results[:3]:  # Show first 3
                print(f"- \"{quote['quote_text']}\" - {quote['author_name']}")
        
        # Example source search
        print("\n=== SOURCE SEARCH DEMO ===")
        source_results = search_service.search_by_source("Star Wars")
        if source_results:
            print(f"\nQuotes from sources matching 'Star Wars':")
            for quote in source_results[:3]:  # Show first 3
                print(f"- \"{quote['quote_text']}\" - {quote['author_name']}")
        
    except Exception as e:
        logger.error(f"Error during search demo: {e}")
    finally:
        search_service.close()

if __name__ == "__main__":
    main()