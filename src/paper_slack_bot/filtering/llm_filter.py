"""LLM-based relevance filtering for papers."""

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from paper_slack_bot.config import LLMConfig
from paper_slack_bot.storage.database import Paper

logger = logging.getLogger(__name__)

# Score bounds for relevance scoring
MIN_SCORE = 0
MAX_SCORE = 100


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
                RelevanceResult(score=50.0, explanation=f"Error: {str(e)}", paper=p) for p in papers
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

    def _build_prompt(self, paper: Paper, research_interests: Optional[str] = None) -> str:
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

    def _parse_batch_response(self, content: str, papers: list[Paper]) -> list[RelevanceResult]:
        """Parse LLM response for batch scoring.

        Args:
            content: LLM response content.
            papers: Original papers list.

        Returns:
            List of RelevanceResult objects.
        """
        results = []

        # First, try to clean markdown code blocks if present
        cleaned_content = content
        # Remove markdown code blocks (```json ... ``` or ``` ... ```)
        code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        if code_block_match:
            cleaned_content = code_block_match.group(1)

        try:
            # Try to parse JSON array
            start = cleaned_content.find("[")
            end = cleaned_content.rfind("]") + 1
            if start >= 0 and end > start:
                json_str = cleaned_content[start:end]
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
            logger.warning(f"Error parsing batch response as JSON array: {e}")

        # Try to parse individual JSON objects for each paper
        try:
            json_objects = re.findall(r"\{[^{}]*\}", cleaned_content)
            if json_objects:
                for i, json_str in enumerate(json_objects):
                    if i < len(papers):
                        try:
                            item = json.loads(json_str)
                            score = float(item.get("score", 50))
                            explanation = item.get("explanation", "No explanation")
                            results.append(
                                RelevanceResult(
                                    score=score,
                                    explanation=explanation,
                                    paper=papers[i],
                                )
                            )
                        except (json.JSONDecodeError, ValueError):
                            continue

                if results:
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
        except Exception as e:
            logger.warning(f"Error parsing individual JSON objects: {e}")

        # Fallback: try to extract scores using regex patterns
        # Look for patterns like "Paper 1: 85/100" or "1. Score: 85"
        score_patterns = [
            r"[Pp]aper\s*(\d+)[:\s]+(\d{1,3})(?:/100)?",
            r"(\d+)\.\s*[Ss]core[:\s]+(\d{1,3})",
            r"(\d+)[.)\s]+.*?(\d{1,3})\s*/\s*100",
        ]

        for pattern in score_patterns:
            matches = re.findall(pattern, content)
            if matches:
                paper_scores = {}
                for match in matches:
                    paper_num = int(match[0])
                    score = min(MAX_SCORE, max(MIN_SCORE, int(match[1])))
                    paper_scores[paper_num] = score

                if paper_scores:
                    for i, paper in enumerate(papers, 1):
                        score = float(paper_scores.get(i, 50))
                        results.append(
                            RelevanceResult(
                                score=score,
                                explanation="Score extracted from text",
                                paper=paper,
                            )
                        )
                    return results

        # Final fallback: return default scores with descriptive explanation
        return [
            RelevanceResult(
                score=50.0,
                explanation="Unable to parse LLM response",
                paper=p,
            )
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
