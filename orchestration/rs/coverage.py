"""Dynamic coverage topic system for the Retrieval Subgraph.

The coverage system defines what topics must be researched for a company.
The base set of default topics can be expanded dynamically by the LLM
during plan_retrieval based on the company's profile and financial features.

The coverage_gate uses this system to determine whether enough evidence
has been gathered across all required topics before proceeding.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Default topic categories
# ---------------------------------------------------------------------------

class CoverageTopicCategory(str, Enum):
    """Base coverage topic categories (the LLM can add custom ones)."""
    governance = "governance"
    financials = "financials"
    legal_regulatory = "legal_regulatory"
    market_position = "market_position"
    management = "management"
    controversy = "controversy"
    competition = "competition"
    environmental = "environmental"


DEFAULT_TOPICS: list[str] = [t.value for t in CoverageTopicCategory]


class CoverageTopic(BaseModel):
    """A single coverage topic with its evidence tracking."""
    name: str
    description: str = ""
    required: bool = True
    min_sources: int = 2          # Minimum unique sources needed
    found_sources: int = 0
    sample_queries: list[str] = Field(default_factory=list)
    is_satisfied: bool = False


class CoverageState(BaseModel):
    """Tracks coverage across all topics for a case."""
    topics: list[CoverageTopic] = Field(default_factory=list)
    max_retry_attempts: int = 2
    current_attempt: int = 0
    overall_status: str = "not_started"  # not_started, partial, sufficient, insufficient

    def get_missing_topics(self) -> list[CoverageTopic]:
        return [t for t in self.topics if t.required and not t.is_satisfied]

    def get_covered_topics(self) -> list[CoverageTopic]:
        return [t for t in self.topics if t.is_satisfied]

    def check_coverage(self) -> str:
        """Returns overall coverage status."""
        missing = self.get_missing_topics()
        covered = self.get_covered_topics()

        if not self.topics:
            return "not_started"
        if not missing:
            return "sufficient"
        if covered:
            return "partial"
        return "insufficient"

    def can_retry(self) -> bool:
        return self.current_attempt < self.max_retry_attempts

    def update_topic(self, topic_name: str, source_count: int) -> None:
        """Update a topic's source count and satisfaction status."""
        for topic in self.topics:
            if topic.name == topic_name:
                topic.found_sources = source_count
                topic.is_satisfied = source_count >= topic.min_sources
                break


def build_default_coverage_topics(
    company_name: str | None = None,
    industry: str | None = None,
) -> list[CoverageTopic]:
    """Build the default set of coverage topics with descriptions.

    These serve as the base set. The LLM in plan_retrieval can expand
    this list with company-specific or industry-specific topics.
    """
    suffix = f" for {company_name}" if company_name else ""

    topics = [
        CoverageTopic(
            name="governance",
            description=f"Corporate governance structure, board composition, executive oversight{suffix}",
            min_sources=2,
            sample_queries=[
                f"{company_name or 'company'} corporate governance board of directors",
                f"{company_name or 'company'} executive leadership changes",
            ],
        ),
        CoverageTopic(
            name="financials",
            description=f"Financial health, earnings, revenue trends, debt management{suffix}",
            min_sources=2,
            sample_queries=[
                f"{company_name or 'company'} financial results revenue earnings",
                f"{company_name or 'company'} debt obligations credit rating",
            ],
        ),
        CoverageTopic(
            name="legal_regulatory",
            description=f"Legal proceedings, regulatory actions, compliance issues{suffix}",
            min_sources=2,
            sample_queries=[
                f"{company_name or 'company'} lawsuit regulatory action SEC",
                f"{company_name or 'company'} compliance violation penalty",
            ],
        ),
        CoverageTopic(
            name="market_position",
            description=f"Market share, competitive advantages, industry positioning{suffix}",
            min_sources=2,
            sample_queries=[
                f"{company_name or 'company'} market share industry position",
                f"{company_name or 'company'} competitive advantage moat",
            ],
        ),
        CoverageTopic(
            name="management",
            description=f"Key management personnel, leadership stability, succession planning{suffix}",
            min_sources=1,
            sample_queries=[
                f"{company_name or 'company'} CEO management team",
                f"{company_name or 'company'} executive turnover",
            ],
        ),
        CoverageTopic(
            name="controversy",
            description=f"Controversies, scandals, negative press, reputational risks{suffix}",
            min_sources=1,
            sample_queries=[
                f"{company_name or 'company'} controversy scandal",
                f"{company_name or 'company'} negative news criticism",
            ],
        ),
        CoverageTopic(
            name="competition",
            description=f"Competitive landscape, peer comparison, industry trends{suffix}",
            min_sources=2,
            sample_queries=[
                f"{company_name or 'company'} competitors peers comparison",
                f"{company_name or 'company'} industry trends outlook",
            ],
        ),
        CoverageTopic(
            name="environmental",
            description=f"ESG practices, environmental risks, sustainability, climate impact{suffix}",
            min_sources=1,
            sample_queries=[
                f"{company_name or 'company'} ESG environmental sustainability",
                f"{company_name or 'company'} carbon emissions climate risk",
            ],
        ),
    ]

    return topics
