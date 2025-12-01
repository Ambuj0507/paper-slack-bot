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
