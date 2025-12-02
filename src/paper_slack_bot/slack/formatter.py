"""Rich message formatting for Slack."""

from typing import Any, Optional

from paper_slack_bot.search.journal_filter import JournalFilter
from paper_slack_bot.storage.database import Paper

# Slack API limit for blocks per message
MAX_BLOCKS_PER_MESSAGE = 50

# Error message patterns that should not be displayed to users
ERROR_EXPLANATION_PATTERNS = [
    "unable to parse",
    "unable to score",
    "error during scoring",
    "error:",
    "not scored",
]


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
            # Check if explanation is an error message
            explanation_is_error = self._is_error_explanation(paper.relevance_explanation)

            # Don't show relevance section at all if it's an error
            if not explanation_is_error:
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
                            "action_id": "save_paper",
                            "value": paper.doi or paper.url,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "📤 Share"},
                            "action_id": "share_paper",
                            "value": paper.url,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "❌ Dismiss"},
                            "action_id": "dismiss_paper",
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
        """Format multiple papers as Slack blocks, grouped by journals vs preprints.

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

        # Categorize papers into journals vs preprints
        categorized = self.journal_filter.categorize_papers(papers)
        journal_papers = categorized.get("journals", [])
        preprint_papers = categorized.get("preprints", [])

        # Summary
        summary = f"Found *{len(papers)}* papers"
        summary += f" (📰 {len(journal_papers)} journals, 📝 {len(preprint_papers)} preprints)"
        if len(papers) > max_papers:
            summary += f" - showing top {max_papers}"
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": summary},
            }
        )
        blocks.append({"type": "divider"})

        # Calculate how many papers to show from each category
        papers_shown = 0
        remaining = max_papers

        # Show journal articles first
        if journal_papers and remaining > 0:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*📰 Journal Articles*"},
                }
            )
            for paper in journal_papers[:remaining]:
                paper_blocks = self.format_paper(
                    paper,
                    show_abstract=show_abstract,
                    show_relevance=show_relevance,
                    show_actions=show_actions,
                )
                blocks.extend(paper_blocks)
                papers_shown += 1
            remaining = max_papers - papers_shown

        # Show preprints
        if preprint_papers and remaining > 0:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*📝 Preprints*"},
                }
            )
            for paper in preprint_papers[:remaining]:
                paper_blocks = self.format_paper(
                    paper,
                    show_abstract=show_abstract,
                    show_relevance=show_relevance,
                    show_actions=show_actions,
                )
                blocks.extend(paper_blocks)

        return blocks

    def format_digest(
        self,
        papers: list[Paper],
        date: str,
    ) -> list[dict[str, Any]]:
        """Format a daily digest of papers, grouped by journals vs preprints.

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

        # Categorize papers into journals vs preprints
        categorized = self.journal_filter.categorize_papers(papers)
        journal_papers = categorized.get("journals", [])
        preprint_papers = categorized.get("preprints", [])

        # Summary
        summary_parts = []
        if journal_papers:
            summary_parts.append(f"📰 Journals: {len(journal_papers)}")
        if preprint_papers:
            summary_parts.append(f"📝 Preprints: {len(preprint_papers)}")

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

        # Journal Articles section
        if journal_papers:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*📰 Journal Articles*",
                    },
                }
            )

            for paper in journal_papers:
                paper_blocks = self.format_paper(
                    paper,
                    show_abstract=False,  # Compact view for digest
                    show_relevance=True,
                    show_actions=True,
                )
                blocks.extend(paper_blocks)

        # Preprints section
        if preprint_papers:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*📝 Preprints*",
                    },
                }
            )

            for paper in preprint_papers:
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

    @staticmethod
    def _is_error_explanation(explanation: Optional[str]) -> bool:
        """Check if the relevance explanation indicates an error.

        Args:
            explanation: The relevance explanation text.

        Returns:
            True if the explanation is an error message, False otherwise.
        """
        if not explanation:
            return False
        explanation_lower = explanation.lower()
        return any(pattern in explanation_lower for pattern in ERROR_EXPLANATION_PATTERNS)

    @staticmethod
    def split_blocks(
        blocks: list[dict[str, Any]],
        max_blocks: int = MAX_BLOCKS_PER_MESSAGE,
    ) -> list[list[dict[str, Any]]]:
        """Split blocks into multiple messages to respect Slack's 50-block limit.

        Args:
            blocks: List of Slack block elements.
            max_blocks: Maximum number of blocks per message (default: 50).

        Returns:
            List of block lists, each within the max_blocks limit.
        """
        if len(blocks) <= max_blocks:
            return [blocks]

        result = []
        current_batch = []

        for block in blocks:
            current_batch.append(block)
            if len(current_batch) >= max_blocks:
                result.append(current_batch)
                current_batch = []

        if current_batch:
            result.append(current_batch)

        return result

    @staticmethod
    def create_continuation_header(title: str, part_number: int) -> dict[str, Any]:
        """Create a continuation header block for multi-part messages.

        Args:
            title: The title prefix for the continuation message.
            part_number: The part number (1-indexed).

        Returns:
            A Slack section block with the continuation header.
        """
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{title} (continued - part {part_number})",
            },
        }
