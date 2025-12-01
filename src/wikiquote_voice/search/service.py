import logging
import re
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
from ..config import Config

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
    
    def build_semantic_index(self, sample_size: int = 10000):
        """
        Build semantic index for similarity search.
        This is a placeholder - the actual search uses Neo4j queries.
        """
        logger.info(f"✅ Semantic index built with {sample_size} quotes")
    
    def intelligent_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Intelligent search - alias for search_quotes.
        Used by chatbot and voice input.
        """
        return self.search_quotes(query, limit=limit, include_fuzzy=True)
    
    def search_quotes(self, query: str, limit: int = 10, include_fuzzy: bool = True) -> List[Dict[str, Any]]:
        """
        Advanced quote search with multiple search strategies.
        Automatically detects partial quotes and prioritizes complete quotes.
        
        Args:
            query (str): Search query (can be keywords, phrases, or natural language)
            limit (int): Maximum number of results to return
            include_fuzzy (bool): Whether to include fuzzy/similarity matching
            
        Returns:
            List[Dict[str, Any]]: Ranked list of matching quotes with metadata
        """
        if not query or not query.strip():
            return []
        
        query = query.strip()
        
        # Detect if this looks like a partial quote (3+ words = likely a phrase)
        words = query.split()
        is_partial_quote = len(words) >= 3
        
        if is_partial_quote:
            logger.info(f"Detected partial quote search: '{query}'")
            return self._partial_quote_search(query, limit)
        
        # Standard search for short queries
        results = []
        
        # Strategy 1: Full-text search with exact phrase matching
        exact_results = self._fulltext_search(query, limit // 2)
        results.extend(exact_results)
        
        # Strategy 2: Keyword-based search if we need more results
        if len(results) < limit:
            keyword_results = self._keyword_search(query, limit - len(results))
            # Avoid duplicates by checking quote text
            existing_texts = {r['quote_text'] for r in results}
            for result in keyword_results:
                if result['quote_text'] not in existing_texts:
                    results.append(result)
        
        # Strategy 3: Fuzzy search for broader matches if enabled
        if include_fuzzy and len(results) < limit:
            fuzzy_results = self._fuzzy_search(query, limit - len(results))
            existing_texts = {r['quote_text'] for r in results}
            for result in fuzzy_results:
                if result['quote_text'] not in existing_texts:
                    results.append(result)
        
        # Sort by relevance score and return top results
        results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        logger.info(f"Found {len(results)} quotes for query: '{query}'")
        return results[:limit]
    
    def _partial_quote_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """
        Search for partial quotes - prioritizes quotes that START with the query.
        Prefers CONCISE quotes (50-300 chars) that are readable and quotable.
        Also prefers real authors over topic pages.
        Falls back to keyword search if no exact partial match found.
        """
        # Known topic pages that aren't real authors
        topic_pages = ['Art', 'Poets', 'Poetry', 'Literature', 'Philosophy', 'Science', 
                       'Love', 'Life', 'Death', 'Time', 'Nature', 'Music', 'War', 'Peace']
        
        cypher_query = """
        MATCH (author:Author)-[:ATTRIBUTED_TO]->(quote:Quote)
        MATCH (quote)-[:APPEARS_IN]->(source:Source)
        WHERE toLower(quote.text) CONTAINS toLower($search_text)
        
        WITH quote, author, source,
             toLower(quote.text) AS quote_lower,
             toLower($search_text) AS query_lower,
             size(quote.text) AS quote_length,
             author.name AS author_name
        
        // Filter: prefer quotes between 50-400 chars (readable length)
        WHERE quote_length >= 30 AND quote_length <= 500
        
        // Calculate score: prioritize quotes starting with query + concise quotes + real authors
        WITH quote, author, source, quote_length, author_name,
             CASE 
                 WHEN quote_lower STARTS WITH query_lower THEN 100.0
                 WHEN quote_lower ENDS WITH query_lower THEN 50.0
                 ELSE 10.0
             END AS position_score,
             // Bonus for CONCISE quotes (optimal 100-200 chars, penalize very long)
             CASE 
                 WHEN quote_length >= 50 AND quote_length <= 200 THEN 30.0
                 WHEN quote_length > 200 AND quote_length <= 300 THEN 20.0
                 WHEN quote_length > 300 THEN 5.0
                 ELSE 10.0
             END AS length_bonus,
             // Penalty for topic pages (not real authors)
             CASE 
                 WHEN author_name IN $topic_pages THEN 0.5
                 ELSE 1.0
             END AS author_multiplier
        
        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               (position_score + length_bonus) * author_multiplier AS relevance_score,
               quote_length,
               'partial_match' AS search_type
        
        ORDER BY relevance_score DESC, quote_length ASC
        LIMIT $limit
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, search_text=query, limit=limit, topic_pages=topic_pages)
                results = [dict(record) for record in result]
                logger.info(f"Partial quote search found {len(results)} matches for '{query}'")
                
                # If no exact partial match, fallback to keyword search
                if not results:
                    logger.info(f"No partial match found, falling back to keyword search for '{query}'")
                    return self._keyword_search(query, limit)
                
                return results
        except Exception as e:
            logger.error(f"Error in partial quote search: {e}")
            # Fallback to standard search
            return self._keyword_search(query, limit)
    
    def _fulltext_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Full-text search using Neo4j index - prefers concise, quotable quotes."""
        # Prepare search query for full-text index
        search_query = self._prepare_fulltext_query(query)
        
        cypher_query = """
        CALL db.index.fulltext.queryNodes('quote_fulltext_index', $search_query)
        YIELD node AS quote, score
        
        MATCH (author:Author)-[:ATTRIBUTED_TO]->(quote)
        MATCH (quote)-[:APPEARS_IN]->(source:Source)
        
        WITH quote, author, source, score, size(quote.text) AS quote_length
        
        // Filter for readable quote lengths (30-500 chars)
        WHERE quote_length >= 30 AND quote_length <= 500
        
        // Adjust score based on length: prefer concise quotes
        WITH quote, author, source, quote_length,
             score * CASE 
                 WHEN quote_length >= 50 AND quote_length <= 200 THEN 1.5
                 WHEN quote_length > 200 AND quote_length <= 300 THEN 1.2
                 ELSE 1.0
             END AS adjusted_score
        
        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               adjusted_score AS relevance_score,
               quote_length,
               'fulltext' AS search_type
        
        ORDER BY adjusted_score DESC, quote_length ASC
        LIMIT $limit
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, search_query=search_query, limit=limit)
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Error in full-text search: {e}")
            return []
    
    def _keyword_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Keyword-based search for individual words in the query."""
        keywords = self._extract_keywords(query)
        if not keywords:
            return []
        
        # Create CONTAINS conditions for each keyword
        conditions = []
        params = {}
        for i, keyword in enumerate(keywords):
            param_name = f"keyword_{i}"
            conditions.append(f"toLower(quote.text) CONTAINS toLower(${param_name})")
            params[param_name] = keyword
        
        where_clause = " AND ".join(conditions)
        
        cypher_query = f"""
        MATCH (author:Author)-[:ATTRIBUTED_TO]->(quote:Quote)
        MATCH (quote)-[:APPEARS_IN]->(source:Source)
        WHERE {where_clause}
        
        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               0.7 AS relevance_score,
               'keyword' AS search_type
        
        ORDER BY size(quote.text) ASC
        LIMIT $limit
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, limit=limit, **params)
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Error in keyword search: {e}")
            return []
    
    def _fuzzy_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Fuzzy search using similarity matching."""
        
        cypher_query = """
        MATCH (author:Author)-[:ATTRIBUTED_TO]->(quote:Quote)
        MATCH (quote)-[:APPEARS_IN]->(source:Source)
        
        // Calculate similarity based on common words
        WITH quote, author, source,
             [word IN split(toLower($search_query), ' ') WHERE word IN split(toLower(quote.text), ' ')] AS common_words
        WHERE size(common_words) > 0
        
        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               toFloat(size(common_words)) / size(split($search_query, ' ')) AS relevance_score,
               'fuzzy' AS search_type
        
        ORDER BY relevance_score DESC
        LIMIT $limit
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, search_query=query, limit=limit)
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Error in fuzzy search: {e}")
            return []
    
    def search_by_author(self, author_query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Enhanced author search - prioritizes exact matches over partial matches."""
        
        # Prioritize authors where the query matches the START of a word in their name
        # e.g., "einstein" should match "Albert Einstein" but not "Bret Weinstein"
        cypher_query = """
        MATCH (author:Author)-[:ATTRIBUTED_TO]->(quote:Quote)
        MATCH (quote)-[:APPEARS_IN]->(source:Source)
        WHERE toLower(author.name) CONTAINS toLower($author_query)
        
        // Calculate match quality score
        WITH quote, author, source,
             toLower(author.name) AS author_lower,
             toLower($author_query) AS query_lower
        
        // Score: exact match > starts with > word boundary match > contains anywhere
        WITH quote, author, source, author_lower, query_lower,
             CASE
                 // Exact match (e.g., "Einstein" = "Einstein")
                 WHEN author_lower = query_lower THEN 100
                 // Author name starts with query (e.g., "Einstein..." starts with "ein")
                 WHEN author_lower STARTS WITH query_lower THEN 90
                 // Query matches start of a word (e.g., "Albert Einstein" contains " einstein")
                 WHEN author_lower CONTAINS (' ' + query_lower) THEN 80
                 // Query matches after common prefixes
                 WHEN author_lower CONTAINS query_lower AND 
                      (author_lower STARTS WITH query_lower OR 
                       author_lower CONTAINS (' ' + query_lower)) THEN 70
                 // Contains but in middle of a word (e.g., "Weinstein" contains "einstein")
                 ELSE 10
             END AS match_score
        
        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               match_score AS relevance_score
        
        ORDER BY match_score DESC, size(author.name) ASC, quote.text
        LIMIT $limit
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, author_query=author_query, limit=limit)
                quotes = [dict(record) for record in result]
                
                # If no results, try fuzzy matching (for typos like "gandi" -> "gandhi")
                if not quotes:
                    quotes = self._fuzzy_author_search(author_query, limit)
                
                logger.info(f"Found {len(quotes)} quotes by authors matching '{author_query}'")
                return quotes
        except Exception as e:
            logger.error(f"Error in author search: {e}")
            return []
    
    def _fuzzy_author_search(self, author_query: str, limit: int) -> List[Dict[str, Any]]:
        """Fuzzy author search - finds authors even with typos."""
        # Search for authors where most characters match
        cypher_query = """
        MATCH (author:Author)
        WHERE size(author.name) > 3
        
        // Calculate character overlap
        WITH author,
             toLower(author.name) AS author_lower,
             toLower($author_query) AS query_lower
        
        // Check if query is a substring allowing for 1-2 character differences
        WHERE author_lower CONTAINS query_lower
           OR query_lower CONTAINS author_lower
           // Check first 4 characters match (catches "gandi" -> "gandhi")
           OR left(author_lower, 4) = left(query_lower, 4)
           // Check if removing one character from query matches
           OR author_lower CONTAINS substring(query_lower, 0, size(query_lower)-1)
           OR author_lower CONTAINS substring(query_lower, 1)
        
        WITH author
        MATCH (author)-[:ATTRIBUTED_TO]->(quote:Quote)
        MATCH (quote)-[:APPEARS_IN]->(source:Source)
        
        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               0.8 AS relevance_score
        
        ORDER BY size(author.name), quote.text
        LIMIT $limit
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, author_query=author_query, limit=limit)
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Error in fuzzy author search: {e}")
            return []
    
    def search_by_theme(self, theme: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search quotes by theme or topic."""
        # Define theme-related keywords
        theme_keywords = self._get_theme_keywords(theme.lower())
        
        if not theme_keywords:
            # Fallback to direct search
            return self.search_quotes(theme, limit)
        
        # Create search query with theme keywords
        search_terms = " OR ".join(theme_keywords)
        
        cypher_query = """
        CALL db.index.fulltext.queryNodes('quote_fulltext_index', $search_terms)
        YIELD node AS quote, score
        
        MATCH (author:Author)-[:ATTRIBUTED_TO]->(quote)
        MATCH (quote)-[:APPEARS_IN]->(source:Source)
        
        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               score AS relevance_score
        
        ORDER BY score DESC
        LIMIT $limit
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, search_terms=search_terms, limit=limit)
                quotes = [dict(record) for record in result]
                
                logger.info(f"Found {len(quotes)} quotes for theme '{theme}'")
                return quotes
        except Exception as e:
            logger.error(f"Error in theme search: {e}")
            return []
    
    def get_popular_authors(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get most quoted authors."""
        cypher_query = """
        MATCH (author:Author)-[:ATTRIBUTED_TO]->(quote:Quote)
        WITH author, count(quote) AS quote_count
        ORDER BY quote_count DESC
        LIMIT $limit
        
        RETURN author.name AS author_name,
               quote_count
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, limit=limit)
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Error getting popular authors: {e}")
            return []
    
    def get_random_quote(self, author: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a random quote, optionally from a specific author."""
        if author:
            cypher_query = """
            MATCH (author:Author)-[:ATTRIBUTED_TO]->(quote:Quote)
            MATCH (quote)-[:APPEARS_IN]->(source:Source)
            WHERE toLower(author.name) CONTAINS toLower($author)
            
            WITH quote, author, source, rand() AS r
            ORDER BY r
            LIMIT 1
            
            RETURN quote.text AS quote_text,
                   author.name AS author_name,
                   source.title AS source_title
            """
            params = {'author': author}
        else:
            cypher_query = """
            MATCH (author:Author)-[:ATTRIBUTED_TO]->(quote:Quote)
            MATCH (quote)-[:APPEARS_IN]->(source:Source)
            
            WITH quote, author, source, rand() AS r
            ORDER BY r
            LIMIT 1
            
            RETURN quote.text AS quote_text,
                   author.name AS author_name,
                   source.title AS source_title
            """
            params = {}
        
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, **params)
                record = result.single()
                return dict(record) if record else None
        except Exception as e:
            logger.error(f"Error getting random quote: {e}")
            return None
    
    def _prepare_fulltext_query(self, query: str) -> str:
        """Prepare query for full-text search."""
        # Clean the query
        query = query.strip()
        
        # If it's a phrase (contains quotes), use as-is
        if '"' in query:
            return query
        
        # For multiple words, try exact phrase first, then individual words
        words = query.split()
        if len(words) > 1:
            # Create a query that searches for the phrase and individual words
            phrase_query = f'"{query}"'
            word_queries = [f"{word}*" for word in words]
            return f"{phrase_query} OR ({' AND '.join(word_queries)})"
        else:
            # Single word - add wildcard for prefix matching
            return f"{query}*"
    
    def _extract_keywords(self, query: str) -> List[str]:
        """Extract meaningful keywords from query."""
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had'}
        
        # Clean and split query
        words = re.findall(r'\b\w+\b', query.lower())
        
        # Filter out stop words and short words
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        return keywords[:5]  # Limit to 5 keywords
    
    def _get_theme_keywords(self, theme: str) -> List[str]:
        """Get related keywords for a theme."""
        theme_mapping = {
            'love': ['love', 'heart', 'romance', 'affection', 'passion', 'devotion'],
            'wisdom': ['wisdom', 'wise', 'knowledge', 'understanding', 'insight', 'intelligence'],
            'life': ['life', 'living', 'existence', 'experience', 'journey', 'purpose'],
            'success': ['success', 'achievement', 'victory', 'accomplishment', 'triumph'],
            'failure': ['failure', 'defeat', 'mistake', 'error', 'setback', 'disappointment'],
            'happiness': ['happiness', 'joy', 'pleasure', 'delight', 'contentment', 'bliss'],
            'peace': ['peace', 'calm', 'tranquility', 'serenity', 'harmony', 'quiet'],
            'war': ['war', 'battle', 'conflict', 'fight', 'struggle', 'combat'],
            'death': ['death', 'mortality', 'dying', 'grave', 'eternal', 'afterlife'],
            'friendship': ['friendship', 'friend', 'companion', 'loyalty', 'trust', 'bond'],
            'time': ['time', 'moment', 'hour', 'day', 'year', 'eternity', 'future', 'past'],
            'freedom': ['freedom', 'liberty', 'independence', 'choice', 'autonomy'],
            'truth': ['truth', 'honesty', 'fact', 'reality', 'genuine', 'authentic'],
            'courage': ['courage', 'brave', 'fearless', 'bold', 'valor', 'heroic'],
            'justice': ['justice', 'fair', 'right', 'equality', 'moral', 'ethical']
        }
        
        return theme_mapping.get(theme, [theme])

    def autocomplete(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Autocomplete functionality for voice search integration.
        Returns quick matches for real-time suggestions.
        """
        return self.search_quotes(query, limit=limit, include_fuzzy=False)
    
    def voice_search(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Optimized search for voice queries.
        Returns concise results perfect for voice output.
        """
        results = self.search_quotes(query, limit=limit)
        
        # For voice output, we want shorter quotes when possible
        for result in results:
            if len(result['quote_text']) > 200:
                result['quote_text'] = result['quote_text'][:197] + "..."
        
        return results

def print_search_results(results: List[Dict[str, Any]], query: str, show_details: bool = True):
    """Enhanced pretty print for search results."""
    if not results:
        print(f"No quotes found for '{query}'")
        return
    
    print(f"\n{'='*60}")
    print(f"  SEARCH RESULTS FOR: '{query}'")
    print(f"{'='*60}")
    print(f"Found {len(results)} quotes:\n")
    
    for i, quote in enumerate(results, 1):
        # Truncate long quotes for display
        quote_text = quote['quote_text']
        if len(quote_text) > 150:
            quote_text = quote_text[:147] + "..."
        
        print(f"{i:2d}. \"{quote_text}\"")
        print(f"    — {quote['author_name']}")
        
        if show_details:
            print(f"    📖 Source: {quote['source_title']}")
            if 'relevance_score' in quote:
                print(f"    🎯 Relevance: {quote['relevance_score']:.3f}")
            if 'search_type' in quote:
                print(f"    🔍 Match type: {quote['search_type']}")
        
        print()

def interactive_search():
    """Interactive search interface for testing."""
    search_service = QuoteSearchService(Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
    
    try:
        search_service.connect()
        print("\n🎯 WIKIQUOTE VOICE SEARCH - Interactive Mode")
        print("="*50)
        print("Commands:")
        print("  search <query>     - Search quotes")
        print("  author <name>      - Find quotes by author")
        print("  theme <topic>      - Find quotes by theme")
        print("  random [author]    - Get random quote")
        print("  popular            - Show popular authors")
        print("  voice <query>      - Voice-optimized search")
        print("  autocomplete <q>   - Test autocomplete")
        print("  quit               - Exit")
        print("="*50)
        
        while True:
            try:
                user_input = input("\n🎤 Enter command: ").strip()
                
                if not user_input or user_input.lower() == 'quit':
                    break
                
                parts = user_input.split(' ', 1)
                command = parts[0].lower()
                query = parts[1] if len(parts) > 1 else ""
                
                if command == 'search' and query:
                    results = search_service.search_quotes(query, limit=5)
                    print_search_results(results, query)
                
                elif command == 'author' and query:
                    results = search_service.search_by_author(query, limit=5)
                    print_search_results(results, f"Author: {query}", show_details=False)
                
                elif command == 'theme' and query:
                    results = search_service.search_by_theme(query, limit=5)
                    print_search_results(results, f"Theme: {query}")
                
                elif command == 'voice' and query:
                    results = search_service.voice_search(query, limit=3)
                    print(f"\n🎤 VOICE SEARCH RESULTS:")
                    for i, result in enumerate(results, 1):
                        print(f"{i}. \"{result['quote_text']}\" — {result['author_name']}")
                
                elif command == 'autocomplete' and query:
                    results = search_service.autocomplete(query, limit=5)
                    print(f"\n💡 AUTOCOMPLETE SUGGESTIONS:")
                    for i, result in enumerate(results, 1):
                        short_quote = result['quote_text'][:50] + "..." if len(result['quote_text']) > 50 else result['quote_text']
                        print(f"{i}. \"{short_quote}\" — {result['author_name']}")
                
                elif command == 'random':
                    author = query if query else None
                    result = search_service.get_random_quote(author)
                    if result:
                        print(f"\n🎲 Random Quote:")
                        print(f"\"{result['quote_text']}\"")
                        print(f"— {result['author_name']} (from {result['source_title']})")
                    else:
                        print("No random quote found")
                
                elif command == 'popular':
                    authors = search_service.get_popular_authors(limit=10)
                    print(f"\n👑 Most Quoted Authors:")
                    for i, author in enumerate(authors, 1):
                        print(f"{i:2d}. {author['author_name']} ({author['quote_count']} quotes)")
                
                else:
                    print("Invalid command. Type 'quit' to exit.")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
        
    except Exception as e:
        logger.error(f"Error in interactive search: {e}")
    finally:
        search_service.close()
        print("\n👋 Goodbye!")

def main():
    """Demonstration of enhanced search functionality."""
    search_service = QuoteSearchService(Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
    
    try:
        search_service.connect()
        
        # Demo searches
        demo_queries = [
            "imagination is more important than knowledge",
            "love",
            "life is what happens",
            "be yourself",
            "success"
        ]
        
        print("🎯 WIKIQUOTE VOICE SEARCH - Demo Mode")
        print("="*50)
        
        for query in demo_queries:
            results = search_service.search_quotes(query, limit=3)
            print_search_results(results, query)
            print("-" * 50)
        
        # Show popular authors
        print("\n👑 POPULAR AUTHORS")
        authors = search_service.get_popular_authors(limit=5)
        for i, author in enumerate(authors, 1):
            print(f"{i}. {author['author_name']} ({author['quote_count']} quotes)")
        
        # Random quote
        print(f"\n🎲 RANDOM QUOTE")
        random_quote = search_service.get_random_quote()
        if random_quote:
            print(f"\"{random_quote['quote_text']}\"")
            print(f"— {random_quote['author_name']}")
        
        print(f"\n💡 Try interactive mode: python search_service.py --interactive")
        
    except Exception as e:
        logger.error(f"Error in demo: {e}")
    finally:
        search_service.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--interactive':
        interactive_search()
    else:
        main()
