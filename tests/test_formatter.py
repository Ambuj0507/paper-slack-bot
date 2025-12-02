"""Tests for Slack formatter module."""

import pytest

from paper_slack_bot.slack.formatter import SlackFormatter, MAX_BLOCKS_PER_MESSAGE
from paper_slack_bot.storage.database import Paper


class TestSlackFormatter:
    """Tests for SlackFormatter."""

    @pytest.fixture
    def formatter(self):
        """Create a SlackFormatter instance."""
        return SlackFormatter()

    @pytest.fixture
    def sample_paper(self):
        """Create a sample paper."""
        return Paper(
            title="Test Paper",
            authors=["Author 1", "Author 2"],
            abstract="Test abstract for the paper.",
            doi="10.1234/test",
            journal="Nature",
            publication_date="2024-01-01",
            url="https://example.com",
            source="pubmed",
            relevance_score=85,
            relevance_explanation="Highly relevant",
        )


class TestIsErrorExplanation:
    """Tests for the _is_error_explanation method."""

    def test_error_explanation_unable_to_parse(self):
        """Test that 'Unable to parse LLM response' is detected as error."""
        assert SlackFormatter._is_error_explanation("Unable to parse LLM response") is True

    def test_error_explanation_unable_to_score(self):
        """Test that 'Unable to score' variations are detected as error."""
        assert SlackFormatter._is_error_explanation("Unable to score - LLM response invalid") is True

    def test_error_explanation_error_during_scoring(self):
        """Test that 'Error during scoring' is detected as error."""
        assert SlackFormatter._is_error_explanation("Error during scoring: API timeout") is True

    def test_error_explanation_not_scored(self):
        """Test that 'Not scored' is detected as error."""
        assert SlackFormatter._is_error_explanation("Not scored") is True

    def test_error_explanation_error_prefix(self):
        """Test that 'Error:' prefix is detected as error."""
        assert SlackFormatter._is_error_explanation("Error: Something went wrong") is True

    def test_valid_explanation(self):
        """Test that valid explanations are not detected as errors."""
        assert SlackFormatter._is_error_explanation("Highly relevant research paper") is False

    def test_empty_explanation(self):
        """Test that empty explanations are not detected as errors."""
        assert SlackFormatter._is_error_explanation("") is False
        assert SlackFormatter._is_error_explanation(None) is False

    def test_case_insensitive(self):
        """Test that error detection is case insensitive."""
        assert SlackFormatter._is_error_explanation("UNABLE TO PARSE") is True
        assert SlackFormatter._is_error_explanation("error: something") is True


class TestFormatPaperWithErrorExplanation:
    """Tests for format_paper with error explanations."""

    @pytest.fixture
    def formatter(self):
        """Create a SlackFormatter instance."""
        return SlackFormatter()

    def test_format_paper_hides_relevance_on_error_explanation(self, formatter):
        """Test that relevance section is hidden when explanation is an error."""
        paper = Paper(
            title="Test Paper",
            authors=["Author 1"],
            abstract="Test abstract",
            doi="10.1234/test",
            journal="Nature",
            publication_date="2024-01-01",
            url="https://example.com",
            source="pubmed",
            relevance_score=50,
            relevance_explanation="Unable to parse LLM response",
        )

        blocks = formatter.format_paper(paper, show_relevance=True)

        # Check that no block contains the relevance text
        relevance_blocks = [b for b in blocks if "Relevance:" in str(b)]
        assert len(relevance_blocks) == 0

    def test_format_paper_shows_relevance_on_valid_explanation(self, formatter):
        """Test that relevance section is shown with valid explanation."""
        paper = Paper(
            title="Test Paper",
            authors=["Author 1"],
            abstract="Test abstract",
            doi="10.1234/test",
            journal="Nature",
            publication_date="2024-01-01",
            url="https://example.com",
            source="pubmed",
            relevance_score=85,
            relevance_explanation="Highly relevant paper about machine learning",
        )

        blocks = formatter.format_paper(paper, show_relevance=True)

        # Check that a block contains the relevance text
        relevance_blocks = [b for b in blocks if "Relevance:" in str(b)]
        assert len(relevance_blocks) == 1


class TestSplitBlocks:
    """Tests for the split_blocks method."""

    def test_split_blocks_under_limit(self):
        """Test that blocks under the limit are returned as a single list."""
        blocks = [{"type": "section", "text": {"type": "plain_text", "text": f"Block {i}"}}
                  for i in range(10)]

        result = SlackFormatter.split_blocks(blocks)

        assert len(result) == 1
        assert result[0] == blocks

    def test_split_blocks_exactly_at_limit(self):
        """Test that blocks exactly at the limit are returned as a single list."""
        blocks = [{"type": "section", "text": {"type": "plain_text", "text": f"Block {i}"}}
                  for i in range(MAX_BLOCKS_PER_MESSAGE)]

        result = SlackFormatter.split_blocks(blocks)

        assert len(result) == 1
        assert len(result[0]) == MAX_BLOCKS_PER_MESSAGE

    def test_split_blocks_over_limit(self):
        """Test that blocks over the limit are split into multiple lists."""
        blocks = [{"type": "section", "text": {"type": "plain_text", "text": f"Block {i}"}}
                  for i in range(75)]

        result = SlackFormatter.split_blocks(blocks)

        assert len(result) == 2
        assert len(result[0]) == MAX_BLOCKS_PER_MESSAGE
        assert len(result[1]) == 25

    def test_split_blocks_multiple_batches(self):
        """Test splitting blocks into multiple batches."""
        blocks = [{"type": "section", "text": {"type": "plain_text", "text": f"Block {i}"}}
                  for i in range(125)]

        result = SlackFormatter.split_blocks(blocks)

        assert len(result) == 3
        assert len(result[0]) == MAX_BLOCKS_PER_MESSAGE
        assert len(result[1]) == MAX_BLOCKS_PER_MESSAGE
        assert len(result[2]) == 25

    def test_split_blocks_empty_list(self):
        """Test that an empty list returns a single empty list."""
        blocks = []

        result = SlackFormatter.split_blocks(blocks)

        assert len(result) == 1
        assert result[0] == []

    def test_split_blocks_custom_max(self):
        """Test splitting with a custom max_blocks value."""
        blocks = [{"type": "section", "text": {"type": "plain_text", "text": f"Block {i}"}}
                  for i in range(15)]

        result = SlackFormatter.split_blocks(blocks, max_blocks=10)

        assert len(result) == 2
        assert len(result[0]) == 10
        assert len(result[1]) == 5

    def test_split_blocks_preserves_order(self):
        """Test that block order is preserved after splitting."""
        blocks = [{"type": "section", "text": {"type": "plain_text", "text": f"Block {i}"}}
                  for i in range(75)]

        result = SlackFormatter.split_blocks(blocks)

        # Flatten the result
        flattened = [block for batch in result for block in batch]

        assert flattened == blocks

    def test_max_blocks_constant_is_50(self):
        """Test that the MAX_BLOCKS_PER_MESSAGE constant is 50."""
        assert MAX_BLOCKS_PER_MESSAGE == 50


class TestContinuationHeader:
    """Tests for the create_continuation_header method."""

    def test_create_continuation_header(self):
        """Test creating a continuation header."""
        header = SlackFormatter.create_continuation_header("🔍 *Search Results*", 2)

        assert header["type"] == "section"
        assert header["text"]["type"] == "mrkdwn"
        assert "continued - part 2" in header["text"]["text"]
        assert "🔍 *Search Results*" in header["text"]["text"]

    def test_create_continuation_header_different_parts(self):
        """Test continuation headers for different part numbers."""
        header1 = SlackFormatter.create_continuation_header("📚 *Paper Digest*", 3)
        header2 = SlackFormatter.create_continuation_header("📚 *Paper Digest*", 5)

        assert "part 3" in header1["text"]["text"]
        assert "part 5" in header2["text"]["text"]
