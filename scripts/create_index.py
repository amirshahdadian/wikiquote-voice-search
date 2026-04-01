"""
Create Full-text Index for Wikiquote Neo4j Database

This script creates a full-text search index on Quote nodes
for fast autocomplete and search functionality.
"""

import sys
from pathlib import Path
import logging

# Add parent directory to path for src imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
from src.wikiquote_voice import Config

# Set up logging
logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL), 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_fulltext_index():
    """Create a full-text search index on Quote nodes."""
    
    logger.info("Connecting to Neo4j...")
    logger.info(f"URI: {Config.NEO4J_URI}")
    
    try:
        driver = GraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
        )
        
        # Test connection
        with driver.session() as session:
            session.run("RETURN 1")
        logger.info("✅ Connected to Neo4j")
        
        with driver.session() as session:
            # Create full-text index across quote text plus denormalized provenance fields.
            logger.info("Creating full-text index on Quote searchable fields...")
            
            index_query = """
            CREATE FULLTEXT INDEX quote_fulltext_index IF NOT EXISTS
            FOR (q:Quote) ON EACH [q.text, q.canonical_text, q.primary_author, q.primary_source, q.primary_page]
            """
            
            try:
                session.run(index_query)
                logger.info("✅ Full-text index 'quote_fulltext_index' created (or already exists)")
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info("ℹ️ Index already exists")
                else:
                    raise
            
            # Create additional indexes for performance
            logger.info("Creating additional indexes...")
            
            additional_indexes = [
                ("author_name_index", "CREATE INDEX author_name_index IF NOT EXISTS FOR (a:Author) ON (a.name)"),
                ("source_title_index", "CREATE INDEX source_title_index IF NOT EXISTS FOR (s:Source) ON (s.title)"),
                ("page_title_index", "CREATE INDEX page_title_index IF NOT EXISTS FOR (p:Page) ON (p.title)"),
                ("quote_fingerprint_index", "CREATE INDEX quote_fingerprint_index IF NOT EXISTS FOR (q:Quote) ON (q.fingerprint)"),
                ("occurrence_key_index", "CREATE INDEX occurrence_key_index IF NOT EXISTS FOR (o:QuoteOccurrence) ON (o.key)"),
            ]
            
            for index_name, query in additional_indexes:
                try:
                    session.run(query)
                    logger.info(f"✅ Index '{index_name}' created (or already exists)")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        logger.info(f"ℹ️ Index '{index_name}' already exists")
                    else:
                        logger.warning(f"⚠️ Could not create index '{index_name}': {e}")
            
            # List all indexes
            logger.info("\n📋 Current indexes:")
            result = session.run("SHOW INDEXES")
            for record in result:
                logger.info(f"  - {record['name']}: {record['type']} on {record.get('labelsOrTypes', 'N/A')}")
        
        driver.close()
        logger.info("\n✅ Index creation complete!")
        
    except AuthError:
        logger.error("❌ Authentication failed. Check NEO4J_USERNAME and NEO4J_PASSWORD")
        sys.exit(1)
    except ServiceUnavailable:
        logger.error("❌ Neo4j service unavailable. Is Neo4j running?")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    print("=" * 60)
    print("WIKIQUOTE NEO4J INDEX CREATOR")
    print("=" * 60)
    
    create_fulltext_index()
    
    print("\nNext steps:")
    print("  1. Test search: PYTHONPATH=src python3 -m wikiquote_voice.search.service --interactive")
    print("  2. Run Streamlit: streamlit run streamlit_app.py")


if __name__ == "__main__":
    main()
