"""Tests for search engine module."""

import pytest
from unittest.mock import MagicMock

from paper_slack_bot.search.search_engine import (
    SearchEngine,
    SearchFilters,
    BooleanQueryParser,
    SemanticSearch,
)
from paper_slack_bot.storage.database import Database, Paper


class TestBooleanQueryParser:
    """Tests for boolean query parser."""

    @pytest.fixture
    def parser(self):
        """Create a query parser."""
        return BooleanQueryParser()

    def test_parse_simple_query(self, parser):
        """Test parsing a simple query."""
        result = parser.parse("machine learning")
        
        assert "machine" in result["must"]
        assert "learning" in result["must"]

    def test_parse_and_query(self, parser):
        """Test parsing AND query."""
        result = parser.parse("deep AND learning")
        
        assert "deep" in result["must"]
        assert "learning" in result["must"]

    def test_parse_or_query(self, parser):
        """Test parsing OR query."""
        result = parser.parse("genomics OR proteomics")
        
        assert "genomics" in result["should"]
        assert "proteomics" in result["should"]

    def test_parse_not_query(self, parser):
        """Test parsing NOT query."""
        result = parser.parse("machine learning NOT clinical")
        
        assert "machine" in result["must"]
        assert "learning" in result["must"]
        assert "clinical" in result["must_not"]

    def test_parse_quoted_phrase(self, parser):
        """Test parsing quoted phrases."""
        result = parser.parse('"machine learning" AND biology')
        
        assert "machine learning" in result["must"]
        assert "biology" in result["must"]

    def test_matches_must_terms(self, parser):
        """Test matching must terms."""
        parsed = {"must": ["machine", "learning"], "should": [], "must_not": []}
        
        assert parser.matches(parsed, "Machine Learning for Biology")
        assert not parser.matches(parsed, "Deep Learning for Biology")

    def test_matches_not_terms(self, parser):
        """Test matching NOT terms."""
        parsed = {"must": ["learning"], "should": [], "must_not": ["clinical"]}
        
        assert parser.matches(parsed, "Deep Learning Methods")
        assert not parser.matches(parsed, "Clinical Learning Study")

    def test_matches_or_terms(self, parser):
        """Test matching OR terms."""
        parsed = {"must": [], "should": ["genomics", "proteomics"], "must_not": []}
        
        assert parser.matches(parsed, "Genomics Study")
        assert parser.matches(parsed, "Proteomics Analysis")
        assert not parser.matches(parsed, "Clinical Study")


class TestSearchFilters:
    """Tests for search filters."""

    def test_default_filters(self):
        """Test default filter values."""
        filters = SearchFilters()
        
        assert filters.authors is None
        assert filters.date_from is None
        assert filters.journals is None

    def test_custom_filters(self):
        """Test custom filter values."""
        filters = SearchFilters(
            authors=["Smith", "Jones"],
            date_from="2024-01-01",
            journals=["Nature", "Science"],
        )
        
        assert filters.authors == ["Smith", "Jones"]
        assert filters.date_from == "2024-01-01"
        assert filters.journals == ["Nature", "Science"]


class TestSearchEngine:
    """Tests for search engine."""

    @pytest.fixture
    def mock_database(self, tmp_path):
        """Create a mock database."""
        db_path = tmp_path / "test.db"
        return Database(db_path)

    @pytest.fixture
    def search_engine(self, mock_database):
        """Create a search engine."""
        return SearchEngine(mock_database, use_semantic=False)

    @pytest.fixture
    def sample_papers(self):
        """Create sample papers for testing."""
        return [
            Paper(
                title="Machine Learning for Genomics",
                authors=["John Smith", "Jane Doe"],
                abstract="Deep learning applied to genomic data analysis.",
                doi="10.1234/ml-genomics",
                journal="Nature",
                publication_date="2024-01-15",
                url="https://example.com/1",
                source="pubmed",
            ),
            Paper(
                title="Clinical Trial Results",
                authors=["Bob Wilson"],
                abstract="Results from a clinical trial on drug efficacy.",
                doi="10.1234/clinical",
                journal="Lancet",
                publication_date="2024-01-10",
                url="https://example.com/2",
                source="pubmed",
            ),
            Paper(
                title="Protein Structure Prediction",
                authors=["Alice Brown", "John Smith"],
                abstract="New methods for predicting protein structures using AI.",
                doi="10.1234/protein",
                journal="Science",
                publication_date="2024-01-05",
                url="https://example.com/3",
                source="pubmed",
            ),
        ]

    def test_search_keyword_match(self, search_engine, sample_papers):
        """Test keyword search."""
        results = search_engine.search("machine learning", sample_papers)
        
        assert len(results) == 1
        assert results[0].title == "Machine Learning for Genomics"

    def test_search_boolean_query(self, search_engine, sample_papers):
        """Test boolean query search."""
        results = search_engine.search("learning NOT clinical", sample_papers)
        
        assert len(results) == 1
        assert "Machine Learning" in results[0].title

    def test_search_with_author_filter(self, search_engine, sample_papers):
        """Test search with author filter."""
        filters = SearchFilters(authors=["John Smith"])
        results = search_engine.search("learning", sample_papers, filters=filters)
        
        # Should only return papers by John Smith that match "learning"
        for paper in results:
            assert any("Smith" in a for a in paper.authors)

    def test_search_with_journal_filter(self, search_engine, sample_papers):
        """Test search with journal filter."""
        filters = SearchFilters(journals=["Nature"])
        results = search_engine.search("learning", sample_papers, filters=filters)
        
        for paper in results:
            assert paper.journal == "Nature"

    def test_search_with_exclude_terms(self, search_engine, sample_papers):
        """Test search with exclude terms."""
        filters = SearchFilters(exclude_terms=["clinical"])
        results = search_engine.search("learning", sample_papers, filters=filters)
        
        for paper in results:
            assert "clinical" not in paper.title.lower()
            assert "clinical" not in paper.abstract.lower()

    def test_search_saves_history(self, search_engine, sample_papers):
        """Test that search saves to history."""
        search_engine.search("machine learning", sample_papers, user_id="U12345")
        
        history = search_engine.get_search_history(user_id="U12345")
        assert len(history) >= 1
        assert history[0].query == "machine learning"

    def test_search_empty_papers(self, search_engine):
        """Test search with empty paper list."""
        results = search_engine.search("test", [])
        assert results == []


class TestSemanticSearch:
    """Tests for semantic search."""

    def test_init_without_model(self):
        """Test initialization without model loading."""
        search = SemanticSearch()
        assert search._model is None
        assert search._model_load_attempted is False

    def test_search_without_model_returns_defaults(self):
        """Test search when model is not available returns default scores."""
        # Create a search instance and prevent model loading
        search = SemanticSearch.__new__(SemanticSearch)
        search.model_name = "test-model"
        search._model = None  # Simulate model not available
        search._model_load_attempted = True  # Prevent lazy loading
        
        papers = [
            Paper(
                title="Test Paper",
                authors=["Author"],
                abstract="Abstract",
                doi="10.1234/test",
                journal="Journal",
                publication_date="2024-01-01",
                url="https://example.com",
                source="pubmed",
            )
        ]
        
        # Should return papers with default scores when model unavailable
        results = search.search("query", papers)
        assert len(results) == 1
        assert results[0][1] == 1.0  # Default score
