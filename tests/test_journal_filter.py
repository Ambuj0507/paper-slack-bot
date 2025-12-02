"""Tests for journal filter module."""

import pytest

from paper_slack_bot.config import JournalConfig
from paper_slack_bot.search.journal_filter import (
    JournalFilter,
    JournalInfo,
    PREPRINT_SERVERS,
)
from paper_slack_bot.storage.database import Paper


class TestJournalFilter:
    """Tests for journal filter."""

    @pytest.fixture
    def filter(self):
        """Create a journal filter with default config."""
        return JournalFilter()

    @pytest.fixture
    def custom_filter(self):
        """Create a journal filter with custom exclude config."""
        config = JournalConfig(
            exclude=["Bad Journal"],
        )
        return JournalFilter(config)

    @pytest.fixture
    def sample_papers(self):
        """Create sample papers for testing."""
        return [
            Paper(
                title="Paper 1",
                authors=["Author 1"],
                abstract="Abstract 1",
                doi="10.1234/1",
                journal="Nature",
                publication_date="2024-01-01",
                url="https://example.com/1",
                source="pubmed",
            ),
            Paper(
                title="Paper 2",
                authors=["Author 2"],
                abstract="Abstract 2",
                doi="10.1234/2",
                journal="bioRxiv",
                publication_date="2024-01-02",
                url="https://example.com/2",
                source="biorxiv",
            ),
            Paper(
                title="Paper 3",
                authors=["Author 3"],
                abstract="Abstract 3",
                doi="10.1234/3",
                journal="Unknown Journal",
                publication_date="2024-01-03",
                url="https://example.com/3",
                source="pubmed",
            ),
            Paper(
                title="Paper 4",
                authors=["Author 4"],
                abstract="Abstract 4",
                doi="10.1234/4",
                journal="arXiv",
                publication_date="2024-01-04",
                url="https://example.com/4",
                source="arxiv",
            ),
        ]

    def test_normalize_journal_name(self, filter):
        """Test journal name normalization."""
        assert filter.normalize_journal_name("  Nature  ") == "Nature"
        assert filter.normalize_journal_name("nejm") == "The New England Journal of Medicine"
        assert filter.normalize_journal_name("pnas") == "Proceedings of the National Academy of Sciences"

    def test_is_preprint(self, filter):
        """Test preprint detection."""
        assert filter.is_preprint("bioRxiv") is True
        assert filter.is_preprint("arXiv") is True
        assert filter.is_preprint("medRxiv") is True
        assert filter.is_preprint("Nature") is False
        assert filter.is_preprint("Science") is False

    def test_get_journal_emoji(self, filter):
        """Test getting journal emoji."""
        # Preprints get the preprint emoji
        assert filter.get_journal_emoji("bioRxiv") == "📝"
        assert filter.get_journal_emoji("arXiv") == "📝"
        # Journals get the journal emoji
        assert filter.get_journal_emoji("Nature") == "📰"
        assert filter.get_journal_emoji("Unknown") == "📰"

    def test_get_journal_info(self, filter):
        """Test getting full journal info."""
        info = filter.get_journal_info("Nature")
        
        assert isinstance(info, JournalInfo)
        assert info.name == "Nature"
        assert info.is_preprint is False
        assert info.emoji == "📰"

        info_preprint = filter.get_journal_info("bioRxiv")
        assert info_preprint.is_preprint is True
        assert info_preprint.emoji == "📝"

    def test_filter_papers_includes_all_by_default(self, filter, sample_papers):
        """Test that all papers are included by default."""
        filtered, excluded = filter.filter_papers(sample_papers)
        
        assert len(filtered) == 4
        assert excluded == []

    def test_filter_papers_by_exclude_list(self, filter, sample_papers):
        """Test filtering papers by exclude list."""
        filtered, excluded = filter.filter_papers(
            sample_papers,
            exclude_journals=["Nature"],
        )
        
        journals = [p.journal for p in filtered]
        assert "Nature" not in journals
        assert len(filtered) == 3
        assert excluded == ["Nature"]

    def test_filter_papers_empty_list(self, filter):
        """Test filtering empty paper list."""
        filtered, excluded = filter.filter_papers([])
        assert filtered == []
        assert excluded == []

    def test_categorize_papers(self, filter, sample_papers):
        """Test categorizing papers into journals vs preprints."""
        categorized = filter.categorize_papers(sample_papers)
        
        # Should have 'journals' and 'preprints' keys
        assert "journals" in categorized
        assert "preprints" in categorized
        
        # Check journals
        journal_names = [p.journal for p in categorized["journals"]]
        assert "Nature" in journal_names
        assert "Unknown Journal" in journal_names
        
        # Check preprints
        preprint_names = [p.journal for p in categorized["preprints"]]
        assert "bioRxiv" in preprint_names
        assert "arXiv" in preprint_names

    def test_custom_config_exclude(self, custom_filter, sample_papers):
        """Test filter with custom exclude configuration."""
        # Add a paper from excluded journal
        bad_paper = Paper(
            title="Bad Paper",
            authors=["Author"],
            abstract="Abstract",
            doi="10.1234/bad",
            journal="Bad Journal",
            publication_date="2024-01-05",
            url="https://example.com/bad",
            source="pubmed",
        )
        papers_with_bad = sample_papers + [bad_paper]
        
        filtered, excluded = custom_filter.filter_papers(papers_with_bad)
        
        journals = [p.journal for p in filtered]
        assert "Bad Journal" not in journals
        assert len(filtered) == 4  # Original 4, excluding the bad one

    def test_preprint_servers_constant(self):
        """Test that preprint servers constant is defined correctly."""
        assert "bioRxiv" in PREPRINT_SERVERS
        assert "arXiv" in PREPRINT_SERVERS
        assert "medRxiv" in PREPRINT_SERVERS
