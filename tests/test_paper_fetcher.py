"""Tests for paper fetcher module."""

import pytest
from unittest.mock import patch, MagicMock

from paper_slack_bot.search.paper_fetcher import (
    PaperFetcher,
    PubMedFetcher,
    BioRxivFetcher,
    ArxivFetcher,
)
from paper_slack_bot.storage.database import Paper


class TestPubMedFetcher:
    """Tests for PubMed fetcher."""

    @pytest.fixture
    def fetcher(self):
        """Create a PubMed fetcher."""
        return PubMedFetcher(api_key="test_api_key")

    def test_parse_pubmed_xml(self, fetcher):
        """Test parsing PubMed XML response."""
        xml_content = """<?xml version="1.0"?>
        <PubmedArticleSet>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>12345</PMID>
                    <Article>
                        <ArticleTitle>Test Paper Title</ArticleTitle>
                        <AuthorList>
                            <Author>
                                <LastName>Smith</LastName>
                                <ForeName>John</ForeName>
                            </Author>
                        </AuthorList>
                        <Abstract>
                            <AbstractText>This is a test abstract.</AbstractText>
                        </Abstract>
                        <Journal>
                            <Title>Nature</Title>
                            <JournalIssue>
                                <PubDate>
                                    <Year>2024</Year>
                                    <Month>01</Month>
                                </PubDate>
                            </JournalIssue>
                        </Journal>
                    </Article>
                </MedlineCitation>
                <PubmedData>
                    <ArticleIdList>
                        <ArticleId IdType="doi">10.1234/test</ArticleId>
                    </ArticleIdList>
                </PubmedData>
            </PubmedArticle>
        </PubmedArticleSet>
        """
        
        papers = fetcher._parse_pubmed_xml(xml_content)
        
        assert len(papers) == 1
        paper = papers[0]
        assert paper.title == "Test Paper Title"
        assert "John Smith" in paper.authors
        assert paper.abstract == "This is a test abstract."
        assert paper.journal == "Nature"
        assert paper.doi == "10.1234/test"
        assert paper.source == "pubmed"


class TestBioRxivFetcher:
    """Tests for bioRxiv fetcher."""

    @pytest.fixture
    def fetcher(self):
        """Create a bioRxiv fetcher."""
        return BioRxivFetcher()

    def test_parse_paper(self, fetcher):
        """Test parsing bioRxiv paper data."""
        item = {
            "title": "Test Preprint",
            "authors": "Smith, John; Doe, Jane",
            "abstract": "Test abstract",
            "doi": "10.1101/2024.01.01.12345",
            "date": "2024-01-15",
        }
        
        paper = fetcher._parse_paper(item)
        
        assert paper is not None
        assert paper.title == "Test Preprint"
        assert "Smith, John" in paper.authors
        assert paper.journal == "bioRxiv"
        assert paper.source == "biorxiv"

    def test_matches_keywords(self, fetcher):
        """Test keyword matching."""
        paper = Paper(
            title="Machine Learning for Genomics",
            authors=["John Smith"],
            abstract="Deep learning applied to single-cell RNA-seq",
            doi="10.1234/test",
            journal="bioRxiv",
            publication_date="2024-01-15",
            url="https://example.com",
            source="biorxiv",
        )
        
        assert fetcher._matches_keywords(paper, ["machine learning"])
        assert fetcher._matches_keywords(paper, ["genomics", "proteomics"])
        assert not fetcher._matches_keywords(paper, ["clinical trial"])


class TestArxivFetcher:
    """Tests for arXiv fetcher."""

    @pytest.fixture
    def fetcher(self):
        """Create an arXiv fetcher."""
        return ArxivFetcher()

    def test_parse_arxiv_xml(self, fetcher):
        """Test parsing arXiv API response."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom" 
              xmlns:arxiv="http://arxiv.org/schemas/atom">
            <entry>
                <title>Deep Learning for Biology</title>
                <author><name>John Smith</name></author>
                <author><name>Jane Doe</name></author>
                <summary>A new deep learning method for biological data.</summary>
                <link href="http://arxiv.org/abs/2401.12345" type="text/html"/>
                <published>2024-01-15T00:00:00Z</published>
                <arxiv:primary_category term="cs.LG"/>
            </entry>
        </feed>
        """
        
        papers = fetcher._parse_arxiv_xml(xml_content)
        
        assert len(papers) == 1
        paper = papers[0]
        assert paper.title == "Deep Learning for Biology"
        assert "John Smith" in paper.authors
        assert paper.source == "arxiv"
        assert "cs.LG" in paper.journal


class TestPaperFetcher:
    """Tests for unified paper fetcher."""

    @pytest.fixture
    def fetcher(self):
        """Create a paper fetcher."""
        return PaperFetcher(ncbi_api_key="test_key")

    def test_fetcher_initialization(self, fetcher):
        """Test fetcher initialization."""
        assert "pubmed" in fetcher.fetchers
        assert "biorxiv" in fetcher.fetchers
        assert "arxiv" in fetcher.fetchers

    @pytest.mark.asyncio
    async def test_fetch_all_handles_errors(self, fetcher):
        """Test that fetch_all handles errors gracefully."""
        with patch.object(
            fetcher.fetchers["pubmed"],
            "fetch_papers",
            side_effect=Exception("API Error"),
        ):
            with patch.object(
                fetcher.fetchers["biorxiv"],
                "fetch_papers",
                return_value=[],
            ):
                with patch.object(
                    fetcher.fetchers["arxiv"],
                    "fetch_papers",
                    return_value=[],
                ):
                    papers = await fetcher.fetch_all(
                        keywords=["test"],
                        databases=["pubmed", "biorxiv", "arxiv"],
                        days_back=1,
                    )
                    # Should not raise, just return empty list
                    assert papers == []
