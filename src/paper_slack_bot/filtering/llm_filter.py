"""LLM-based relevance filtering for papers."""

import json
import logging
from dataclasses import dataclass
from typing import Optional

from paper_slack_bot.config import LLMConfig
from paper_slack_bot.storage.database import Paper

logger = logging.getLogger(__name__)


@dataclass
class RelevanceResult:
    """Result of LLM relevance scoring."""

    score: float  # 0-100
    explanation: str
    paper: Paper


class LLMFilter:
    """LLM-based filter for paper relevance scoring."""

    DEFAULT_PROMPT = """You are a research assistant helping filter scientific papers.
Rate each paper's relevance from 0-100 and provide a brief explanation.
Consider: methodology novelty, dataset quality, and practical applications."""

    def __init__(
        self,
        api_key: str,
        config: Optional[LLMConfig] = None,
    ):
        """Initialize the LLM filter.

        Args:
            api_key: API key for OpenAI or compatible service.
            config: LLM configuration.
        """
        self.api_key = api_key
        self.config = config or LLMConfig()
        self._client = None

    @property
    def client(self):
        """Lazy load the OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI

                client_kwargs = {"api_key": self.api_key}
                if self.config.base_url:
                    client_kwargs["base_url"] = self.config.base_url

                self._client = OpenAI(**client_kwargs)
            except ImportError:
                logger.error("openai package not installed")
                raise
        return self._client

    def score_paper(
        self,
        paper: Paper,
        research_interests: Optional[str] = None,
    ) -> RelevanceResult:
        """Score a single paper's relevance.

        Args:
            paper: Paper to score.
            research_interests: Optional research interests description.

        Returns:
            RelevanceResult with score and explanation.
        """
        prompt = self._build_prompt(paper, research_interests)

        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=300,
            )

            content = response.choices[0].message.content or ""
            score, explanation = self._parse_response(content)

            return RelevanceResult(
                score=score,
                explanation=explanation,
                paper=paper,
            )
        except Exception as e:
            logger.error(f"Error scoring paper: {e}")
            return RelevanceResult(
                score=50.0,
                explanation=f"Error during scoring: {str(e)}",
                paper=paper,
            )

    def score_papers(
        self,
        papers: list[Paper],
        research_interests: Optional[str] = None,
        batch_size: int = 5,
    ) -> list[RelevanceResult]:
        """Score multiple papers for relevance.

        Args:
            papers: List of papers to score.
            research_interests: Optional research interests description.
            batch_size: Number of papers to score in a single API call.

        Returns:
            List of RelevanceResult objects.
        """
        results = []

        # Process papers in batches
        for i in range(0, len(papers), batch_size):
            batch = papers[i : i + batch_size]
            batch_results = self._score_batch(batch, research_interests)
            results.extend(batch_results)

        return results

    def _score_batch(
        self,
        papers: list[Paper],
        research_interests: Optional[str] = None,
    ) -> list[RelevanceResult]:
        """Score a batch of papers.

        Args:
            papers: Batch of papers to score.
            research_interests: Optional research interests description.

        Returns:
            List of RelevanceResult objects.
        """
        prompt = self._build_batch_prompt(papers, research_interests)

        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
            )

            content = response.choices[0].message.content or ""
            return self._parse_batch_response(content, papers)
        except Exception as e:
            logger.error(f"Error scoring batch: {e}")
            return [
                RelevanceResult(score=50.0, explanation=f"Error: {str(e)}", paper=p)
                for p in papers
            ]

    def filter_papers(
        self,
        papers: list[Paper],
        min_score: float = 50.0,
        research_interests: Optional[str] = None,
    ) -> list[Paper]:
        """Filter papers by relevance score.

        Args:
            papers: List of papers to filter.
            min_score: Minimum relevance score (0-100).
            research_interests: Optional research interests description.

        Returns:
            List of papers meeting the minimum score.
        """
        results = self.score_papers(papers, research_interests)

        filtered = []
        for result in results:
            if result.score >= min_score:
                # Update paper with relevance info
                result.paper.relevance_score = result.score
                result.paper.relevance_explanation = result.explanation
                filtered.append(result.paper)

        # Sort by score descending
        filtered.sort(key=lambda p: p.relevance_score or 0, reverse=True)

        return filtered

    def _get_system_prompt(self) -> str:
        """Get the system prompt for the LLM.

        Returns:
            System prompt string.
        """
        return self.config.filtering_prompt or self.DEFAULT_PROMPT

    def _build_prompt(
        self, paper: Paper, research_interests: Optional[str] = None
    ) -> str:
        """Build prompt for single paper scoring.

        Args:
            paper: Paper to score.
            research_interests: Optional research interests.

        Returns:
            Prompt string.
        """
        prompt = f"""Please evaluate the relevance of this scientific paper:

Title: {paper.title}
Authors: {', '.join(paper.authors[:5])}{'...' if len(paper.authors) > 5 else ''}
Journal: {paper.journal}
Abstract: {paper.abstract[:1000]}{'...' if len(paper.abstract) > 1000 else ''}
"""

        if research_interests:
            prompt += f"\nResearch interests: {research_interests}\n"

        prompt += """
Provide your response in the following JSON format:
{
    "score": <0-100>,
    "explanation": "<brief explanation of the score>"
}
"""
        return prompt

    def _build_batch_prompt(
        self,
        papers: list[Paper],
        research_interests: Optional[str] = None,
    ) -> str:
        """Build prompt for batch paper scoring.

        Args:
            papers: List of papers to score.
            research_interests: Optional research interests.

        Returns:
            Prompt string.
        """
        prompt = "Please evaluate the relevance of these scientific papers:\n\n"

        for i, paper in enumerate(papers, 1):
            prompt += f"""Paper {i}:
Title: {paper.title}
Journal: {paper.journal}
Abstract: {paper.abstract[:500]}{'...' if len(paper.abstract) > 500 else ''}

"""

        if research_interests:
            prompt += f"Research interests: {research_interests}\n\n"

        prompt += """Provide your response as a JSON array:
[
    {"paper": 1, "score": <0-100>, "explanation": "<brief explanation>"},
    {"paper": 2, "score": <0-100>, "explanation": "<brief explanation>"},
    ...
]
"""
        return prompt

    def _parse_response(self, content: str) -> tuple[float, str]:
        """Parse LLM response for single paper.

        Args:
            content: LLM response content.

        Returns:
            Tuple of (score, explanation).
        """
        try:
            # Try to parse JSON
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                data = json.loads(json_str)
                return float(data.get("score", 50)), data.get(
                    "explanation", "No explanation provided"
                )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Error parsing LLM response: {e}")

        # Fallback: try to extract score from text
        import re

        score_match = re.search(r"(\d{1,3})\s*[/\\]?\s*100", content)
        if score_match:
            return float(score_match.group(1)), content

        return 50.0, content

    def _parse_batch_response(
        self, content: str, papers: list[Paper]
    ) -> list[RelevanceResult]:
        """Parse LLM response for batch scoring.

        Args:
            content: LLM response content.
            papers: Original papers list.

        Returns:
            List of RelevanceResult objects.
        """
        results = []

        try:
            # Try to parse JSON array
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                data = json.loads(json_str)

                for i, item in enumerate(data):
                    if i < len(papers):
                        score = float(item.get("score", 50))
                        explanation = item.get("explanation", "No explanation")
                        results.append(
                            RelevanceResult(
                                score=score,
                                explanation=explanation,
                                paper=papers[i],
                            )
                        )

                # Fill in missing papers with default scores
                for i in range(len(results), len(papers)):
                    results.append(
                        RelevanceResult(
                            score=50.0,
                            explanation="Not scored",
                            paper=papers[i],
                        )
                    )

                return results
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Error parsing batch response: {e}")

        # Fallback: return default scores
        return [
            RelevanceResult(score=50.0, explanation="Parse error", paper=p)
            for p in papers
        ]


class OllamaFilter(LLMFilter):
    """LLM filter using local Ollama models."""

    def __init__(
        self,
        model: str = "llama2",
        base_url: str = "http://localhost:11434/v1",
        config: Optional[LLMConfig] = None,
    ):
        """Initialize the Ollama filter.

        Args:
            model: Ollama model name.
            base_url: Ollama API base URL.
            config: LLM configuration.
        """
        # Ollama uses a dummy API key
        super().__init__(api_key="ollama", config=config)
        self.config.model = model
        self.config.base_url = base_url
