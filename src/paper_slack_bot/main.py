"""Main entry point and CLI for Paper Slack Bot."""

import asyncio
import logging
import sys
from pathlib import Path

import click

from paper_slack_bot.config import Config
from paper_slack_bot.filtering.llm_filter import LLMFilter
from paper_slack_bot.search.journal_filter import JournalFilter
from paper_slack_bot.search.paper_fetcher import PaperFetcher
from paper_slack_bot.search.search_engine import SearchEngine
from paper_slack_bot.slack.bot import PaperSlackBot
from paper_slack_bot.slack.formatter import SlackFormatter
from paper_slack_bot.storage.database import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version="0.1.0", prog_name="paper-slack-bot")
def cli():
    """Paper Slack Bot - Scientific paper discovery for Slack.

    A Slack-focused scientific paper discovery bot with enhanced search,
    journal filtering, and LLM-based relevance scoring.
    """
    pass


@cli.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    default="config.yml",
    help="Path to configuration file",
)
@click.option(
    "--days",
    "-d",
    default=1,
    type=int,
    help="Number of days to look back",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print papers without posting to Slack",
)
def post(config_path: str, days: int, dry_run: bool):
    """Post papers to Slack channel.

    Fetches papers from configured sources, filters them, and posts to Slack.
    """
    try:
        config = Config.from_yaml(config_path)
        config.search.days_back = days

        # Fetch papers
        fetcher = PaperFetcher(ncbi_api_key=config.ncbi_api_key)
        papers = asyncio.run(
            fetcher.fetch_all(
                keywords=config.search.keywords,
                databases=config.search.databases,
                days_back=days,
                max_results_per_source=50,
            )
        )
        click.echo(f"Fetched {len(papers)} papers from {len(config.search.databases)} sources")

        # Apply journal filter
        journal_filter = JournalFilter(config.journals)
        papers = journal_filter.filter_papers(papers)
        click.echo(f"After journal filter: {len(papers)} papers")

        # Apply LLM filter if available
        if config.openai_api_key and papers:
            llm_filter = LLMFilter(api_key=config.openai_api_key, config=config.llm)
            papers = llm_filter.filter_papers(
                papers,
                min_score=50,
                research_interests=config.llm.filtering_prompt,
            )
            click.echo(f"After LLM filter: {len(papers)} papers")

        if dry_run:
            # Print papers to console
            click.echo("\n" + "=" * 80)
            for i, paper in enumerate(papers[:20], 1):
                click.echo(f"\n[{i}] {paper.title}")
                click.echo(f"    Journal: {paper.journal}")
                click.echo(f"    Authors: {', '.join(paper.authors[:3])}")
                click.echo(f"    URL: {paper.url}")
                if paper.relevance_score:
                    click.echo(f"    Relevance: {paper.relevance_score:.0f}/100")
            click.echo("\n" + "=" * 80)
        else:
            # Post to Slack
            bot = PaperSlackBot(config)
            bot.post_papers()
            click.echo("Papers posted to Slack successfully!")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("query")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    default="config.yml",
    help="Path to configuration file",
)
@click.option(
    "--limit",
    "-l",
    default=20,
    type=int,
    help="Maximum number of results",
)
@click.option(
    "--source",
    "-s",
    multiple=True,
    type=click.Choice(["pubmed", "biorxiv", "arxiv"]),
    help="Search specific sources (can be repeated)",
)
def search(query: str, config_path: str, limit: int, source: tuple):
    """Search for papers (print to console).

    QUERY is the search string to use.
    """
    try:
        config = Config.from_yaml(config_path)
        databases = list(source) if source else config.search.databases

        # Search papers
        fetcher = PaperFetcher(ncbi_api_key=config.ncbi_api_key)
        papers = asyncio.run(
            fetcher.search(
                query=query,
                databases=databases,
                max_results_per_source=limit,
            )
        )
        click.echo(f"Found {len(papers)} papers")

        # Apply journal filter
        journal_filter = JournalFilter(config.journals)
        papers = journal_filter.filter_papers(papers)

        # Apply search engine for ranking
        database = Database(config.storage.database_path)
        search_engine = SearchEngine(database, use_semantic=True)
        papers = search_engine.search(query=query, papers=papers)

        # Print results
        click.echo("\n" + "=" * 80)
        for i, paper in enumerate(papers[:limit], 1):
            journal_info = journal_filter.get_journal_info(paper.journal)
            click.echo(f"\n[{i}] {paper.title}")
            click.echo(f"    {journal_info.emoji} {paper.journal}")
            click.echo(f"    Authors: {', '.join(paper.authors[:3])}")
            click.echo(f"    Date: {paper.publication_date}")
            click.echo(f"    Source: {paper.source}")
            click.echo(f"    URL: {paper.url}")
            if paper.abstract:
                abstract = paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
                click.echo(f"    Abstract: {abstract}")
        click.echo("\n" + "=" * 80)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    default="config.yml",
    help="Path to configuration file",
)
def serve(config_path: str):
    """Run the Slack bot server.

    Starts the bot in socket mode and listens for slash commands.
    """
    try:
        config = Config.from_yaml(config_path)
        errors = config.validate()

        if errors:
            for error in errors:
                click.echo(f"Config error: {error}", err=True)
            sys.exit(1)

        bot = PaperSlackBot(config)
        click.echo("Starting Paper Slack Bot...")
        click.echo("Press Ctrl+C to stop")
        bot.run()

    except KeyboardInterrupt:
        click.echo("\nStopping bot...")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("test-config")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    default="config.yml",
    help="Path to configuration file",
)
def test_config(config_path: str):
    """Test configuration file.

    Validates the configuration file and checks API connections.
    """
    try:
        click.echo(f"Loading configuration from {config_path}...")
        config = Config.from_yaml(config_path)

        click.echo("\n📋 Configuration Summary:")
        click.echo(f"  Slack Bot Token: {'✅ Set' if config.slack.bot_token else '❌ Not set'}")
        click.echo(f"  Slack App Token: {'✅ Set' if config.slack.app_token else '❌ Not set'}")
        click.echo(f"  Slack Channel: {config.slack.channel_id or '❌ Not set'}")
        click.echo(f"  NCBI API Key: {'✅ Set' if config.ncbi_api_key else '⚠️ Not set (will be rate limited)'}")
        click.echo(f"  OpenAI API Key: {'✅ Set' if config.openai_api_key else '⚠️ Not set (LLM filtering disabled)'}")

        click.echo(f"\n🔍 Search Configuration:")
        click.echo(f"  Keywords: {', '.join(config.search.keywords) or 'None'}")
        click.echo(f"  Databases: {', '.join(config.search.databases)}")
        click.echo(f"  Days Back: {config.search.days_back}")

        click.echo(f"\n📚 Journal Configuration:")
        click.echo(f"  Include: {', '.join(config.journals.include) or 'All'}")
        click.echo(f"  Exclude: {', '.join(config.journals.exclude) or 'None'}")
        click.echo(f"  Tiers: {', '.join(config.journals.tiers) or 'None'}")
        click.echo(f"  Show Preprints: {'Yes' if config.journals.show_preprints else 'No'}")

        click.echo(f"\n🤖 LLM Configuration:")
        click.echo(f"  Provider: {config.llm.provider}")
        click.echo(f"  Model: {config.llm.model}")
        click.echo(f"  Base URL: {config.llm.base_url or 'Default'}")

        click.echo(f"\n⏰ Schedule Configuration:")
        click.echo(f"  Enabled: {'Yes' if config.schedule.enabled else 'No'}")
        click.echo(f"  Time: {config.schedule.time} {config.schedule.timezone}")

        # Validate
        errors = config.validate()
        if errors:
            click.echo("\n❌ Validation Errors:")
            for error in errors:
                click.echo(f"  - {error}")
            sys.exit(1)
        else:
            click.echo("\n✅ Configuration is valid!")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    default="config.yml",
    help="Path to configuration file",
)
@click.option(
    "--days",
    "-d",
    default=30,
    type=int,
    help="Delete papers older than this many days",
)
def cleanup(config_path: str, days: int):
    """Clean up old papers from the database.

    Removes papers older than the specified number of days.
    """
    try:
        config = Config.from_yaml(config_path)
        database = Database(config.storage.database_path)

        deleted = database.cleanup_old_papers(days=days)
        click.echo(f"Deleted {deleted} papers older than {days} days")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
