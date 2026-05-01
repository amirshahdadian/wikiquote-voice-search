import logging
import re
import unicodedata
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
from backend.app.core.settings import settings

logger = logging.getLogger(__name__)

class QuoteSearchService:
    PAGE_TYPE_MULTIPLIERS = {
        "person": 1.3,
        "literary_work": 1.15,
        "theme": 0.2,
        "film": 0.1,
        "tv_show": 0.08,
    }
    PRIMARY_PAGE_TYPES = ("person", "literary_work")
    PRIMARY_QUOTE_TYPES = ("sourced", "template", "blockquote")

    def __init__(self, uri: str, username: str, password: str, database: str | None = None):
        """Initialize the search service with Neo4j connection."""
        self.uri = uri
        self.username = username
        self.password = password
        self.database = database
        self.driver = None
        
    def connect(self):
        """Establish connection to Neo4j database."""
        try:
            self.driver = self._create_verified_driver(self.uri)
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

    def _create_verified_driver(self, uri: str):
        """
        Create and verify a Neo4j driver.

        Single-instance local Neo4j deployments often expose Bolt without routing.
        If a ``neo4j://`` URI fails due to missing routing information, retry the
        same endpoint with ``bolt://`` automatically.
        """
        driver = GraphDatabase.driver(uri, auth=(self.username, self.password))
        try:
            driver.verify_connectivity()
            return driver
        except ServiceUnavailable as exc:
            message = str(exc)
            should_retry_with_bolt = (
                uri.startswith("neo4j://")
                and "routing information" in message.lower()
            )
            driver.close()

            if not should_retry_with_bolt:
                raise

            fallback_uri = "bolt://" + uri[len("neo4j://") :]
            logger.warning(
                "Neo4j routing unavailable for %s; retrying direct Bolt connection via %s",
                uri,
                fallback_uri,
            )
            fallback_driver = GraphDatabase.driver(
                fallback_uri,
                auth=(self.username, self.password),
            )
            fallback_driver.verify_connectivity()
            self.uri = fallback_uri
            return fallback_driver

    def _page_type_multiplier_case(self, property_name: str = "occurrence.page_type") -> str:
        """Return a Cypher CASE expression that prefers high-precision page types."""
        return f"""
        CASE coalesce({property_name}, 'unknown')
            WHEN 'person' THEN {self.PAGE_TYPE_MULTIPLIERS['person']}
            WHEN 'literary_work' THEN {self.PAGE_TYPE_MULTIPLIERS['literary_work']}
            WHEN 'theme' THEN {self.PAGE_TYPE_MULTIPLIERS['theme']}
            WHEN 'film' THEN {self.PAGE_TYPE_MULTIPLIERS['film']}
            WHEN 'tv_show' THEN {self.PAGE_TYPE_MULTIPLIERS['tv_show']}
            ELSE 0.8
        END
        """
    
    def close(self):
        """Close the Neo4j connection."""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")

    def session(self):
        """Open a session against the configured Neo4j database, if provided."""
        if self.driver is None:
            raise RuntimeError("Neo4j driver is not connected")
        if self.database:
            return self.driver.session(database=self.database)
        return self.driver.session()
    
    def build_semantic_index(self, sample_size: int = 10000):
        """
        Placeholder hook for semantic retrieval.
        Current search remains Neo4j lexical/fuzzy query based.
        """
        logger.info(
            "Semantic index hook invoked (sample_size=%s), but no semantic index is built in this version",
            sample_size,
        )
    
    def intelligent_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Intelligent search - alias for search_quotes.
        Used by chatbot and voice input.
        """
        return self.search_quotes(query, limit=limit, include_fuzzy=True)

    def _normalize_search_text(self, text: str) -> str:
        """Normalize text for punctuation-insensitive quote matching."""
        normalized = unicodedata.normalize("NFKD", text or "")
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        normalized = normalized.lower().replace("&", " and ")
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return " ".join(normalized.split())
    
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
        
        query = " ".join(query.strip().split())

        theme_match = re.match(r"^quotes?\s+(?:about|on|regarding)\s+(.+)$", query, re.IGNORECASE)
        if theme_match:
            return self.search_by_theme(theme_match.group(1).strip(), limit=limit)
        
        is_partial_quote = self._looks_like_partial_quote(query)
        
        if is_partial_quote:
            logger.info(f"Detected partial quote search: '{query}'")
            return self._partial_quote_search(query, limit)
        
        results = self._run_search_pipeline(query, limit, include_fuzzy=include_fuzzy)
        results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        logger.info(f"Found {len(results)} quotes for query: '{query}'")
        return results[:limit]

    def _run_search_pipeline(self, query: str, limit: int, include_fuzzy: bool = True) -> List[Dict[str, Any]]:
        """Run primary-corpus search first, then backfill from broader corpora if needed."""
        results: List[Dict[str, Any]] = []
        primary_steps = [
            lambda remaining: self._fulltext_search(query, remaining, scope="primary"),
            lambda remaining: self._keyword_search(query, remaining, scope="primary"),
        ]
        if include_fuzzy:
            primary_steps.append(lambda remaining: self._fuzzy_search(query, remaining, scope="primary"))

        secondary_steps = [
            lambda remaining: self._fulltext_search(query, remaining, scope="secondary"),
            lambda remaining: self._keyword_search(query, remaining, scope="secondary"),
        ]
        if include_fuzzy:
            secondary_steps.append(lambda remaining: self._fuzzy_search(query, remaining, scope="secondary"))

        for step in primary_steps + secondary_steps:
            remaining = limit - len(results)
            if remaining <= 0:
                break
            results = self._merge_unique_results(results, step(remaining), limit)

        return results

    def _merge_unique_results(
        self, existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]], limit: int
    ) -> List[Dict[str, Any]]:
        """Deduplicate search results across strategies while preserving score ordering."""
        seen = {
            (
                result.get("quote_text"),
                result.get("author_name"),
                result.get("source_title"),
            )
            for result in existing
        }
        merged = list(existing)
        for result in incoming:
            key = (
                result.get("quote_text"),
                result.get("author_name"),
                result.get("source_title"),
            )
            if key in seen:
                continue
            merged.append(result)
            seen.add(key)
            if len(merged) >= limit:
                break
        return merged

    def _looks_like_partial_quote(self, query: str) -> bool:
        """
        Distinguish quote fragments from natural-language search commands.

        A simple word-count rule incorrectly routes requests like
        ``quotes about courage and fear`` into the partial quote path.
        """
        normalized = " ".join(query.lower().split())
        words = normalized.split()

        if len(words) < 3:
            return False

        if re.search(
            r"\b(find|search|show|get|give|tell|want|need|looking)\b",
            normalized,
        ):
            return False

        if re.search(r"\bquotes?\s+(about|on|regarding|by|from)\b", normalized):
            return False

        if normalized.startswith(("who said ", "who wrote ")):
            return False

        return True

    def _fulltext_index_name(self, scope: str) -> str:
        """Return the full-text index name for the requested search scope."""
        return "quote_primary_fulltext_index" if scope == "primary" else "quote_fulltext_index"

    def _scope_condition(self, scope: str, occurrence_alias: str = "occurrence") -> str:
        """Return a Cypher filter for the requested search scope."""
        primary_condition = f"coalesce({occurrence_alias}.is_primary, false)"
        if scope == "primary":
            return primary_condition
        return f"NOT ({primary_condition})"
    
    def _partial_quote_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """
        Search for partial quotes - prioritizes quotes that START with the query.
        Prefers concise, clean completions in the primary corpus before broader fallback.
        """
        results = self._partial_quote_search_in_scope(query, limit, scope="primary")
        if results:
            return results
        logger.info(f"No primary-corpus partial match found, falling back to broader search for '{query}'")
        return self._partial_quote_search_in_scope(query, limit, scope="secondary")

    def _partial_quote_search_in_scope(self, query: str, limit: int, scope: str) -> List[Dict[str, Any]]:
        """Search partial quotes within a specific quality scope."""
        page_type_multiplier_case = self._page_type_multiplier_case()
        scope_condition = self._scope_condition(scope)
        normalized_query = self._normalize_search_text(query)

        cypher_query = f"""
        MATCH (quote:Quote)-[:HAS_OCCURRENCE]->(occurrence:QuoteOccurrence)-[:CITED_AS]->(source:Source)
        MATCH (occurrence)-[:ATTRIBUTED_TO]->(author:Author)
        WHERE {scope_condition}
          AND coalesce(quote.normalized_text, quote.canonical_text, quote.text) CONTAINS $search_normalized

        WITH quote, occurrence, author, source,
             coalesce(quote.normalized_text, quote.canonical_text, quote.text) AS normalized_quote,
             $search_normalized AS query_normalized,
             size(quote.text) AS quote_length,
             size($search_normalized) AS query_length

        WHERE quote_length >= 15 AND quote_length <= 320

        WITH quote, occurrence, author, source, quote_length, query_length, normalized_quote, query_normalized,
             size(split(normalized_quote, query_normalized)[0]) AS prefix_gap

        WITH quote, occurrence, author, source, quote_length, query_length, normalized_quote, query_normalized, prefix_gap,
             CASE
                 WHEN normalized_quote = query_normalized THEN 170.0
                 WHEN normalized_quote STARTS WITH query_normalized THEN 140.0
                 WHEN (' ' + normalized_quote) CONTAINS (' ' + query_normalized + ' ') THEN 110.0
                 WHEN normalized_quote CONTAINS query_normalized THEN 90.0
                 ELSE 0.0
             END AS position_score,
             CASE
                 WHEN quote_length >= 18 AND quote_length <= 140 THEN 25.0
                 WHEN quote_length > 140 AND quote_length <= 220 THEN 15.0
                 ELSE 5.0
             END AS length_bonus,
             CASE
                 WHEN quote_length > query_length THEN
                    CASE
                        WHEN (quote_length - query_length) <= 40 THEN 35.0
                        WHEN (quote_length - query_length) <= 120 THEN 18.0
                        ELSE 5.0
                    END
                 ELSE 0.0
             END AS completion_bonus,
             CASE
                 WHEN toFloat(query_length) / quote_length >= 0.55 THEN 35.0
                 WHEN toFloat(query_length) / quote_length >= 0.35 THEN 22.0
                 WHEN toFloat(query_length) / quote_length >= 0.2 THEN 10.0
                 ELSE 0.0
             END AS coverage_bonus,
             CASE
                 WHEN prefix_gap = 0 THEN 25.0
                 WHEN prefix_gap <= 20 THEN 8.0
                 WHEN prefix_gap <= 60 THEN -4.0
                 ELSE -15.0
             END AS prefix_bonus,
             CASE occurrence.quote_type
                 WHEN 'sourced' THEN 20.0
                 WHEN 'template' THEN 15.0
                 WHEN 'blockquote' THEN 12.0
                 WHEN 'attributed' THEN -10.0
                 ELSE -25.0
             END AS quote_type_bonus,
             CASE
                 WHEN source.title IS NOT NULL THEN 12.0
                 ELSE -15.0
             END AS source_bonus,
             {page_type_multiplier_case} AS page_type_multiplier,
             CASE
                 WHEN normalized_quote STARTS WITH query_normalized THEN 'beginning'
                 WHEN normalized_quote ENDS WITH query_normalized THEN 'end'
                 WHEN (' ' + normalized_quote) CONTAINS (' ' + query_normalized + ' ') THEN 'middle'
                 ELSE 'distributed'
             END AS match_position

        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               occurrence.page_type AS page_type,
               occurrence.quote_type AS quote_type,
               ((position_score + length_bonus + completion_bonus + coverage_bonus + prefix_bonus + quote_type_bonus + source_bonus) * page_type_multiplier) / 100.0 AS relevance_score,
               quote_length,
               match_position,
               CASE WHEN $scope = 'primary' THEN 'partial_match_primary' ELSE 'partial_match_secondary' END AS search_type
        
        ORDER BY relevance_score DESC, quote_length ASC
        LIMIT $limit
        """
        
        try:
            with self.session() as session:
                result = session.run(
                    cypher_query,
                    search_normalized=normalized_query,
                    limit=limit,
                    scope=scope,
                    primary_page_types=list(self.PRIMARY_PAGE_TYPES),
                    primary_quote_types=list(self.PRIMARY_QUOTE_TYPES),
                )
                results = [dict(record) for record in result]
                logger.info(f"Partial quote search ({scope}) found {len(results)} matches for '{query}'")
                return results
        except Exception as e:
            logger.error(f"Error in partial quote search: {e}")
            return self._keyword_search(query, limit, scope=scope)
    
    def _fulltext_search(self, query: str, limit: int, scope: str = "primary") -> List[Dict[str, Any]]:
        """Full-text search using Neo4j indexes tuned for the requested corpus scope."""
        normalized_query = self._normalize_search_text(query)
        search_query = self._prepare_fulltext_query(normalized_query or query)
        page_type_multiplier_case = self._page_type_multiplier_case()
        scope_condition = self._scope_condition(scope)
        index_name = self._fulltext_index_name(scope)
        
        cypher_query = f"""
        CALL db.index.fulltext.queryNodes('{index_name}', $search_query)
        YIELD node AS quote, score

        MATCH (quote)-[:HAS_OCCURRENCE]->(occurrence:QuoteOccurrence)-[:CITED_AS]->(source:Source)
        MATCH (occurrence)-[:ATTRIBUTED_TO]->(author:Author)

        WHERE {scope_condition}

        WITH quote, occurrence, author, source, score,
             coalesce(quote.normalized_text, quote.canonical_text, quote.text) AS normalized_quote,
             size(quote.text) AS quote_length,
             size($normalized_query) AS query_length

        WHERE quote_length >= 15 AND quote_length <= 320

        WITH quote, occurrence, author, source, normalized_quote, quote_length, query_length,
             score * CASE 
                 WHEN quote_length >= 18 AND quote_length <= 160 THEN 1.8
                 WHEN quote_length > 160 AND quote_length <= 240 THEN 1.35
                 ELSE 1.0
             END * CASE
                 WHEN query_length > 0 AND toFloat(query_length) / quote_length >= 0.35 THEN 1.35
                 WHEN query_length > 0 AND toFloat(query_length) / quote_length >= 0.2 THEN 1.15
                 ELSE 1.0
             END * CASE
                 WHEN source.title IS NOT NULL THEN 1.15
                 ELSE 0.75
             END * CASE
                 WHEN occurrence.quote_type = 'sourced' THEN 1.2
                 WHEN occurrence.quote_type IN ['template', 'blockquote'] THEN 1.1
                 ELSE 0.8
             END * CASE
                 WHEN normalized_quote STARTS WITH $normalized_query THEN 1.45
                 WHEN (' ' + normalized_quote) CONTAINS (' ' + $normalized_query + ' ') THEN 1.15
                 ELSE 1.0
             END * CASE
                 WHEN size(split(normalized_quote, $normalized_query)[0]) = 0 THEN 1.2
                 WHEN size(split(normalized_quote, $normalized_query)[0]) <= 24 THEN 1.05
                 ELSE 0.85
             END * {page_type_multiplier_case} AS adjusted_score

        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               occurrence.page_type AS page_type,
               occurrence.quote_type AS quote_type,
               adjusted_score AS relevance_score,
               quote_length,
               CASE WHEN $scope = 'primary' THEN 'fulltext_primary' ELSE 'fulltext_secondary' END AS search_type
        
        ORDER BY adjusted_score DESC, quote_length ASC
        LIMIT $limit
        """
        
        try:
            with self.session() as session:
                result = session.run(
                    cypher_query,
                    search_query=search_query,
                    normalized_query=normalized_query or query.lower(),
                    limit=limit,
                    scope=scope,
                    primary_page_types=list(self.PRIMARY_PAGE_TYPES),
                    primary_quote_types=list(self.PRIMARY_QUOTE_TYPES),
                )
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Error in full-text search: {e}")
            return []
    
    def _keyword_search(self, query: str, limit: int, scope: str = "primary") -> List[Dict[str, Any]]:
        """Keyword-based search for individual words in the query."""
        keywords = self._extract_keywords(query)
        if not keywords:
            return []
        page_type_multiplier_case = self._page_type_multiplier_case()
        scope_condition = self._scope_condition(scope)
        
        # Create CONTAINS conditions for each keyword
        conditions = []
        params = {}
        for i, keyword in enumerate(keywords):
            param_name = f"keyword_{i}"
            conditions.append(f"coalesce(quote.normalized_text, quote.canonical_text, quote.text) CONTAINS ${param_name}")
            params[param_name] = keyword
        
        where_clause = " AND ".join(conditions)
        
        cypher_query = f"""
        MATCH (quote:Quote)-[:HAS_OCCURRENCE]->(occurrence:QuoteOccurrence)-[:CITED_AS]->(source:Source)
        MATCH (occurrence)-[:ATTRIBUTED_TO]->(author:Author)
        WHERE {scope_condition} AND {where_clause}
        
        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               occurrence.page_type AS page_type,
               occurrence.quote_type AS quote_type,
               0.75
               * CASE WHEN source.title IS NOT NULL THEN 1.1 ELSE 0.75 END
               * CASE WHEN occurrence.quote_type = 'sourced' THEN 1.1 ELSE 0.85 END
               * {page_type_multiplier_case} AS relevance_score,
               CASE WHEN $scope = 'primary' THEN 'keyword_primary' ELSE 'keyword_secondary' END AS search_type
        
        ORDER BY size(quote.text) ASC
        LIMIT $limit
        """
        
        try:
            with self.session() as session:
                result = session.run(
                    cypher_query,
                    limit=limit,
                    scope=scope,
                    primary_page_types=list(self.PRIMARY_PAGE_TYPES),
                    primary_quote_types=list(self.PRIMARY_QUOTE_TYPES),
                    **params,
                )
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Error in keyword search: {e}")
            return []
    
    def _fuzzy_search(self, query: str, limit: int, scope: str = "primary") -> List[Dict[str, Any]]:
        """Fuzzy search using similarity matching."""
        page_type_multiplier_case = self._page_type_multiplier_case()
        scope_condition = self._scope_condition(scope)
        normalized_query = self._normalize_search_text(query)
        
        cypher_query = f"""
        MATCH (quote:Quote)-[:HAS_OCCURRENCE]->(occurrence:QuoteOccurrence)-[:CITED_AS]->(source:Source)
        MATCH (occurrence)-[:ATTRIBUTED_TO]->(author:Author)
        WHERE {scope_condition}
        
        // Calculate similarity based on common words
        WITH quote, occurrence, author, source,
             [word IN split($search_query, ' ') WHERE word IN split(coalesce(quote.normalized_text, quote.canonical_text, quote.text), ' ')] AS common_words
        WHERE size(common_words) > 0
        
        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               occurrence.page_type AS page_type,
               occurrence.quote_type AS quote_type,
               (toFloat(size(common_words)) / size(split($search_query, ' ')))
               * CASE WHEN source.title IS NOT NULL THEN 1.05 ELSE 0.8 END
               * CASE WHEN occurrence.quote_type = 'sourced' THEN 1.1 ELSE 0.85 END
               * {page_type_multiplier_case} AS relevance_score,
               CASE WHEN $scope = 'primary' THEN 'fuzzy_primary' ELSE 'fuzzy_secondary' END AS search_type
        
        ORDER BY relevance_score DESC
        LIMIT $limit
        """
        
        try:
            with self.session() as session:
                result = session.run(
                    cypher_query,
                    search_query=normalized_query,
                    limit=limit,
                    scope=scope,
                    primary_page_types=list(self.PRIMARY_PAGE_TYPES),
                    primary_quote_types=list(self.PRIMARY_QUOTE_TYPES),
                )
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Error in fuzzy search: {e}")
            return []
    
    def search_by_author(self, author_query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Enhanced author search - prioritizes exact matches over partial matches."""
        page_type_multiplier_case = self._page_type_multiplier_case()
        
        # Prioritize authors where the query matches the START of a word in their name
        # e.g., "einstein" should match "Albert Einstein" but not "Bret Weinstein"
        cypher_query = f"""
        MATCH (occurrence:QuoteOccurrence)-[:ATTRIBUTED_TO]->(author:Author)
        MATCH (quote:Quote)-[:HAS_OCCURRENCE]->(occurrence)-[:CITED_AS]->(source:Source)
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
        
        WITH quote, author, source, match_score,
             match_score * {page_type_multiplier_case} AS adjusted_score

        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               adjusted_score AS relevance_score
        
        ORDER BY adjusted_score DESC, size(author.name) ASC, quote.text
        LIMIT $limit
        """
        
        try:
            with self.session() as session:
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
        page_type_multiplier_case = self._page_type_multiplier_case()
        # Search for authors where most characters match
        cypher_query = f"""
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
        MATCH (occurrence:QuoteOccurrence)-[:ATTRIBUTED_TO]->(author)
        MATCH (quote:Quote)-[:HAS_OCCURRENCE]->(occurrence)-[:CITED_AS]->(source:Source)
        
        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               0.8 * {page_type_multiplier_case} AS relevance_score
        
        ORDER BY size(author.name), quote.text
        LIMIT $limit
        """
        
        try:
            with self.session() as session:
                result = session.run(cypher_query, author_query=author_query, limit=limit)
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Error in fuzzy author search: {e}")
            return []
    
    def search_by_theme(self, theme: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search quotes by theme or topic."""
        # Define theme-related keywords
        theme_keywords = self._get_theme_keywords(theme.lower())
        page_type_multiplier_case = self._page_type_multiplier_case()
        
        if not theme_keywords:
            # Fallback to direct search
            return self.search_quotes(theme, limit)
        
        # Create search query with theme keywords
        search_terms = " OR ".join(theme_keywords)
        
        cypher_query = f"""
        CALL db.index.fulltext.queryNodes('quote_fulltext_index', $search_terms)
        YIELD node AS quote, score

        MATCH (quote)-[:HAS_OCCURRENCE]->(occurrence:QuoteOccurrence)-[:CITED_AS]->(source:Source)
        MATCH (occurrence)-[:ATTRIBUTED_TO]->(author:Author)

        WITH quote, occurrence, author, source, score,
             score * {page_type_multiplier_case} AS adjusted_score

        RETURN DISTINCT quote.text AS quote_text,
               author.name AS author_name,
               source.title AS source_title,
               adjusted_score AS relevance_score
        
        ORDER BY adjusted_score DESC
        LIMIT $limit
        """
        
        try:
            with self.session() as session:
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
        MATCH (occurrence:QuoteOccurrence)-[:ATTRIBUTED_TO]->(author:Author)
        WITH author, count(DISTINCT occurrence) AS quote_count
        ORDER BY quote_count DESC
        LIMIT $limit
        
        RETURN author.name AS author_name,
               quote_count
        """
        
        try:
            with self.session() as session:
                result = session.run(cypher_query, limit=limit)
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Error getting popular authors: {e}")
            return []
    
    def get_random_quote(self, author: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a random quote, optionally from a specific author."""
        if author:
            cypher_query = """
            MATCH (occurrence:QuoteOccurrence)-[:ATTRIBUTED_TO]->(author:Author)
            MATCH (quote:Quote)-[:HAS_OCCURRENCE]->(occurrence)-[:CITED_AS]->(source:Source)
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
            MATCH (occurrence:QuoteOccurrence)-[:ATTRIBUTED_TO]->(author:Author)
            MATCH (quote:Quote)-[:HAS_OCCURRENCE]->(occurrence)-[:CITED_AS]->(source:Source)
            
            WITH quote, author, source, rand() AS r
            ORDER BY r
            LIMIT 1
            
            RETURN quote.text AS quote_text,
                   author.name AS author_name,
                   source.title AS source_title
            """
            params = {}
        
        try:
            with self.session() as session:
                result = session.run(cypher_query, **params)
                record = result.single()
                return dict(record) if record else None
        except Exception as e:
            logger.error(f"Error getting random quote: {e}")
            return None
    
    def _prepare_fulltext_query(self, query: str) -> str:
        """Prepare query for full-text search."""
        # Clean the query
        query = self._normalize_search_text(query).strip() or query.strip()
        
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
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'quote', 'quotes', 'about'}
        
        # Clean and split query
        words = self._normalize_search_text(query).split()
        
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
    search_service = QuoteSearchService(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)
    
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
    search_service = QuoteSearchService(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)
    
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
