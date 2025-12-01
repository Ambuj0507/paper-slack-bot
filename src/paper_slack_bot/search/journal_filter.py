"""Journal name filtering for papers."""

import logging
from dataclasses import dataclass
from typing import Optional

from paper_slack_bot.config import JournalConfig
from paper_slack_bot.storage.database import Paper

logger = logging.getLogger(__name__)


# Pre-defined journal tiers with common variations
JOURNAL_TIERS = {
    "tier1": [
        "Nature",
        "Science",
        "Cell",
        "The New England Journal of Medicine",
        "NEJM",
        "Lancet",
        "The Lancet",
    ],
    "tier2": [
        "Nature Methods",
        "Nature Communications",
        "PNAS",
        "Proceedings of the National Academy of Sciences",
        "eLife",
        "Nature Biotechnology",
        "Nature Genetics",
        "Nature Medicine",
        "Nature Reviews",
    ],
    "ml": [
        "NeurIPS",
        "ICML",
        "ICLR",
        "Nature Machine Intelligence",
        "Journal of Machine Learning Research",
        "JMLR",
        "Advances in Neural Information Processing Systems",
    ],
    "preprints": [
        "bioRxiv",
        "arXiv",
        "medRxiv",
    ],
}

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

# Journal emoji indicators
JOURNAL_EMOJIS = {
    "tier1": "🏆",
    "tier2": "⭐",
    "ml": "🤖",
    "preprints": "📝",
    "default": "📄",
}


@dataclass
class JournalInfo:
    """Information about a journal."""

    name: str
    normalized_name: str
    tier: Optional[str] = None
    emoji: str = "📄"


class JournalFilter:
    """Filter papers by journal name and tier."""

    def __init__(self, config: Optional[JournalConfig] = None):
        """Initialize the journal filter.

        Args:
            config: Journal configuration.
        """
        self.config = config or JournalConfig()
        self._build_lookup_tables()

    def _build_lookup_tables(self) -> None:
        """Build lookup tables for fast journal matching."""
        self._tier_lookup: dict[str, str] = {}
        for tier, journals in JOURNAL_TIERS.items():
            for journal in journals:
                self._tier_lookup[journal.lower()] = tier

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

    def get_journal_tier(self, journal: str) -> Optional[str]:
        """Get the tier of a journal.

        Args:
            journal: Journal name.

        Returns:
            Tier name (tier1, tier2, ml, preprints) or None.
        """
        journal_lower = journal.lower()

        # Direct lookup
        if journal_lower in self._tier_lookup:
            return self._tier_lookup[journal_lower]

        # Partial matching for variations
        for tier, journals in JOURNAL_TIERS.items():
            for j in journals:
                if j.lower() in journal_lower or journal_lower in j.lower():
                    return tier

        return None

    def get_journal_emoji(self, journal: str) -> str:
        """Get the emoji indicator for a journal.

        Args:
            journal: Journal name.

        Returns:
            Emoji string.
        """
        tier = self.get_journal_tier(journal)
        return JOURNAL_EMOJIS.get(tier or "default", JOURNAL_EMOJIS["default"])

    def get_journal_info(self, journal: str) -> JournalInfo:
        """Get full information about a journal.

        Args:
            journal: Journal name.

        Returns:
            JournalInfo object.
        """
        normalized = self.normalize_journal_name(journal)
        tier = self.get_journal_tier(journal)
        emoji = self.get_journal_emoji(journal)

        return JournalInfo(
            name=journal,
            normalized_name=normalized,
            tier=tier,
            emoji=emoji,
        )

    def filter_papers(
        self,
        papers: list[Paper],
        include_journals: Optional[list[str]] = None,
        exclude_journals: Optional[list[str]] = None,
        tiers: Optional[list[str]] = None,
        show_preprints: bool = True,
    ) -> list[Paper]:
        """Filter papers by journal criteria.

        Args:
            papers: List of papers to filter.
            include_journals: List of journals to include (whitelist).
            exclude_journals: List of journals to exclude (blacklist).
            tiers: List of tiers to include (tier1, tier2, ml, preprints).
            show_preprints: Whether to show preprints.

        Returns:
            Filtered list of papers.
        """
        if not papers:
            return []

        # Use config values if not specified
        include_journals = include_journals or self.config.include
        exclude_journals = exclude_journals or self.config.exclude
        tiers = tiers or self.config.tiers
        show_preprints = (
            show_preprints if show_preprints is not None else self.config.show_preprints
        )

        # Build allowed journals set
        allowed_journals: set[str] = set()

        # Add journals from specified tiers
        if tiers:
            for tier in tiers:
                tier_lower = tier.lower()
                if tier_lower in JOURNAL_TIERS:
                    allowed_journals.update(
                        j.lower() for j in JOURNAL_TIERS[tier_lower]
                    )

        # Add explicitly included journals
        if include_journals:
            allowed_journals.update(j.lower() for j in include_journals)

        # Add preprints if allowed
        if show_preprints:
            allowed_journals.update(j.lower() for j in JOURNAL_TIERS["preprints"])

        # Build excluded journals set
        excluded_journals = set(j.lower() for j in (exclude_journals or []))

        # Filter papers
        filtered = []
        for paper in papers:
            journal_lower = paper.journal.lower()

            # Skip if in exclude list
            if self._matches_any(journal_lower, excluded_journals):
                continue

            # If no allowed journals specified, include all (except excluded)
            if not allowed_journals:
                filtered.append(paper)
                continue

            # Check if in allowed list
            if self._matches_any(journal_lower, allowed_journals):
                filtered.append(paper)

        return filtered

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
        """Categorize papers by journal tier.

        Args:
            papers: List of papers to categorize.

        Returns:
            Dictionary mapping tier to list of papers.
        """
        categorized: dict[str, list[Paper]] = {
            "tier1": [],
            "tier2": [],
            "ml": [],
            "preprints": [],
            "other": [],
        }

        for paper in papers:
            tier = self.get_journal_tier(paper.journal)
            if tier:
                categorized[tier].append(paper)
            else:
                categorized["other"].append(paper)

        return categorized

    def get_tier_journals(self, tier: str) -> list[str]:
        """Get list of journals in a tier.

        Args:
            tier: Tier name.

        Returns:
            List of journal names.
        """
        return JOURNAL_TIERS.get(tier.lower(), [])

    def get_all_tiers(self) -> list[str]:
        """Get list of all tier names.

        Returns:
            List of tier names.
        """
        return list(JOURNAL_TIERS.keys())
