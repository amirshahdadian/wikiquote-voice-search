import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
import sys

from backend.app.core.logging import configure_logging
from backend.app.core.settings import settings

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
        """Clear all nodes and relationships from the database in small batches."""
        with self.driver.session() as session:
            deleted = 1
            total = 0
            while deleted > 0:
                result = session.run(
                    """
                    MATCH (n)
                    WITH n LIMIT 50000
                    DETACH DELETE n
                    RETURN count(*) AS deleted
                    """
                )
                deleted = result.single()["deleted"]
                total += deleted
                if deleted > 0:
                    logger.info(f"Cleared {total:,} nodes so far...")
        logger.info(f"Database cleared — {total:,} nodes removed")
    
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

            // Preserve NULL for missing author/source instead of polluting the
            // graph with placeholder "Unknown" nodes.
            WITH quote_data,
                 CASE
                    WHEN quote_data.author IS NULL OR trim(quote_data.author) = '' THEN null
                    ELSE quote_data.author
                 END AS author_name,
                 CASE
                    WHEN quote_data.source IS NULL OR trim(quote_data.source) = '' THEN null
                    ELSE quote_data.source
                 END AS source_title
            WITH quote_data, author_name, source_title,
                 (
                    quote_data.page_type IN ['person', 'literary_work']
                    AND quote_data.quote_type IN ['sourced', 'template', 'blockquote']
                    AND source_title IS NOT NULL
                    AND author_name IS NOT NULL
                    AND NOT toLower(quote_data.page_title) =~ '.*\\b(proverbs?|aphorisms?|sayings?|quotations?|quotes?|idioms?|maxims?|slogans?|opening lines|catchphrases|taglines?)\\b.*'
                    AND NOT toLower(coalesce(author_name,'')) =~ '.*\\b(proverbs?|aphorisms?|sayings?|quotations?|quotes?|idioms?|maxims?|slogans?|opening lines|catchphrases|taglines?)\\b.*'
                    AND NOT toLower(coalesce(source_title,'')) =~ '.*\\b(proverbs?|aphorisms?|sayings?|quotations?|quotes?|idioms?|maxims?|slogans?|opening lines|catchphrases|taglines?)\\b.*'
                    AND NOT toLower(quote_data.page_title) =~ '.*\\((?:\\d{4}\\s+)?(?:film|movie|tv|television|series)\\).*'
                    AND NOT toLower(quote_data.page_title) =~ '.*(?:^|/|\\()season\\s+[a-z0-9]+.*'
                 ) AS occurrence_is_primary

            // Only create Author/Source nodes when we have real values (not NULL).
            FOREACH (_ IN CASE WHEN author_name IS NOT NULL THEN [1] ELSE [] END |
                MERGE (a:Author {name: author_name})
            )
            FOREACH (_ IN CASE WHEN source_title IS NOT NULL THEN [1] ELSE [] END |
                MERGE (s:Source {title: source_title})
            )
            MERGE (page:Page {title: quote_data.page_title})

            MERGE (quote:Quote {fingerprint: quote_data.quote_fingerprint})
              ON CREATE SET
                quote.text = quote_data.quote,
                quote.canonical_text = coalesce(quote_data.canonical_quote, quote_data.quote),
                quote.normalized_text = coalesce(quote_data.normalized_quote, quote_data.canonical_quote, quote_data.quote),
                quote.page_type = quote_data.page_type,
                quote.quote_type = quote_data.quote_type,
                quote.primary_author = author_name,
                quote.primary_source = source_title,
                quote.primary_page = quote_data.page_title,
                quote.work = quote_data.work,
                quote.year = quote_data.year,
                quote.original_text = quote_data.original_text,
                quote.is_primary = occurrence_is_primary
              ON MATCH SET
                quote.page_type = CASE
                    WHEN occurrence_is_primary THEN quote_data.page_type
                    ELSE coalesce(quote.page_type, quote_data.page_type)
                END,
                quote.quote_type = CASE
                    WHEN occurrence_is_primary THEN quote_data.quote_type
                    ELSE coalesce(quote.quote_type, quote_data.quote_type)
                END,
                quote.primary_author = CASE
                    WHEN occurrence_is_primary AND author_name IS NOT NULL THEN author_name
                    ELSE coalesce(quote.primary_author, author_name)
                END,
                quote.primary_source = CASE
                    WHEN occurrence_is_primary AND source_title IS NOT NULL THEN source_title
                    ELSE coalesce(quote.primary_source, source_title)
                END,
                quote.primary_page = CASE
                    WHEN occurrence_is_primary THEN quote_data.page_title
                    ELSE coalesce(quote.primary_page, quote_data.page_title)
                END,
                quote.work = coalesce(quote.work, quote_data.work),
                quote.year = coalesce(quote.year, quote_data.year),
                quote.original_text = coalesce(quote.original_text, quote_data.original_text),
                quote.normalized_text = coalesce(quote.normalized_text, quote_data.normalized_quote, quote_data.canonical_quote, quote_data.quote),
                quote.is_primary = coalesce(quote.is_primary, false) OR occurrence_is_primary

            MERGE (occurrence:QuoteOccurrence {key: quote_data.occurrence_key})
              ON CREATE SET
                occurrence.author_name = author_name,
                occurrence.source_title = source_title,
                occurrence.page_title = quote_data.page_title,
                occurrence.page_type = quote_data.page_type,
                occurrence.context = quote_data.context,
                occurrence.citation = quote_data.citation,
                occurrence.source_locator = quote_data.source_locator,
                occurrence.work = quote_data.work,
                occurrence.year = quote_data.year,
                occurrence.quote_type = quote_data.quote_type,
                occurrence.is_primary = occurrence_is_primary,
                occurrence.search_tier = CASE WHEN occurrence_is_primary THEN 'primary' ELSE 'secondary' END
              ON MATCH SET
                occurrence.author_name = coalesce(occurrence.author_name, author_name),
                occurrence.source_title = coalesce(occurrence.source_title, source_title),
                occurrence.page_type = coalesce(occurrence.page_type, quote_data.page_type),
                occurrence.context = coalesce(occurrence.context, quote_data.context),
                occurrence.citation = coalesce(occurrence.citation, quote_data.citation),
                occurrence.source_locator = coalesce(occurrence.source_locator, quote_data.source_locator),
                occurrence.work = coalesce(occurrence.work, quote_data.work),
                occurrence.year = coalesce(occurrence.year, quote_data.year),
                occurrence.quote_type = coalesce(occurrence.quote_type, quote_data.quote_type),
                occurrence.is_primary = coalesce(occurrence.is_primary, false) OR occurrence_is_primary,
                occurrence.search_tier = CASE
                    WHEN coalesce(occurrence.is_primary, false) OR occurrence_is_primary THEN 'primary'
                    ELSE 'secondary'
                END

            SET quote.search_tier = CASE WHEN quote.is_primary THEN 'primary' ELSE 'secondary' END

            FOREACH (_ IN CASE WHEN quote.is_primary THEN [1] ELSE [] END |
                SET quote:PrimaryQuote
            )
            FOREACH (_ IN CASE WHEN NOT quote.is_primary THEN [1] ELSE [] END |
                SET quote:SecondaryQuote
            )

            // Create relationships only when author/source nodes exist (not NULL).
            WITH quote, occurrence, page, author_name, source_title
            MERGE (quote)-[:EXTRACTED_FROM]->(page)
            MERGE (quote)-[:HAS_OCCURRENCE]->(occurrence)
            MERGE (occurrence)-[:FOUND_ON_PAGE]->(page)

            WITH quote, occurrence, author_name, source_title
            FOREACH (_ IN CASE WHEN author_name IS NOT NULL THEN [1] ELSE [] END |
                MERGE (a:Author {name: author_name})
                MERGE (a)-[:ATTRIBUTED_TO]->(quote)
                MERGE (occurrence)-[:ATTRIBUTED_TO]->(a)
            )
            FOREACH (_ IN CASE WHEN source_title IS NOT NULL THEN [1] ELSE [] END |
                MERGE (s:Source {title: source_title})
                MERGE (quote)-[:APPEARS_IN]->(s)
                MERGE (occurrence)-[:CITED_AS]->(s)
            )
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


def build_search_indexes() -> None:
    """Create Neo4j full-text and supporting indexes."""
    configure_logging(settings.log_level)
    logger.info("Connecting to Neo4j for index creation")
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    try:
        with driver.session() as session:
            session.run("RETURN 1")
            fulltext_indexes = [
                (
                    "quote_primary_fulltext_index",
                    """
                    CREATE FULLTEXT INDEX quote_primary_fulltext_index IF NOT EXISTS
                    FOR (q:PrimaryQuote)
                    ON EACH [q.text, q.canonical_text, q.normalized_text, q.primary_author, q.primary_source, q.primary_page]
                    """,
                ),
                (
                    "quote_fulltext_index",
                    """
                    CREATE FULLTEXT INDEX quote_fulltext_index IF NOT EXISTS
                    FOR (q:Quote)
                    ON EACH [q.text, q.canonical_text, q.normalized_text, q.primary_author, q.primary_source, q.primary_page]
                    """,
                ),
            ]
            supporting_indexes = [
                "CREATE INDEX author_name_index IF NOT EXISTS FOR (a:Author) ON (a.name)",
                "CREATE INDEX source_title_index IF NOT EXISTS FOR (s:Source) ON (s.title)",
                "CREATE INDEX page_title_index IF NOT EXISTS FOR (p:Page) ON (p.title)",
                "CREATE INDEX quote_fingerprint_index IF NOT EXISTS FOR (q:Quote) ON (q.fingerprint)",
                "CREATE INDEX quote_normalized_text_index IF NOT EXISTS FOR (q:Quote) ON (q.normalized_text)",
                "CREATE INDEX occurrence_key_index IF NOT EXISTS FOR (o:QuoteOccurrence) ON (o.key)",
                "CREATE INDEX occurrence_is_primary_index IF NOT EXISTS FOR (o:QuoteOccurrence) ON (o.is_primary)",
                "CREATE INDEX quote_is_primary_index IF NOT EXISTS FOR (q:Quote) ON (q.is_primary)",
            ]
            for _, query in fulltext_indexes:
                session.run(query)
            for query in supporting_indexes:
                session.run(query)
    finally:
        driver.close()


def create_index_main() -> None:
    """CLI entrypoint for creating search indexes."""
    try:
        build_search_indexes()
    except AuthError:
        logger.error("Authentication failed. Check Neo4j credentials.")
        raise SystemExit(1) from None
    except ServiceUnavailable:
        logger.error("Neo4j is unavailable. Ensure the service is running.")
        raise SystemExit(1) from None

def main():
    """Main function to populate the Neo4j database.

    Pass --clear as the first CLI argument to wipe the database before loading.
    """
    clear_first = "--clear" in sys.argv
    if any(argument in {"index", "create-index", "--create-index"} for argument in sys.argv[1:]):
        create_index_main()
        return

    # Load quotes from JSON
    configure_logging(settings.log_level)

    quotes = load_quotes_from_json(str(settings.resolved_quotes_file))

    if not quotes:
        logger.error("No quotes loaded. Please run parse_wikitext.py first.")
        return

    # Initialize Neo4j populator using config
    populator = Neo4jPopulator(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)

    try:
        # Connect to database
        populator.connect()

        if clear_first:
            logger.info("--clear flag set: wiping existing database before load")
            populator.clear_database()

        # Populate database with configured batch size
        populator.populate_quotes(quotes, batch_size=settings.batch_size)
        
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
