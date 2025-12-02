"""Journal name filtering for papers."""

import logging
from dataclasses import dataclass
from typing import Optional

from paper_slack_bot.config import JournalConfig
from paper_slack_bot.storage.database import Paper

logger = logging.getLogger(__name__)


# Known preprint servers for categorization
PREPRINT_SERVERS = [
    "bioRxiv",
    "arXiv",
    "medRxiv",
]

# Journal name normalization mappings
JOURNAL_ALIASES = {
    "nejm": "The New England Journal of Medicine",
    "new england journal of medicine": "The New England Journal of Medicine",
    "pnas": "Proceedings of the National Academy of Sciences",
    "proc natl acad sci": "Proceedings of the National Academy of Sciences",
    "jmlr": "Journal of Machine Learning Research",
    "nat methods": "Nature Methods",
    "nat commun": "Nature Communications",
    "nat biotechnol": "Nature Biotechnology",
    "nat genet": "Nature Genetics",
    "nat med": "Nature Medicine",
    "nat mach intell": "Nature Machine Intelligence",
}

# Emoji indicators
PREPRINT_EMOJI = "📝"
JOURNAL_EMOJI = "📰"


@dataclass
class JournalInfo:
    """Information about a journal."""

    name: str
    normalized_name: str
    is_preprint: bool = False
    emoji: str = JOURNAL_EMOJI


class JournalFilter:
    """Filter papers by journal name."""

    def __init__(self, config: Optional[JournalConfig] = None):
        """Initialize the journal filter.

        Args:
            config: Journal configuration.
        """
        self.config = config or JournalConfig()
        self._preprint_lookup = set(s.lower() for s in PREPRINT_SERVERS)

    def normalize_journal_name(self, name: str) -> str:
        """Normalize a journal name.

        Args:
            name: Journal name to normalize.

        Returns:
            Normalized journal name.
        """
        name_lower = name.lower().strip()

        # Check for known aliases
        if name_lower in JOURNAL_ALIASES:
            return JOURNAL_ALIASES[name_lower]

        # Return original name with title case
        return name.strip()

    def is_preprint(self, journal: str) -> bool:
        """Check if a journal is a preprint server.

        Args:
            journal: Journal name.

        Returns:
            True if the journal is a preprint server.
        """
        journal_lower = journal.lower()

        # Direct match
        if journal_lower in self._preprint_lookup:
            return True

        # Partial match for variations
        for preprint in self._preprint_lookup:
            if preprint in journal_lower or journal_lower in preprint:
                return True

        return False

    def get_journal_emoji(self, journal: str) -> str:
        """Get the emoji indicator for a journal.

        Args:
            journal: Journal name.

        Returns:
            Emoji string.
        """
        if self.is_preprint(journal):
            return PREPRINT_EMOJI
        return JOURNAL_EMOJI

    def get_journal_info(self, journal: str) -> JournalInfo:
        """Get full information about a journal.

        Args:
            journal: Journal name.

        Returns:
            JournalInfo object.
        """
        normalized = self.normalize_journal_name(journal)
        is_preprint = self.is_preprint(journal)
        emoji = self.get_journal_emoji(journal)

        return JournalInfo(
            name=journal,
            normalized_name=normalized,
            is_preprint=is_preprint,
            emoji=emoji,
        )

    def filter_papers(
        self,
        papers: list[Paper],
        exclude_journals: Optional[list[str]] = None,
    ) -> tuple[list[Paper], list[str]]:
        """Filter papers by exclusion list only. All journals are included by default.

        Args:
            papers: List of papers to filter.
            exclude_journals: List of journals to exclude (blacklist).

        Returns:
            Tuple of (filtered papers list, excluded journals list).
        """
        if not papers:
            return [], []

        # Use config values if not specified
        exclude_journals = exclude_journals if exclude_journals is not None else self.config.exclude

        # Build excluded journals set
        excluded_journals = set(j.lower() for j in (exclude_journals or []))

        # Filter papers - include all except explicitly excluded
        filtered = []
        for paper in papers:
            journal_lower = paper.journal.lower()

            # Skip if in exclude list
            if self._matches_any(journal_lower, excluded_journals):
                continue

            filtered.append(paper)

        return filtered, list(exclude_journals or [])

    def _matches_any(self, journal: str, journal_set: set[str]) -> bool:
        """Check if journal matches any in the set.

        Args:
            journal: Journal name (lowercase).
            journal_set: Set of journal names (lowercase).

        Returns:
            True if journal matches any in set.
        """
        # Exact match
        if journal in journal_set:
            return True

        # Partial match
        for j in journal_set:
            if j in journal or journal in j:
                return True

        return False

    def categorize_papers(
        self, papers: list[Paper]
    ) -> dict[str, list[Paper]]:
        """Categorize papers into journals vs preprints.

        Args:
            papers: List of papers to categorize.

        Returns:
            Dictionary with 'journals' and 'preprints' keys.
        """
        categorized: dict[str, list[Paper]] = {
            "journals": [],
            "preprints": [],
        }

        for paper in papers:
            if self.is_preprint(paper.journal):
                categorized["preprints"].append(paper)
            else:
                categorized["journals"].append(paper)

        return categorized
