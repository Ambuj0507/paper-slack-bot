"""Tests for LLM filter module."""

from unittest.mock import MagicMock, patch

import pytest

from paper_slack_bot.config import LLMConfig
from paper_slack_bot.filtering.llm_filter import LLMFilter, OllamaFilter, RelevanceResult
from paper_slack_bot.storage.database import Paper


class TestLLMFilter:
    """Tests for LLM filter."""

    @pytest.fixture
    def sample_paper(self):
        """Create a sample paper."""
        return Paper(
            title="Deep Learning for Genomics",
            authors=["John Smith", "Jane Doe"],
            abstract="A novel deep learning approach for genomic analysis.",
            doi="10.1234/test",
            journal="Nature",
            publication_date="2024-01-15",
            url="https://example.com",
            source="pubmed",
        )

    @pytest.fixture
    def sample_papers(self):
        """Create sample papers for batch testing."""
        return [
            Paper(
                title="Machine Learning Methods",
                authors=["Author 1"],
                abstract="Novel ML methods for biology.",
                doi="10.1234/1",
                journal="Nature",
                publication_date="2024-01-01",
                url="https://example.com/1",
                source="pubmed",
            ),
            Paper(
                title="Clinical Trial Results",
                authors=["Author 2"],
                abstract="Results from clinical trial.",
                doi="10.1234/2",
                journal="Lancet",
                publication_date="2024-01-02",
                url="https://example.com/2",
                source="pubmed",
            ),
        ]

    def test_parse_json_response(self):
        """Test parsing JSON response."""
        filter = LLMFilter.__new__(LLMFilter)

        response = '{"score": 85, "explanation": "Highly relevant paper"}'
        score, explanation = filter._parse_response(response)

        assert score == 85
        assert explanation == "Highly relevant paper"

    def test_parse_json_with_extra_text(self):
        """Test parsing JSON with surrounding text."""
        filter = LLMFilter.__new__(LLMFilter)

        response = 'Here is my evaluation: {"score": 75, "explanation": "Good paper"}'
        score, explanation = filter._parse_response(response)

        assert score == 75
        assert explanation == "Good paper"

    def test_parse_fallback_score(self):
        """Test fallback score extraction."""
        filter = LLMFilter.__new__(LLMFilter)

        response = "I rate this paper 80/100 because it's relevant."
        score, explanation = filter._parse_response(response)

        assert score == 80

    def test_parse_invalid_response(self):
        """Test parsing invalid response."""
        filter = LLMFilter.__new__(LLMFilter)

        response = "This is an invalid response without a score."
        score, explanation = filter._parse_response(response)

        assert score == 50.0  # Default score

    def test_parse_batch_response(self):
        """Test parsing batch response."""
        filter = LLMFilter.__new__(LLMFilter)
        papers = [
            Paper(
                title="Paper 1",
                authors=[],
                abstract="",
                doi="1",
                journal="",
                publication_date="",
                url="",
                source="",
            ),
            Paper(
                title="Paper 2",
                authors=[],
                abstract="",
                doi="2",
                journal="",
                publication_date="",
                url="",
                source="",
            ),
        ]

        response = """[
            {"paper": 1, "score": 85, "explanation": "Relevant"},
            {"paper": 2, "score": 45, "explanation": "Less relevant"}
        ]"""

        results = filter._parse_batch_response(response, papers)

        assert len(results) == 2
        assert results[0].score == 85
        assert results[1].score == 45

    def test_parse_batch_response_with_markdown_code_block(self):
        """Test parsing batch response with markdown code block."""
        filter = LLMFilter.__new__(LLMFilter)
        papers = [
            Paper(
                title="Paper 1",
                authors=[],
                abstract="",
                doi="1",
                journal="",
                publication_date="",
                url="",
                source="",
            ),
            Paper(
                title="Paper 2",
                authors=[],
                abstract="",
                doi="2",
                journal="",
                publication_date="",
                url="",
                source="",
            ),
        ]

        response = """Here is my evaluation:
```json
[
    {"paper": 1, "score": 90, "explanation": "Highly relevant"},
    {"paper": 2, "score": 30, "explanation": "Not relevant"}
]
```
"""

        results = filter._parse_batch_response(response, papers)

        assert len(results) == 2
        assert results[0].score == 90
        assert results[1].score == 30

    def test_parse_batch_response_with_individual_json_objects(self):
        """Test parsing batch response with individual JSON objects."""
        filter = LLMFilter.__new__(LLMFilter)
        papers = [
            Paper(
                title="Paper 1",
                authors=[],
                abstract="",
                doi="1",
                journal="",
                publication_date="",
                url="",
                source="",
            ),
            Paper(
                title="Paper 2",
                authors=[],
                abstract="",
                doi="2",
                journal="",
                publication_date="",
                url="",
                source="",
            ),
        ]

        response = """Paper 1: {"score": 75, "explanation": "Good paper"}
Paper 2: {"score": 60, "explanation": "Decent paper"}"""

        results = filter._parse_batch_response(response, papers)

        assert len(results) == 2
        assert results[0].score == 75
        assert results[1].score == 60

    def test_parse_batch_response_with_text_scores(self):
        """Test parsing batch response with text-based scores."""
        filter = LLMFilter.__new__(LLMFilter)
        papers = [
            Paper(
                title="Paper 1",
                authors=[],
                abstract="",
                doi="1",
                journal="",
                publication_date="",
                url="",
                source="",
            ),
            Paper(
                title="Paper 2",
                authors=[],
                abstract="",
                doi="2",
                journal="",
                publication_date="",
                url="",
                source="",
            ),
        ]

        response = """Paper 1: 85/100 - This is a highly relevant paper
Paper 2: 40/100 - This paper is not very relevant"""

        results = filter._parse_batch_response(response, papers)

        assert len(results) == 2
        assert results[0].score == 85
        assert results[1].score == 40

    def test_parse_batch_response_invalid_returns_defaults(self):
        """Test parsing completely invalid response returns defaults."""
        filter = LLMFilter.__new__(LLMFilter)
        papers = [
            Paper(
                title="Paper 1",
                authors=[],
                abstract="",
                doi="1",
                journal="",
                publication_date="",
                url="",
                source="",
            ),
        ]

        response = "This is an invalid response with no scores whatsoever."

        results = filter._parse_batch_response(response, papers)

        assert len(results) == 1
        assert results[0].score == 50.0
        assert "Unable to parse" in results[0].explanation

    def test_build_prompt(self, sample_paper):
        """Test building prompt for single paper."""
        filter = LLMFilter.__new__(LLMFilter)
        filter.config = LLMConfig()

        prompt = filter._build_prompt(sample_paper)

        assert "Deep Learning for Genomics" in prompt
        assert "John Smith" in prompt
        assert "Nature" in prompt
        assert "genomic analysis" in prompt

    def test_build_prompt_with_interests(self, sample_paper):
        """Test building prompt with research interests."""
        filter = LLMFilter.__new__(LLMFilter)
        filter.config = LLMConfig()

        prompt = filter._build_prompt(
            sample_paper,
            research_interests="I focus on single-cell analysis.",
        )

        assert "single-cell analysis" in prompt

    def test_build_batch_prompt(self, sample_papers):
        """Test building batch prompt."""
        filter = LLMFilter.__new__(LLMFilter)
        filter.config = LLMConfig()

        prompt = filter._build_batch_prompt(sample_papers)

        assert "Paper 1:" in prompt
        assert "Paper 2:" in prompt
        assert "Machine Learning Methods" in prompt
        assert "Clinical Trial Results" in prompt

    @patch("paper_slack_bot.filtering.llm_filter.LLMFilter.client")
    def test_score_paper(self, mock_client, sample_paper):
        """Test scoring a single paper."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"score": 90, "explanation": "Very relevant"}'))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        filter = LLMFilter.__new__(LLMFilter)
        filter.config = LLMConfig()
        filter._client = mock_client

        result = filter.score_paper(sample_paper)

        assert isinstance(result, RelevanceResult)
        assert result.score == 90
        assert result.explanation == "Very relevant"
        assert result.paper == sample_paper

    @patch("paper_slack_bot.filtering.llm_filter.LLMFilter.client")
    def test_score_paper_error(self, mock_client, sample_paper):
        """Test scoring paper with API error."""
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        filter = LLMFilter.__new__(LLMFilter)
        filter.config = LLMConfig()
        filter._client = mock_client

        result = filter.score_paper(sample_paper)

        assert result.score == 50.0
        assert "Error" in result.explanation

    @patch("paper_slack_bot.filtering.llm_filter.LLMFilter._score_batch")
    def test_filter_papers(self, mock_score_batch, sample_papers):
        """Test filtering papers by score."""
        mock_score_batch.return_value = [
            RelevanceResult(score=80, explanation="Good", paper=sample_papers[0]),
            RelevanceResult(score=40, explanation="Not relevant", paper=sample_papers[1]),
        ]

        filter = LLMFilter.__new__(LLMFilter)
        filter.config = LLMConfig()

        filtered = filter.filter_papers(sample_papers, min_score=50)

        assert len(filtered) == 1
        assert filtered[0].title == "Machine Learning Methods"
        assert filtered[0].relevance_score == 80


class TestOllamaFilter:
    """Tests for Ollama filter."""

    def test_ollama_initialization(self):
        """Test Ollama filter initialization."""
        filter = OllamaFilter(
            model="llama2",
            base_url="http://localhost:11434/v1",
        )

        assert filter.config.model == "llama2"
        assert filter.config.base_url == "http://localhost:11434/v1"
        assert filter.api_key == "ollama"

    def test_ollama_custom_model(self):
        """Test Ollama filter with custom model."""
        filter = OllamaFilter(model="mistral")

        assert filter.config.model == "mistral"
