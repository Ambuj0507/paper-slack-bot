"""Slack bot with slash commands and event handling."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from paper_slack_bot.config import Config
from paper_slack_bot.filtering.llm_filter import LLMFilter
from paper_slack_bot.search.journal_filter import JournalFilter
from paper_slack_bot.search.paper_fetcher import PaperFetcher
from paper_slack_bot.search.search_engine import SearchEngine
from paper_slack_bot.slack.formatter import SlackFormatter
from paper_slack_bot.storage.database import Database, UserPreference

logger = logging.getLogger(__name__)


class PaperSlackBot:
    """Slack bot for paper discovery."""

    def __init__(self, config: Config):
        """Initialize the Slack bot.

        Args:
            config: Bot configuration.
        """
        self.config = config
        self.app = App(token=config.slack.bot_token)
        self.database = Database(config.storage.database_path)
        self.paper_fetcher = PaperFetcher(ncbi_api_key=config.ncbi_api_key)
        self.search_engine = SearchEngine(self.database)
        self.journal_filter = JournalFilter(config.journals)
        self.formatter = SlackFormatter(self.journal_filter)
        self.scheduler: Optional[BackgroundScheduler] = None

        # Initialize LLM filter if API key provided
        self.llm_filter: Optional[LLMFilter] = None
        if config.openai_api_key:
            self.llm_filter = LLMFilter(
                api_key=config.openai_api_key,
                config=config.llm,
            )

        # Register handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register Slack event handlers."""
        # Slash commands
        self.app.command("/papersearch")(self._handle_papersearch)
        self.app.command("/papersubscribe")(self._handle_papersubscribe)
        self.app.command("/paperjournals")(self._handle_paperjournals)
        self.app.command("/papersettings")(self._handle_papersettings)

        # Action handlers
        self.app.action("save_paper")(self._handle_save_paper)
        self.app.action("share_paper")(self._handle_share_paper)
        self.app.action("dismiss_paper")(self._handle_dismiss_paper)
        self.app.action("view_all_results")(self._handle_view_all)

        # Message events
        self.app.event("message")(self._handle_message)

    def _handle_papersearch(self, ack, command, client):
        """Handle /papersearch command.

        Args:
            ack: Acknowledge function.
            command: Command payload.
            client: Slack client.
        """
        ack()

        query = command.get("text", "").strip()
        user_id = command.get("user_id")
        channel_id = command.get("channel_id")

        if not query:
            error_msg = "Please provide a search query. Usage: /papersearch <query>"
            client.chat_postMessage(
                channel=channel_id,
                text=f"Error: {error_msg}",
                blocks=self.formatter.format_error(error_msg),
            )
            return

        try:
            # Run async search in sync context
            papers = asyncio.run(
                self.paper_fetcher.search(
                    query=query,
                    databases=self.config.search.databases,
                    max_results_per_source=20,
                )
            )

            # Apply journal filter
            papers, _ = self.journal_filter.filter_papers(papers)

            # Apply LLM filter if available
            if self.llm_filter and papers:
                papers = self.llm_filter.filter_papers(
                    papers,
                    min_score=30,
                    research_interests=self.config.llm.filtering_prompt,
                )

            # Apply search engine for ranking
            papers = self.search_engine.search(
                query=query,
                papers=papers,
                user_id=user_id,
            )

            # Format and send results
            blocks = self.formatter.format_search_results(
                papers=papers,
                query=query,
                user_id=user_id,
            )

            # Split blocks to respect Slack's 50-block limit
            block_batches = SlackFormatter.split_blocks(blocks)

            for i, batch in enumerate(block_batches):
                if i > 0:
                    # Add continuation header for subsequent messages
                    header = SlackFormatter.create_continuation_header(
                        "🔍 *Search Results*", i + 1
                    )
                    batch.insert(0, header)
                client.chat_postMessage(
                    channel=channel_id,
                    text=f"Search results for: {query} ({len(papers)} papers found)",
                    blocks=batch,
                )

        except Exception as e:
            logger.error(f"Error in papersearch: {e}")
            error_msg = f"Search failed: {str(e)}"
            client.chat_postMessage(
                channel=channel_id,
                text=f"Error: {error_msg}",
                blocks=self.formatter.format_error(error_msg),
            )

    def _handle_papersubscribe(self, ack, command, client):
        """Handle /papersubscribe command.

        Args:
            ack: Acknowledge function.
            command: Command payload.
            client: Slack client.
        """
        ack()

        keywords = command.get("text", "").strip()
        user_id = command.get("user_id")
        channel_id = command.get("channel_id")

        if not keywords:
            # Show current subscriptions
            pref = self.database.get_user_preference(user_id)
            if pref and pref.subscribed_keywords:
                message = "Your current subscriptions:\n• " + "\n• ".join(
                    pref.subscribed_keywords
                )
            else:
                message = "You have no active subscriptions.\nUsage: /papersubscribe <keywords>"

            client.chat_postMessage(
                channel=channel_id,
                text=message,
                blocks=self.formatter.format_success(message),
            )
            return

        try:
            # Get or create user preferences
            pref = self.database.get_user_preference(user_id)
            if pref:
                current_keywords = pref.subscribed_keywords
            else:
                current_keywords = []

            # Parse keywords (comma-separated)
            new_keywords = [k.strip() for k in keywords.split(",") if k.strip()]
            all_keywords = list(set(current_keywords + new_keywords))

            # Save preferences
            self.database.save_user_preference(
                UserPreference(
                    user_id=user_id,
                    subscribed_keywords=all_keywords,
                    preferred_journals=pref.preferred_journals if pref else [],
                )
            )

            new_keywords_str = ", ".join(new_keywords)
            all_keywords_str = ", ".join(all_keywords)
            message = f"Subscribed to: {new_keywords_str}\nAll subscriptions: {all_keywords_str}"
            client.chat_postMessage(
                channel=channel_id,
                text=message,
                blocks=self.formatter.format_success(message),
            )

        except Exception as e:
            logger.error(f"Error in papersubscribe: {e}")
            error_msg = f"Subscription failed: {str(e)}"
            client.chat_postMessage(
                channel=channel_id,
                text=f"Error: {error_msg}",
                blocks=self.formatter.format_error(error_msg),
            )

    def _handle_paperjournals(self, ack, command, client):
        """Handle /paperjournals command.

        Args:
            ack: Acknowledge function.
            command: Command payload.
            client: Slack client.
        """
        ack()

        channel_id = command.get("channel_id")

        try:
            # Show current journal configuration
            excluded = self.config.journals.exclude or []
            if excluded:
                message = f"*Journal Configuration*\n\nAll journals are included by default.\n\n*Excluded journals:*\n• " + "\n• ".join(excluded)
            else:
                message = "*Journal Configuration*\n\nAll journals are included (no exclusions configured).\n\nPapers are grouped into:\n• 📰 Journal Articles\n• 📝 Preprints (bioRxiv, arXiv, medRxiv)"

            blocks = [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": message},
                }
            ]

            client.chat_postMessage(
                channel=channel_id,
                text="Journal configuration",
                blocks=blocks,
            )

        except Exception as e:
            logger.error(f"Error in paperjournals: {e}")
            error_msg = f"Failed to list journals: {str(e)}"
            client.chat_postMessage(
                channel=channel_id,
                text=f"Error: {error_msg}",
                blocks=self.formatter.format_error(error_msg),
            )

    def _handle_papersettings(self, ack, command, client):
        """Handle /papersettings command.

        Args:
            ack: Acknowledge function.
            command: Command payload.
            client: Slack client.
        """
        ack()

        channel_id = command.get("channel_id")
        user_id = command.get("user_id")

        try:
            # Get user preferences
            pref = self.database.get_user_preference(user_id)

            settings = {
                "Search Keywords": ", ".join(self.config.search.keywords) or "None",
                "Databases": ", ".join(self.config.search.databases),
                "Days Back": self.config.search.days_back,
                "LLM Provider": self.config.llm.provider,
                "LLM Model": self.config.llm.model,
                "Scheduled Posting": "Enabled" if self.config.schedule.enabled else "Disabled",
                "Post Time": f"{self.config.schedule.time} {self.config.schedule.timezone}",
            }

            if pref:
                settings["Your Subscriptions"] = (
                    ", ".join(pref.subscribed_keywords) or "None"
                )
                settings["Your Preferred Journals"] = (
                    ", ".join(pref.preferred_journals) or "None"
                )

            blocks = self.formatter.format_settings(settings)
            client.chat_postMessage(
                channel=channel_id,
                text="Bot Settings",
                blocks=blocks,
            )

        except Exception as e:
            logger.error(f"Error in papersettings: {e}")
            error_msg = f"Failed to get settings: {str(e)}"
            client.chat_postMessage(
                channel=channel_id,
                text=f"Error: {error_msg}",
                blocks=self.formatter.format_error(error_msg),
            )

    def _handle_save_paper(self, ack, body, client):
        """Handle save paper action.

        Args:
            ack: Acknowledge function.
            body: Action payload.
            client: Slack client.
        """
        ack()
        # In a real implementation, save to user's saved papers
        logger.info(f"Paper saved: {body.get('actions', [{}])[0].get('value')}")

    def _handle_share_paper(self, ack, body, client):
        """Handle share paper action.

        Args:
            ack: Acknowledge function.
            body: Action payload.
            client: Slack client.
        """
        ack()
        # In a real implementation, open share dialog
        logger.info(f"Paper shared: {body.get('actions', [{}])[0].get('value')}")

    def _handle_dismiss_paper(self, ack, body, client):
        """Handle dismiss paper action.

        Args:
            ack: Acknowledge function.
            body: Action payload.
            client: Slack client.
        """
        ack()
        # In a real implementation, remove paper from view
        logger.info(f"Paper dismissed: {body.get('actions', [{}])[0].get('value')}")

    def _handle_view_all(self, ack, body, client):
        """Handle view all results action.

        Args:
            ack: Acknowledge function.
            body: Action payload.
            client: Slack client.
        """
        ack()
        # In a real implementation, paginate results
        logger.info(f"View all: {body.get('actions', [{}])[0].get('value')}")

    def _handle_message(self, event, say):
        """Handle message events.

        Args:
            event: Message event.
            say: Say function.
        """
        # Bot mention handling could be added here
        pass

    def post_papers(self, channel_id: Optional[str] = None) -> None:
        """Post papers to Slack channel.

        Args:
            channel_id: Optional channel ID (uses config if not provided).
        """
        channel = channel_id or self.config.slack.channel_id

        try:
            # Fetch papers
            papers = asyncio.run(
                self.paper_fetcher.fetch_all(
                    keywords=self.config.search.keywords,
                    databases=self.config.search.databases,
                    days_back=self.config.search.days_back,
                    max_results_per_source=50,
                )
            )

            # Apply journal filter
            papers, _ = self.journal_filter.filter_papers(papers)

            # Apply LLM filter if available
            if self.llm_filter and papers:
                papers = self.llm_filter.filter_papers(
                    papers,
                    min_score=50,
                    research_interests=self.config.llm.filtering_prompt,
                )

            # Filter out already reported papers (papers that already exist in database)
            paper_dois = [p.doi for p in papers if p.doi]
            existing_dois = self.database.get_existing_dois(paper_dois)
            new_papers = [p for p in papers if not (p.doi and p.doi in existing_dois)]
            logger.info(
                f"Filtered {len(papers) - len(new_papers)} already reported papers, "
                f"{len(new_papers)} new papers remaining"
            )
            papers = new_papers

            # Save papers to database
            self.database.save_papers(papers)

            # Format and post digest
            date_str = datetime.now().strftime("%Y-%m-%d")
            blocks = self.formatter.format_digest(papers, date_str)

            # Split blocks to respect Slack's 50-block limit
            block_batches = SlackFormatter.split_blocks(blocks)

            for i, batch in enumerate(block_batches):
                if i > 0:
                    # Add continuation header for subsequent messages
                    header = SlackFormatter.create_continuation_header(
                        "📚 *Paper Digest*", i + 1
                    )
                    batch.insert(0, header)
                self.app.client.chat_postMessage(
                    channel=channel,
                    text=f"Paper Digest - {date_str}: {len(papers)} papers",
                    blocks=batch,
                )

            logger.info(
                f"Posted {len(papers)} papers to {channel} "
                f"in {len(block_batches)} message(s)"
            )

        except Exception as e:
            logger.error(f"Error posting papers: {e}")
            error_msg = f"Failed to fetch papers: {str(e)}"
            self.app.client.chat_postMessage(
                channel=channel,
                text=f"Error: {error_msg}",
                blocks=self.formatter.format_error(error_msg),
            )

    def start_scheduler(self) -> None:
        """Start the scheduled posting."""
        if not self.config.schedule.enabled:
            return

        self.scheduler = BackgroundScheduler(timezone=self.config.schedule.timezone)

        # Parse time
        hour, minute = map(int, self.config.schedule.time.split(":"))

        self.scheduler.add_job(
            self.post_papers,
            CronTrigger(hour=hour, minute=minute),
            id="daily_post",
        )

        self.scheduler.start()
        logger.info(
            f"Scheduler started. Papers will be posted at {self.config.schedule.time} "
            f"{self.config.schedule.timezone}"
        )

    def stop_scheduler(self) -> None:
        """Stop the scheduled posting."""
        if self.scheduler:
            self.scheduler.shutdown()
            self.scheduler = None

    def run(self) -> None:
        """Run the Slack bot."""
        logger.info("Starting Paper Slack Bot...")

        # Start scheduler
        self.start_scheduler()

        # Start socket mode handler
        handler = SocketModeHandler(self.app, self.config.slack.app_token)
        handler.start()


def create_bot(config_path: str) -> PaperSlackBot:
    """Create a bot instance from config file.

    Args:
        config_path: Path to configuration file.

    Returns:
        PaperSlackBot instance.
    """
    config = Config.from_yaml(config_path)
    return PaperSlackBot(config)
