"""Pydantic models for claim-review rules and evaluation results.

These models intentionally mirror the rule vocabulary used in the project report
(indications / exclusions / documentation requirements / timing limits / source
evidence). In v1 a rule is hardcoded; in later phases an LLM will draft a `Rule`
object in exactly this shape, so the structured draft visibly matches the policy.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class Operator(str, Enum):
    """Deterministic comparison operators supported by the rule engine.

    Kept intentionally small - only what the sample rule needs. Extend when a
    real extracted rule requires more.
    """

    EQ = "eq"            # field == value
    IN = "in"            # field in value (value is a list)
    GTE = "gte"          # field >= value
    LTE = "lte"          # field <= value
    BETWEEN = "between"  # value[0] <= field <= value[1] (inclusive)
    PRESENT = "present"  # field is present and non-empty (documentation checks)


class Outcome(str, Enum):
    """Final claim decision. Produced only by deterministic Python."""

    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Condition(BaseModel):
    """A single testable check against one claim field."""

    field: str = Field(..., description="Claim column this condition inspects.")
    op: Operator
    value: Any = Field(
        default=None,
        description="Comparison operand: scalar, list (for `in`), or [low, high] "
        "(for `between`). Ignored for `present`.",
    )
    description: str = Field(
        default="",
        description="Plain-language statement of what this condition requires.",
    )


class Rule(BaseModel):
    """An executable claim-review rule.

    Condition groups map to the report's policy vocabulary. The engine evaluates
    them with a fixed precedence (see rule_engine.evaluate).
    """

    rule_id: str
    version: int = 1
    title: str
    description: str = ""

    # Scope: which claims this rule governs at all.
    applies_when: List[Condition] = Field(default_factory=list)
    # Coverage criteria that must hold for a PASS.
    indications: List[Condition] = Field(default_factory=list)
    # If any holds, the claim FAILs.
    exclusions: List[Condition] = Field(default_factory=list)
    # Required documentation/fields; absence -> NEEDS_REVIEW.
    documentation_requirements: List[Condition] = Field(default_factory=list)
    # Frequency / units / date limits.
    timing_limits: List[Condition] = Field(default_factory=list)

    # Traceability: the policy text this rule was derived from.
    source_evidence: str = ""


class EvalResult(BaseModel):
    """Outcome of evaluating one rule against one claim."""

    claim_id: str
    rule_id: str
    rule_version: int
    outcome: Outcome
    reasons: List[str] = Field(default_factory=list)
    evidence: str = ""
    timestamp: Optional[str] = None
