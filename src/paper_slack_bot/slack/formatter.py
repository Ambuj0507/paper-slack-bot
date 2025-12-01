"""Rich message formatting for Slack."""

from typing import Any, Optional

from paper_slack_bot.search.journal_filter import JournalFilter
from paper_slack_bot.storage.database import Paper


class SlackFormatter:
    """Format papers for Slack messages with rich formatting."""

    def __init__(self, journal_filter: Optional[JournalFilter] = None):
        """Initialize the formatter.

        Args:
            journal_filter: Optional JournalFilter for journal info.
        """
        self.journal_filter = journal_filter or JournalFilter()

    def format_paper(
        self,
        paper: Paper,
        show_abstract: bool = True,
        show_relevance: bool = True,
        show_actions: bool = True,
    ) -> list[dict[str, Any]]:
        """Format a single paper as Slack blocks.

        Args:
            paper: Paper to format.
            show_abstract: Whether to show abstract preview.
            show_relevance: Whether to show relevance score.
            show_actions: Whether to show action buttons.

        Returns:
            List of Slack block elements.
        """
        blocks: list[dict[str, Any]] = []

        # Get journal info
        journal_info = self.journal_filter.get_journal_info(paper.journal)

        # Title with link
        title_text = f"*<{paper.url}|{paper.title}>*"
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": title_text},
            }
        )

        # Authors and journal
        authors_text = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors_text += f" et al. ({len(paper.authors)} authors)"

        metadata_text = f"👤 {authors_text}\n"
        metadata_text += f"{journal_info.emoji} *{paper.journal}*"
        if paper.publication_date:
            metadata_text += f" | 📅 {paper.publication_date}"
        if paper.source:
            metadata_text += f" | 🏷️ {paper.source}"

        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": metadata_text}],
            }
        )

        # Relevance score
        if show_relevance and paper.relevance_score is not None:
            score = paper.relevance_score
            score_bar = self._score_to_bar(score)
            relevance_text = f"🎯 Relevance: {score_bar} {score:.0f}/100"
            if paper.relevance_explanation:
                relevance_text += f"\n_{paper.relevance_explanation}_"

            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": relevance_text},
                }
            )

        # Abstract preview
        if show_abstract and paper.abstract:
            abstract_preview = paper.abstract[:500]
            if len(paper.abstract) > 500:
                abstract_preview += "..."
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"📝 {abstract_preview}"},
                }
            )

        # Action buttons
        if show_actions:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "💾 Save"},
                            "action_id": f"save_paper_{paper.doi or paper.title[:20]}",
                            "value": paper.doi or paper.url,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "📤 Share"},
                            "action_id": f"share_paper_{paper.doi or paper.title[:20]}",
                            "value": paper.url,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "❌ Dismiss"},
                            "action_id": f"dismiss_paper_{paper.doi or paper.title[:20]}",
                            "value": paper.doi or paper.url,
                        },
                    ],
                }
            )

        # Divider
        blocks.append({"type": "divider"})

        return blocks

    def format_papers(
        self,
        papers: list[Paper],
        title: Optional[str] = None,
        show_abstract: bool = True,
        show_relevance: bool = True,
        show_actions: bool = True,
        max_papers: int = 10,
    ) -> list[dict[str, Any]]:
        """Format multiple papers as Slack blocks.

        Args:
            papers: List of papers to format.
            title: Optional title for the message.
            show_abstract: Whether to show abstract preview.
            show_relevance: Whether to show relevance score.
            show_actions: Whether to show action buttons.
            max_papers: Maximum number of papers to include.

        Returns:
            List of Slack block elements.
        """
        blocks: list[dict[str, Any]] = []

        # Header
        if title:
            blocks.append(
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": title, "emoji": True},
                }
            )

        # Summary
        if papers:
            summary = f"Found *{len(papers)}* papers"
            if len(papers) > max_papers:
                summary += f" (showing top {max_papers})"
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": summary},
                }
            )
            blocks.append({"type": "divider"})

        # Papers
        for paper in papers[:max_papers]:
            paper_blocks = self.format_paper(
                paper,
                show_abstract=show_abstract,
                show_relevance=show_relevance,
                show_actions=show_actions,
            )
            blocks.extend(paper_blocks)

        # No papers found
        if not papers:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "📭 No papers found matching your criteria.",
                    },
                }
            )

        return blocks

    def format_digest(
        self,
        papers: list[Paper],
        date: str,
    ) -> list[dict[str, Any]]:
        """Format a daily digest of papers.

        Args:
            papers: List of papers for the digest.
            date: Date string for the digest.

        Returns:
            List of Slack block elements.
        """
        blocks: list[dict[str, Any]] = []

        # Header
        blocks.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📚 Paper Digest - {date}",
                    "emoji": True,
                },
            }
        )

        # Categorize papers by journal tier
        categorized = self.journal_filter.categorize_papers(papers)

        # Summary by tier
        summary_parts = []
        for tier, tier_papers in categorized.items():
            if tier_papers:
                emoji = {
                    "tier1": "🏆",
                    "tier2": "⭐",
                    "ml": "🤖",
                    "preprints": "📝",
                    "other": "📄",
                }.get(tier, "📄")
                summary_parts.append(f"{emoji} {tier.title()}: {len(tier_papers)}")

        if summary_parts:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": " | ".join(summary_parts),
                    },
                }
            )

        blocks.append({"type": "divider"})

        # Papers by tier
        for tier in ["tier1", "tier2", "ml", "preprints", "other"]:
            tier_papers = categorized.get(tier, [])
            if not tier_papers:
                continue

            tier_names = {
                "tier1": "🏆 Top Tier Journals",
                "tier2": "⭐ High-Impact Journals",
                "ml": "🤖 ML/AI Journals",
                "preprints": "📝 Preprints",
                "other": "📄 Other Journals",
            }

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{tier_names.get(tier, tier)}*",
                    },
                }
            )

            for paper in tier_papers[:5]:  # Limit per tier
                paper_blocks = self.format_paper(
                    paper,
                    show_abstract=False,  # Compact view for digest
                    show_relevance=True,
                    show_actions=True,
                )
                blocks.extend(paper_blocks)

        return blocks

    def format_search_results(
        self,
        papers: list[Paper],
        query: str,
        user_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Format search results for Slack.

        Args:
            papers: List of papers found.
            query: Search query used.
            user_id: Optional user ID who ran the search.

        Returns:
            List of Slack block elements.
        """
        blocks = self.format_papers(
            papers,
            title=f"🔍 Search Results: {query}",
            show_abstract=True,
            show_relevance=True,
            show_actions=True,
            max_papers=10,
        )

        # Add "more results" button if needed
        if len(papers) > 10:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": f"View all {len(papers)} results",
                            },
                            "action_id": "view_all_results",
                            "value": query,
                        }
                    ],
                }
            )

        return blocks

    def format_journal_list(
        self,
        journals: list[str],
        tier: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Format a list of journals.

        Args:
            journals: List of journal names.
            tier: Optional tier name.

        Returns:
            List of Slack block elements.
        """
        blocks: list[dict[str, Any]] = []

        title = "📚 Configured Journals"
        if tier:
            title = f"📚 {tier.title()} Journals"

        blocks.append(
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title, "emoji": True},
            }
        )

        if journals:
            journal_list = "\n".join(
                f"• {self.journal_filter.get_journal_emoji(j)} {j}" for j in journals
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": journal_list},
                }
            )
        else:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "No journals configured.",
                    },
                }
            )

        return blocks

    def format_settings(
        self,
        settings: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Format settings for display.

        Args:
            settings: Settings dictionary.

        Returns:
            List of Slack block elements.
        """
        blocks: list[dict[str, Any]] = []

        blocks.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚙️ Bot Settings",
                    "emoji": True,
                },
            }
        )

        settings_text = ""
        for key, value in settings.items():
            settings_text += f"• *{key}*: {value}\n"

        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": settings_text or "No settings"},
            }
        )

        return blocks

    def format_error(self, message: str) -> list[dict[str, Any]]:
        """Format an error message.

        Args:
            message: Error message.

        Returns:
            List of Slack block elements.
        """
        return [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"❌ *Error*: {message}"},
            }
        ]

    def format_success(self, message: str) -> list[dict[str, Any]]:
        """Format a success message.

        Args:
            message: Success message.

        Returns:
            List of Slack block elements.
        """
        return [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"✅ {message}"},
            }
        ]

    def _score_to_bar(self, score: float, length: int = 10) -> str:
        """Convert a score to a progress bar.

        Args:
            score: Score from 0-100.
            length: Length of the bar.

        Returns:
            Progress bar string.
        """
        filled = int((score / 100) * length)
        empty = length - filled
        return "▓" * filled + "░" * empty
