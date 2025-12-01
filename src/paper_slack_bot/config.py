"""Configuration management for Paper Slack Bot."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv


@dataclass
class SlackConfig:
    """Slack configuration."""

    bot_token: str = ""
    app_token: str = ""
    channel_id: str = ""


@dataclass
class SearchConfig:
    """Search configuration."""

    keywords: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=lambda: ["pubmed", "biorxiv", "arxiv"])
    days_back: int = 1


@dataclass
class JournalConfig:
    """Journal filtering configuration."""

    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    tiers: list[str] = field(default_factory=list)
    show_preprints: bool = True

    # Pre-defined journal tiers
    TIER1_JOURNALS: list[str] = field(
        default_factory=lambda: [
            "Nature",
            "Science",
            "Cell",
            "The New England Journal of Medicine",
            "NEJM",
            "Lancet",
            "The Lancet",
        ]
    )
    TIER2_JOURNALS: list[str] = field(
        default_factory=lambda: [
            "Nature Methods",
            "Nature Communications",
            "PNAS",
            "Proceedings of the National Academy of Sciences",
            "eLife",
            "Nature Biotechnology",
            "Nature Genetics",
        ]
    )
    ML_JOURNALS: list[str] = field(
        default_factory=lambda: [
            "NeurIPS",
            "ICML",
            "Nature Machine Intelligence",
            "ICLR",
            "Journal of Machine Learning Research",
        ]
    )
    PREPRINT_SERVERS: list[str] = field(
        default_factory=lambda: ["bioRxiv", "arXiv", "medRxiv"]
    )

    def get_allowed_journals(self) -> set[str]:
        """Get the set of allowed journals based on tiers and include list."""
        allowed = set(self.include)
        for tier in self.tiers:
            tier_lower = tier.lower()
            if tier_lower == "tier1":
                allowed.update(self.TIER1_JOURNALS)
            elif tier_lower == "tier2":
                allowed.update(self.TIER2_JOURNALS)
            elif tier_lower in ("ml", "ml-focused"):
                allowed.update(self.ML_JOURNALS)
        if self.show_preprints:
            allowed.update(self.PREPRINT_SERVERS)
        return allowed


@dataclass
class LLMConfig:
    """LLM configuration."""

    provider: str = "openai"
    model: str = "gpt-4o-mini"
    base_url: Optional[str] = None
    filtering_prompt: str = """You are a research assistant helping filter scientific papers.
Rate each paper's relevance from 0-100 and provide a brief explanation.
Consider: methodology novelty, dataset quality, and practical applications."""


@dataclass
class ScheduleConfig:
    """Schedule configuration."""

    enabled: bool = True
    time: str = "09:00"
    timezone: str = "UTC"


@dataclass
class StorageConfig:
    """Storage configuration."""

    database_path: str = "papers.db"
    cache_days: int = 30


@dataclass
class Config:
    """Main configuration class."""

    slack: SlackConfig = field(default_factory=SlackConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    journals: JournalConfig = field(default_factory=JournalConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    ncbi_api_key: str = ""
    openai_api_key: str = ""

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        """Load configuration from a YAML file.

        Args:
            path: Path to the configuration file.

        Returns:
            Config object with loaded settings.
        """
        load_dotenv()

        with open(path, "r") as f:
            raw_config = yaml.safe_load(f) or {}

        # Resolve environment variables
        config_str = yaml.dump(raw_config)
        config_str = cls._resolve_env_vars(config_str)
        config_data = yaml.safe_load(config_str)

        return cls._from_dict(config_data)

    @staticmethod
    def _resolve_env_vars(text: str) -> str:
        """Resolve environment variable references in text.

        Args:
            text: Text containing ${VAR_NAME} patterns.

        Returns:
            Text with environment variables resolved.
        """
        pattern = r"\$\{([^}]+)\}"

        def replace_env_var(match: re.Match) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, "")

        return re.sub(pattern, replace_env_var, text)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "Config":
        """Create Config from dictionary.

        Args:
            data: Configuration dictionary.

        Returns:
            Config object.
        """
        config = cls()

        # Slack config
        if "slack" in data:
            slack_data = data["slack"]
            config.slack = SlackConfig(
                bot_token=slack_data.get("bot_token", ""),
                app_token=slack_data.get("app_token", ""),
                channel_id=slack_data.get("channel_id", ""),
            )

        # API keys
        config.ncbi_api_key = data.get("ncbi_api_key", "")
        config.openai_api_key = data.get("openai_api_key", "")

        # Search config
        if "search" in data:
            search_data = data["search"]
            config.search = SearchConfig(
                keywords=search_data.get("keywords", []),
                databases=search_data.get("databases", ["pubmed", "biorxiv", "arxiv"]),
                days_back=search_data.get("days_back", 1),
            )

        # Journal config
        if "journals" in data:
            journal_data = data["journals"]
            config.journals = JournalConfig(
                include=journal_data.get("include", []),
                exclude=journal_data.get("exclude", []),
                tiers=journal_data.get("tiers", []),
                show_preprints=journal_data.get("show_preprints", True),
            )

        # LLM config
        if "llm" in data:
            llm_data = data["llm"]
            config.llm = LLMConfig(
                provider=llm_data.get("provider", "openai"),
                model=llm_data.get("model", "gpt-4o-mini"),
                base_url=llm_data.get("base_url"),
                filtering_prompt=llm_data.get("filtering_prompt", config.llm.filtering_prompt),
            )

        # Schedule config
        if "schedule" in data:
            schedule_data = data["schedule"]
            config.schedule = ScheduleConfig(
                enabled=schedule_data.get("enabled", True),
                time=schedule_data.get("time", "09:00"),
                timezone=schedule_data.get("timezone", "UTC"),
            )

        # Storage config
        if "storage" in data:
            storage_data = data["storage"]
            config.storage = StorageConfig(
                database_path=storage_data.get("database_path", "papers.db"),
                cache_days=storage_data.get("cache_days", 30),
            )

        return config

    def validate(self) -> list[str]:
        """Validate the configuration.

        Returns:
            List of validation error messages.
        """
        errors = []

        if not self.slack.bot_token:
            errors.append("Slack bot token is required")
        if not self.slack.app_token:
            errors.append("Slack app token is required")
        if not self.slack.channel_id:
            errors.append("Slack channel ID is required")

        if self.llm.provider == "openai" and not self.openai_api_key:
            errors.append("OpenAI API key is required when using OpenAI provider")

        return errors
