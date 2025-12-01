"""Tests for Slack bot module."""

import pytest
from unittest.mock import MagicMock, patch

from paper_slack_bot.config import (
    Config,
    JournalConfig,
    LLMConfig,
    ScheduleConfig,
    SearchConfig,
    SlackConfig,
    StorageConfig,
)
from paper_slack_bot.storage.database import Paper


class TestBotChatPostMessage:
    """Tests to verify chat_postMessage calls include text parameter."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        config = Config(
            slack=SlackConfig(
                bot_token="xoxb-test-token",
                app_token="xapp-test-token",
                channel_id="C1234567890",
            ),
            search=SearchConfig(
                keywords=["test"],
                databases=["pubmed"],
                days_back=7,
            ),
            journals=JournalConfig(
                include=[],
                exclude=[],
                tiers=[],
                show_preprints=True,
            ),
            llm=LLMConfig(
                provider="openai",
                model="gpt-4o-mini",
                filtering_prompt="",
            ),
            schedule=ScheduleConfig(
                enabled=False,
                time="09:00",
                timezone="UTC",
            ),
            storage=StorageConfig(
                database_path=":memory:",
            ),
            openai_api_key="",
            ncbi_api_key="",
        )
        return config

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

    @patch("paper_slack_bot.slack.bot.App")
    @patch("paper_slack_bot.slack.bot.Database")
    @patch("paper_slack_bot.slack.bot.PaperFetcher")
    def test_papersearch_error_includes_text(self, mock_fetcher, mock_db, mock_app, mock_config):
        """Test that /papersearch error response includes text parameter."""
        from paper_slack_bot.slack.bot import PaperSlackBot

        # Create bot
        bot = PaperSlackBot(mock_config)

        # Mock the client
        mock_client = MagicMock()

        # Simulate empty query
        command = {"text": "", "user_id": "U123", "channel_id": "C123"}

        # Call handler
        bot._handle_papersearch(MagicMock(), command, mock_client)

        # Verify chat_postMessage was called with text parameter
        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        assert "text" in call_kwargs, "chat_postMessage must include 'text' parameter"
        assert "Error" in call_kwargs["text"]
        assert "blocks" in call_kwargs

    @patch("paper_slack_bot.slack.bot.App")
    @patch("paper_slack_bot.slack.bot.Database")
    @patch("paper_slack_bot.slack.bot.PaperFetcher")
    def test_papersubscribe_message_includes_text(
        self, mock_fetcher, mock_db, mock_app, mock_config
    ):
        """Test that /papersubscribe response includes text parameter."""
        from paper_slack_bot.slack.bot import PaperSlackBot

        # Create bot
        bot = PaperSlackBot(mock_config)

        # Mock database to return no preferences
        bot.database.get_user_preference = MagicMock(return_value=None)

        # Mock the client
        mock_client = MagicMock()

        # Simulate empty keywords (show current subscriptions)
        command = {"text": "", "user_id": "U123", "channel_id": "C123"}

        # Call handler
        bot._handle_papersubscribe(MagicMock(), command, mock_client)

        # Verify chat_postMessage was called with text parameter
        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        assert "text" in call_kwargs, "chat_postMessage must include 'text' parameter"
        assert "blocks" in call_kwargs

    @patch("paper_slack_bot.slack.bot.App")
    @patch("paper_slack_bot.slack.bot.Database")
    @patch("paper_slack_bot.slack.bot.PaperFetcher")
    def test_papersettings_includes_text(self, mock_fetcher, mock_db, mock_app, mock_config):
        """Test that /papersettings response includes text parameter."""
        from paper_slack_bot.slack.bot import PaperSlackBot

        # Create bot
        bot = PaperSlackBot(mock_config)

        # Mock database to return no preferences
        bot.database.get_user_preference = MagicMock(return_value=None)

        # Mock the client
        mock_client = MagicMock()

        # Simulate settings command
        command = {"text": "", "user_id": "U123", "channel_id": "C123"}

        # Call handler
        bot._handle_papersettings(MagicMock(), command, mock_client)

        # Verify chat_postMessage was called with text parameter
        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        assert "text" in call_kwargs, "chat_postMessage must include 'text' parameter"
        assert call_kwargs["text"] == "Bot Settings"
        assert "blocks" in call_kwargs

    @patch("paper_slack_bot.slack.bot.App")
    @patch("paper_slack_bot.slack.bot.Database")
    @patch("paper_slack_bot.slack.bot.PaperFetcher")
    def test_paperjournals_includes_text(self, mock_fetcher, mock_db, mock_app, mock_config):
        """Test that /paperjournals response includes text parameter."""
        from paper_slack_bot.slack.bot import PaperSlackBot

        # Create bot
        bot = PaperSlackBot(mock_config)

        # Mock the client
        mock_client = MagicMock()

        # Simulate list command
        command = {"text": "list", "user_id": "U123", "channel_id": "C123"}

        # Call handler
        bot._handle_paperjournals(MagicMock(), command, mock_client)

        # Verify chat_postMessage was called with text parameter
        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        assert "text" in call_kwargs, "chat_postMessage must include 'text' parameter"
        assert "journals" in call_kwargs["text"].lower()
        assert "blocks" in call_kwargs
