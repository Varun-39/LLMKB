"""
RecommendationCard schema (P4/E1) — the response model for the alert path,
replacing src.server.AlertResponse.

D4's structural guarantee (R2) is enforced here via a pydantic validator: it
is impossible to construct a RecommendationCard with a non-null
recommended_action and empty evidence, or with confidence.band == 'none' and
a non-null recommended_action. This is a correctness invariant, not a config
toggle — attempting either raises a ValidationError at construction time.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from src.confidence import Confidence as ConfidenceResult


class DetectedIssue(BaseModel):
    error: str
    component: str
    host: str
    environment: str
    raw_message: str


class Evidence(BaseModel):
    doc_id: str
    doc_type: str
    section: str
    snippet: str
    why_matched: str
    signal_scores: dict[str, float]


class Confidence(BaseModel):
    band: str  # 'high' | 'medium' | 'low' | 'none'
    score: Optional[float] = None
    prior_success_n: int
    prior_total_n: int
    cohort_size: int
    excluded_unknown_n: int

    @classmethod
    def from_result(cls, result: ConfidenceResult) -> "Confidence":
        return cls(
            band=result.band,
            score=result.score,
            prior_success_n=result.prior_success_n,
            prior_total_n=result.prior_total_n,
            cohort_size=result.cohort_size,
            excluded_unknown_n=result.excluded_unknown_n,
        )


class Risk(BaseModel):
    level: str  # from the recommended runbook's own risk_level frontmatter, never invented
    note: Optional[str] = None


class OpsDecision(BaseModel):
    decision: str  # Accept | Edit | Reject | Escalate | Create new KB signal
    actor: str
    timestamp: datetime
    comment: Optional[str] = None
    edited_action: Optional[str] = None


class RecommendationCard(BaseModel):
    correlation_id: str
    signature_id: str
    error_family: Optional[str] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_version: Optional[str] = None  # null when generation disabled (E3) — card is self-describing
    detected_issue: DetectedIssue
    recommended_action: Optional[str] = None
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: Confidence
    risk: Risk
    do_not_do: Optional[str] = None
    escalate_if: Optional[str] = None
    ops_decision: Optional[OpsDecision] = None

    @model_validator(mode="after")
    def _enforce_grounding_invariants(self) -> "RecommendationCard":
        if self.recommended_action is not None and not self.evidence:
            raise ValueError(
                "R2 violation: recommended_action is set but evidence is empty — "
                "a recommendation must always trace to retrieved evidence, never a guess."
            )
        if self.confidence.band == "none" and self.recommended_action is not None:
            raise ValueError(
                "R2 violation: confidence.band is 'none' but recommended_action is not "
                "null — band='none' must produce no action, never a guess."
            )
        return self
