import json
import logging
from typing import List, Dict, Any
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
import sys
from pathlib import Path

# Add parent directory to path for src imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wikiquote_voice import Config


# Set up logging
logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL), 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Neo4jPopulator:
    def __init__(self, uri: str, username: str, password: str):
        """Initialize Neo4j connection."""
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
    
    def clear_database(self):
        """Clear all nodes and relationships from the database."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        logger.info("Database cleared")
    
    def create_constraints(self):
        """Create unique constraints for better performance and data integrity."""
        constraints = [
            "CREATE CONSTRAINT author_name_unique IF NOT EXISTS FOR (a:Author) REQUIRE a.name IS UNIQUE",
            "CREATE CONSTRAINT source_title_unique IF NOT EXISTS FOR (s:Source) REQUIRE s.title IS UNIQUE",
            "CREATE CONSTRAINT page_title_unique IF NOT EXISTS FOR (p:Page) REQUIRE p.title IS UNIQUE",
            "CREATE CONSTRAINT quote_fingerprint_unique IF NOT EXISTS FOR (q:Quote) REQUIRE q.fingerprint IS UNIQUE",
            "CREATE CONSTRAINT occurrence_key_unique IF NOT EXISTS FOR (o:QuoteOccurrence) REQUIRE o.key IS UNIQUE",
        ]
        
        with self.driver.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                    logger.info(f"Created constraint: {constraint}")
                except Exception as e:
                    logger.warning(f"Constraint may already exist: {e}")
    
    def populate_quotes(self, quotes: List[Dict[str, Any]], batch_size: int = 1000):
        """Populate the Neo4j database with quotes, authors, and sources."""
        logger.info(f"Starting to populate database with {len(quotes)} quotes")
        
        # Create constraints first
        self.create_constraints()
        
        # Process quotes in batches for better performance
        for i in range(0, len(quotes), batch_size):
            batch = quotes[i:i + batch_size]
            self._process_batch(batch, i // batch_size + 1, len(quotes) // batch_size + 1)
        
        logger.info("Database population completed")
    
    def _process_batch(self, batch: List[Dict[str, Any]], batch_num: int, total_batches: int):
        """Process a batch of quotes."""
        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} quotes)")
        
        with self.driver.session() as session:
            # Cypher query to create nodes and relationships
            query = """
            UNWIND $quotes AS quote_data

            WITH quote_data,
                 CASE
                    WHEN quote_data.author IS NULL OR trim(quote_data.author) = '' THEN 'Unknown author'
                    ELSE quote_data.author
                 END AS author_name,
                 CASE
                    WHEN quote_data.source IS NULL OR trim(quote_data.source) = '' THEN 'Unknown source'
                    ELSE quote_data.source
                 END AS source_title

            MERGE (author:Author {name: author_name})
            MERGE (source:Source {title: source_title})
            MERGE (page:Page {title: quote_data.page_title})

            MERGE (quote:Quote {fingerprint: quote_data.quote_fingerprint})
              ON CREATE SET
                quote.text = quote_data.quote,
                quote.canonical_text = coalesce(quote_data.canonical_quote, quote_data.quote),
                quote.page_type = quote_data.page_type,
                quote.quote_type = quote_data.quote_type,
                quote.primary_author = author_name,
                quote.primary_source = source_title,
                quote.primary_page = quote_data.page_title,
                quote.work = quote_data.work,
                quote.year = quote_data.year,
                quote.original_text = quote_data.original_text
              ON MATCH SET
                quote.work = coalesce(quote.work, quote_data.work),
                quote.year = coalesce(quote.year, quote_data.year),
                quote.original_text = coalesce(quote.original_text, quote_data.original_text)

            MERGE (occurrence:QuoteOccurrence {key: quote_data.occurrence_key})
              ON CREATE SET
                occurrence.page_title = quote_data.page_title,
                occurrence.page_type = quote_data.page_type,
                occurrence.context = quote_data.context,
                occurrence.citation = quote_data.citation,
                occurrence.source_locator = quote_data.source_locator,
                occurrence.work = quote_data.work,
                occurrence.year = quote_data.year,
                occurrence.quote_type = quote_data.quote_type

            MERGE (author)-[:ATTRIBUTED_TO]->(quote)
            MERGE (quote)-[:APPEARS_IN]->(source)
            MERGE (quote)-[:EXTRACTED_FROM]->(page)
            MERGE (quote)-[:HAS_OCCURRENCE]->(occurrence)
            MERGE (occurrence)-[:FOUND_ON_PAGE]->(page)
            MERGE (occurrence)-[:CITED_AS]->(source)
            """
            
            try:
                session.run(query, quotes=batch)
                logger.info(f"Successfully processed batch {batch_num}")
            except Exception as e:
                logger.error(f"Error processing batch {batch_num}: {e}")
                raise
    
    def get_database_stats(self) -> Dict[str, int]:
        """Get statistics about the populated database."""
        with self.driver.session() as session:
            stats = {}
            
            # Count nodes
            result = session.run("MATCH (a:Author) RETURN count(a) as count")
            stats['authors'] = result.single()['count']
            
            result = session.run("MATCH (q:Quote) RETURN count(q) as count")
            stats['quotes'] = result.single()['count']
            
            result = session.run("MATCH (s:Source) RETURN count(s) as count")
            stats['sources'] = result.single()['count']

            result = session.run("MATCH (p:Page) RETURN count(p) as count")
            stats['pages'] = result.single()['count']

            result = session.run("MATCH (o:QuoteOccurrence) RETURN count(o) as count")
            stats['occurrences'] = result.single()['count']
            
            # Count relationships
            result = session.run("MATCH ()-[r:ATTRIBUTED_TO]->() RETURN count(r) as count")
            stats['attributed_to_relationships'] = result.single()['count']
            
            result = session.run("MATCH ()-[r:APPEARS_IN]->() RETURN count(r) as count")
            stats['appears_in_relationships'] = result.single()['count']
            
            return stats

def load_quotes_from_json(file_path: str) -> List[Dict[str, Any]]:
    """Load quotes from JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            quotes = json.load(f)
        logger.info(f"Loaded {len(quotes)} quotes from {file_path}")
        return quotes
    except FileNotFoundError:
        logger.error(f"JSON file not found: {file_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format: {e}")
        raise

def main():
    """Main function to populate the Neo4j database."""
    # Load quotes from JSON
    quotes = load_quotes_from_json(Config.QUOTES_FILE)
    
    if not quotes:
        logger.error("No quotes loaded. Please run parse_wikitext.py first.")
        return
    
    # Initialize Neo4j populator using config
    populator = Neo4jPopulator(Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
    
    try:
        # Connect to database
        populator.connect()
        
        # Optional: Clear existing data (uncomment if needed)
        # populator.clear_database()
        
        # Populate database with configured batch size
        populator.populate_quotes(quotes, batch_size=Config.BATCH_SIZE)
        
        # Display statistics
        stats = populator.get_database_stats()
        print(f"\n=== DATABASE POPULATION SUMMARY ===")
        print(f"Authors: {stats['authors']}")
        print(f"Quotes: {stats['quotes']}")
        print(f"Sources: {stats['sources']}")
        print(f"Pages: {stats['pages']}")
        print(f"Occurrences: {stats['occurrences']}")
        print(f"Attribution relationships: {stats['attributed_to_relationships']}")
        print(f"Source relationships: {stats['appears_in_relationships']}")
        
    except Exception as e:
        logger.error(f"Error during database population: {e}")
    finally:
        populator.close()

if __name__ == "__main__":
    main()
