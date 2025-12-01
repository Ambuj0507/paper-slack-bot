"""Tests for journal filter module."""

import pytest

from paper_slack_bot.config import JournalConfig
from paper_slack_bot.search.journal_filter import (
    JournalFilter,
    JournalInfo,
    JOURNAL_TIERS,
    JOURNAL_EMOJIS,
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
        """Create a journal filter with custom config."""
        config = JournalConfig(
            include=["Custom Journal"],
            exclude=["Bad Journal"],
            tiers=["tier1"],
            show_preprints=True,
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
                journal="NeurIPS",
                publication_date="2024-01-04",
                url="https://example.com/4",
                source="pubmed",
            ),
        ]

    def test_normalize_journal_name(self, filter):
        """Test journal name normalization."""
        assert filter.normalize_journal_name("  Nature  ") == "Nature"
        assert filter.normalize_journal_name("nejm") == "The New England Journal of Medicine"
        assert filter.normalize_journal_name("pnas") == "Proceedings of the National Academy of Sciences"

    def test_get_journal_tier(self, filter):
        """Test getting journal tier."""
        assert filter.get_journal_tier("Nature") == "tier1"
        assert filter.get_journal_tier("Science") == "tier1"
        assert filter.get_journal_tier("Nature Methods") == "tier2"
        assert filter.get_journal_tier("NeurIPS") == "ml"
        assert filter.get_journal_tier("bioRxiv") == "preprints"
        assert filter.get_journal_tier("Unknown Journal") is None

    def test_get_journal_emoji(self, filter):
        """Test getting journal emoji."""
        assert filter.get_journal_emoji("Nature") == "🏆"
        assert filter.get_journal_emoji("Nature Methods") == "⭐"
        assert filter.get_journal_emoji("NeurIPS") == "🤖"
        assert filter.get_journal_emoji("bioRxiv") == "📝"
        assert filter.get_journal_emoji("Unknown") == "📄"

    def test_get_journal_info(self, filter):
        """Test getting full journal info."""
        info = filter.get_journal_info("Nature")
        
        assert isinstance(info, JournalInfo)
        assert info.name == "Nature"
        assert info.tier == "tier1"
        assert info.emoji == "🏆"

    def test_filter_papers_by_tier(self, filter, sample_papers):
        """Test filtering papers by tier."""
        filtered = filter.filter_papers(
            sample_papers,
            tiers=["tier1"],
            show_preprints=False,
        )
        
        assert len(filtered) == 1
        assert filtered[0].journal == "Nature"

    def test_filter_papers_with_preprints(self, filter, sample_papers):
        """Test filtering papers with preprints included."""
        filtered = filter.filter_papers(
            sample_papers,
            tiers=["tier1"],
            show_preprints=True,
        )
        
        journals = [p.journal for p in filtered]
        assert "Nature" in journals
        assert "bioRxiv" in journals
        assert "Unknown Journal" not in journals

    def test_filter_papers_by_include_list(self, filter, sample_papers):
        """Test filtering papers by include list."""
        filtered = filter.filter_papers(
            sample_papers,
            include_journals=["Unknown Journal"],
            show_preprints=False,
        )
        
        assert len(filtered) == 1
        assert filtered[0].journal == "Unknown Journal"

    def test_filter_papers_by_exclude_list(self, filter, sample_papers):
        """Test filtering papers by exclude list."""
        filtered = filter.filter_papers(
            sample_papers,
            exclude_journals=["Nature"],
            tiers=["tier1", "tier2", "ml"],
            show_preprints=True,
        )
        
        journals = [p.journal for p in filtered]
        assert "Nature" not in journals
        assert "bioRxiv" in journals

    def test_filter_papers_empty_list(self, filter):
        """Test filtering empty paper list."""
        filtered = filter.filter_papers([])
        assert filtered == []

    def test_categorize_papers(self, filter, sample_papers):
        """Test categorizing papers by tier."""
        categorized = filter.categorize_papers(sample_papers)
        
        assert len(categorized["tier1"]) == 1
        assert categorized["tier1"][0].journal == "Nature"
        
        assert len(categorized["ml"]) == 1
        assert categorized["ml"][0].journal == "NeurIPS"
        
        assert len(categorized["preprints"]) == 1
        assert categorized["preprints"][0].journal == "bioRxiv"
        
        assert len(categorized["other"]) == 1
        assert categorized["other"][0].journal == "Unknown Journal"

    def test_get_tier_journals(self, filter):
        """Test getting journals for a tier."""
        tier1_journals = filter.get_tier_journals("tier1")
        
        assert "Nature" in tier1_journals
        assert "Science" in tier1_journals
        assert "Cell" in tier1_journals

    def test_get_all_tiers(self, filter):
        """Test getting all tier names."""
        tiers = filter.get_all_tiers()
        
        assert "tier1" in tiers
        assert "tier2" in tiers
        assert "ml" in tiers
        assert "preprints" in tiers

    def test_custom_config(self, custom_filter, sample_papers):
        """Test filter with custom configuration."""
        filtered = custom_filter.filter_papers(sample_papers)
        
        # Should include tier1, Custom Journal, and preprints
        journals = [p.journal for p in filtered]
        assert "Nature" in journals
        assert "bioRxiv" in journals

    def test_partial_journal_match(self, filter):
        """Test partial journal name matching."""
        assert filter.get_journal_tier("Nature Methods") == "tier2"
        assert filter.get_journal_tier("Nature Communications") == "tier2"
        # Should match if journal name contains tier journal name
        assert filter.get_journal_tier("The Lancet Oncology") is not None or \
               filter.get_journal_tier("Lancet") == "tier1"
