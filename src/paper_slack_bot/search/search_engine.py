"""Enhanced search engine with semantic search and advanced filtering."""

import logging
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np

from paper_slack_bot.storage.database import Database, Paper, SearchQuery

logger = logging.getLogger(__name__)


@dataclass
class SearchFilters:
    """Search filters for paper queries."""

    authors: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    title_keywords: list[str] | None = None
    abstract_keywords: list[str] | None = None
    exclude_terms: list[str] | None = None
    journals: list[str] | None = None
    sources: list[str] | None = None
    min_relevance_score: float | None = None


class BooleanQueryParser:
    """Parser for boolean search queries."""

    def __init__(self):
        """Initialize the parser."""
        self.operators = {"AND", "OR", "NOT"}

    def parse(self, query: str) -> dict:
        """Parse a boolean query string.

        Args:
            query: Query string with boolean operators.

        Returns:
            Parsed query structure.
        """
        # Handle quoted phrases
        phrases = re.findall(r'"([^"]+)"', query)
        query_no_quotes = re.sub(r'"[^"]+"', " PHRASE ", query)

        # Tokenize
        tokens = query_no_quotes.upper().split()

        # Build query structure
        result = {
            "must": [],
            "should": [],
            "must_not": [],
        }

        phrase_idx = 0
        next_is_not = False
        in_or_chain = False
        or_terms: list[str] = []

        i = 0
        while i < len(tokens):
            token = tokens[i]
            
            if token == "NOT":
                next_is_not = True
            elif token == "OR":
                in_or_chain = True
                # If there was a previous term in must, move it to OR terms
                if result["must"] and not or_terms:
                    or_terms.append(result["must"].pop())
            elif token == "AND":
                # Flush OR terms if any
                if or_terms:
                    result["should"].extend(or_terms)
                    or_terms = []
                in_or_chain = False
            elif token == "PHRASE":
                if phrase_idx < len(phrases):
                    term = phrases[phrase_idx].lower()
                    phrase_idx += 1
                    if next_is_not:
                        result["must_not"].append(term)
                        next_is_not = False
                    elif in_or_chain:
                        or_terms.append(term)
                    else:
                        result["must"].append(term)
            else:
                term = token.lower()
                if next_is_not:
                    result["must_not"].append(term)
                    next_is_not = False
                elif in_or_chain:
                    or_terms.append(term)
                else:
                    result["must"].append(term)
            
            i += 1

        # Flush any remaining OR terms
        if or_terms:
            result["should"].extend(or_terms)

        return result

    def _add_term(self, result: dict, term: str, operator: str) -> None:
        """Add a term to the result structure.

        Args:
            result: Result dictionary.
            term: Term to add.
            operator: Current boolean operator.
        """
        if operator == "NOT":
            result["must_not"].append(term)
        elif operator == "OR":
            result["should"].append(term)
        else:  # AND or default
            result["must"].append(term)

    def matches(self, parsed_query: dict, text: str) -> bool:
        """Check if text matches the parsed query.

        Args:
            parsed_query: Parsed query structure.
            text: Text to match against.

        Returns:
            True if text matches query.
        """
        text_lower = text.lower()

        # Check must_not (any match = fail)
        for term in parsed_query["must_not"]:
            if term in text_lower:
                return False

        # Check must (all must match)
        for term in parsed_query["must"]:
            if term not in text_lower:
                return False

        # Check should (at least one must match if no must terms)
        if parsed_query["should"] and not parsed_query["must"]:
            if not any(term in text_lower for term in parsed_query["should"]):
                return False

        return True


class SemanticSearch:
    """Semantic search using sentence embeddings."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize semantic search.

        Args:
            model_name: Name of the sentence-transformers model.
        """
        self.model_name = model_name
        self._model = None
        self._model_load_attempted = False

    @property
    def model(self):
        """Lazy load the model."""
        if self._model is None and not self._model_load_attempted:
            self._model_load_attempted = True
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
            except (ImportError, OSError) as e:
                logger.warning(
                    f"Could not load sentence-transformers model: {e}. "
                    "Semantic search will not be available."
                )
        return self._model
        return self._model

    def encode(self, texts: list[str]) -> Optional[np.ndarray]:
        """Encode texts to embeddings.

        Args:
            texts: List of texts to encode.

        Returns:
            NumPy array of embeddings or None if model unavailable.
        """
        if self.model is None:
            return None
        return self.model.encode(texts, convert_to_numpy=True)

    def search(
        self,
        query: str,
        papers: list[Paper],
        top_k: int = 50,
    ) -> list[tuple[Paper, float]]:
        """Perform semantic search on papers.

        Args:
            query: Search query.
            papers: List of papers to search.
            top_k: Number of top results to return.

        Returns:
            List of (paper, score) tuples sorted by relevance.
        """
        if self.model is None or not papers:
            return [(p, 1.0) for p in papers[:top_k]]

        # Combine title and abstract for paper representation
        paper_texts = [f"{p.title} {p.abstract}" for p in papers]

        # Encode query and papers
        query_embedding = self.encode([query])[0]
        paper_embeddings = self.encode(paper_texts)

        # Compute cosine similarity
        similarities = self._cosine_similarity(query_embedding, paper_embeddings)

        # Sort by similarity
        sorted_indices = np.argsort(similarities)[::-1][:top_k]

        return [(papers[i], float(similarities[i])) for i in sorted_indices]

    def _cosine_similarity(
        self, query: np.ndarray, documents: np.ndarray
    ) -> np.ndarray:
        """Compute cosine similarity between query and documents.

        Args:
            query: Query embedding.
            documents: Document embeddings.

        Returns:
            Array of similarity scores.
        """
        query_norm = query / np.linalg.norm(query)
        doc_norms = documents / np.linalg.norm(documents, axis=1, keepdims=True)
        return np.dot(doc_norms, query_norm)


class SearchEngine:
    """Enhanced search engine combining keyword and semantic search."""

    def __init__(self, database: Database, use_semantic: bool = True):
        """Initialize the search engine.

        Args:
            database: Database instance for search history.
            use_semantic: Whether to enable semantic search.
        """
        self.database = database
        self.query_parser = BooleanQueryParser()
        self.semantic_search = SemanticSearch() if use_semantic else None

    def search(
        self,
        query: str,
        papers: list[Paper],
        filters: Optional[SearchFilters] = None,
        use_semantic: bool = True,
        user_id: Optional[str] = None,
    ) -> list[Paper]:
        """Search papers with keyword and optional semantic search.

        Args:
            query: Search query string.
            papers: List of papers to search.
            filters: Optional search filters.
            use_semantic: Whether to use semantic search.
            user_id: Optional user ID for history.

        Returns:
            List of matching papers sorted by relevance.
        """
        if not papers:
            return []

        # Parse boolean query
        parsed_query = self.query_parser.parse(query)

        # Apply keyword filtering
        filtered_papers = []
        for paper in papers:
            text = f"{paper.title} {paper.abstract}"
            if self.query_parser.matches(parsed_query, text):
                filtered_papers.append(paper)

        # Apply additional filters
        if filters:
            filtered_papers = self._apply_filters(filtered_papers, filters)

        # Apply semantic search for ranking
        if use_semantic and self.semantic_search and filtered_papers:
            results = self.semantic_search.search(query, filtered_papers)
            filtered_papers = [paper for paper, _ in results]

        # Save search to history
        self._save_search_history(query, filters, len(filtered_papers), user_id)

        return filtered_papers

    def _apply_filters(
        self, papers: list[Paper], filters: SearchFilters
    ) -> list[Paper]:
        """Apply additional filters to papers.

        Args:
            papers: List of papers to filter.
            filters: Search filters to apply.

        Returns:
            Filtered list of papers.
        """
        filtered = papers

        # Filter by authors
        if filters.authors:
            authors_lower = [a.lower() for a in filters.authors]
            filtered = [
                p
                for p in filtered
                if any(
                    author.lower() in a.lower()
                    for author in authors_lower
                    for a in p.authors
                )
            ]

        # Filter by date range
        if filters.date_from:
            filtered = [
                p for p in filtered if p.publication_date >= filters.date_from
            ]
        if filters.date_to:
            filtered = [p for p in filtered if p.publication_date <= filters.date_to]

        # Filter by title keywords
        if filters.title_keywords:
            filtered = [
                p
                for p in filtered
                if any(kw.lower() in p.title.lower() for kw in filters.title_keywords)
            ]

        # Filter by abstract keywords
        if filters.abstract_keywords:
            filtered = [
                p
                for p in filtered
                if any(
                    kw.lower() in p.abstract.lower() for kw in filters.abstract_keywords
                )
            ]

        # Exclude terms
        if filters.exclude_terms:
            filtered = [
                p
                for p in filtered
                if not any(
                    term.lower() in f"{p.title} {p.abstract}".lower()
                    for term in filters.exclude_terms
                )
            ]

        # Filter by journals
        if filters.journals:
            journals_lower = [j.lower() for j in filters.journals]
            filtered = [
                p for p in filtered if p.journal.lower() in journals_lower
            ]

        # Filter by sources
        if filters.sources:
            sources_lower = [s.lower() for s in filters.sources]
            filtered = [p for p in filtered if p.source.lower() in sources_lower]

        # Filter by relevance score
        if filters.min_relevance_score is not None:
            filtered = [
                p
                for p in filtered
                if p.relevance_score is not None
                and p.relevance_score >= filters.min_relevance_score
            ]

        return filtered

    def _save_search_history(
        self,
        query: str,
        filters: Optional[SearchFilters],
        result_count: int,
        user_id: Optional[str],
    ) -> None:
        """Save search query to history.

        Args:
            query: Search query.
            filters: Search filters used.
            result_count: Number of results.
            user_id: User ID.
        """
        try:
            filter_dict = {}
            if filters:
                filter_dict = {
                    "authors": filters.authors,
                    "date_from": filters.date_from,
                    "date_to": filters.date_to,
                    "title_keywords": filters.title_keywords,
                    "abstract_keywords": filters.abstract_keywords,
                    "exclude_terms": filters.exclude_terms,
                    "journals": filters.journals,
                    "sources": filters.sources,
                    "min_relevance_score": filters.min_relevance_score,
                }
            search_query = SearchQuery(
                query=query,
                filters=filter_dict,
                result_count=result_count,
                user_id=user_id,
            )
            self.database.save_search_query(search_query)
        except Exception as e:
            logger.error(f"Error saving search history: {e}")

    def get_search_history(
        self, user_id: Optional[str] = None, limit: int = 50
    ) -> list[SearchQuery]:
        """Get search history.

        Args:
            user_id: Optional user ID to filter by.
            limit: Maximum number of results.

        Returns:
            List of SearchQuery objects.
        """
        return self.database.get_search_history(user_id, limit)
