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


# --- Claim data model --------------------------------------------------------
# Canonical claim column names the engine and converter rely on. Defined here so
# the LLM extractor, validator, and converter all agree on the claim schema.
CLAIM_PROCEDURE_FIELD = "procedure_code"
CLAIM_DIAGNOSIS_FIELD = "diagnosis_code"
CLAIM_AGE_FIELD = "patient_age"
CLAIM_UNITS_FIELD = "units"


class PolicyRule(BaseModel):
    """Flat, LLM-facing representation of a drafted policy rule.

    This is the shape the LLM emits via structured JSON output. It uses only
    concrete types (str / int / list[str]) so it maps cleanly onto Gemini's
    response schema, unlike the engine's generic `Condition.value: Any`. A
    converter (`llm_extractor.policy_rule_to_rule`) turns it into a `Rule` the
    deterministic engine can run.
    """

    rule_id: str = Field(..., description="Short identifier, e.g. 'CMS-DEXA-001'.")
    title: str = Field(..., description="Human-readable rule title.")
    description: str = Field(default="", description="One-sentence summary of the rule.")

    service_codes: List[str] = Field(
        default_factory=list,
        description="CPT/HCPCS procedure codes this rule governs.",
    )
    diagnosis_codes: List[str] = Field(
        default_factory=list,
        description="ICD-10 diagnosis codes that are approved indications.",
    )
    min_patient_age: Optional[int] = Field(
        default=None, description="Minimum covered patient age, or null if none."
    )
    max_patient_age: Optional[int] = Field(
        default=None, description="Maximum covered patient age, or null if none."
    )
    exclusion_flag_fields: List[str] = Field(
        default_factory=list,
        description="Claim field names that exclude coverage when their value is 'Y'.",
    )
    required_documentation_fields: List[str] = Field(
        default_factory=list,
        description="Claim field names that must be present (documentation requirements).",
    )
    max_units: Optional[int] = Field(
        default=None, description="Maximum allowed units per claim, or null if none."
    )
    source_evidence: str = Field(
        default="",
        description="Verbatim snippet of the policy text this rule was drawn from.",
    )


class RulePatch(BaseModel):
    """A structured, partial modification to a PolicyRule.

    Proposed by the LLM from a natural-language reviewer instruction. It is a
    *patch*, not a rewrite: only the listed operations are applied. By design it
    has NO field for `rule_id` or `source_evidence`, so a patch can never change
    the rule's identity or its policy provenance. List fields default to empty
    (no-op); `set_*` fields default to None (no change).
    """

    summary: str = Field(
        default="",
        description="Plain-language summary of the change the patch makes.",
    )
    add_service_codes: List[str] = Field(
        default_factory=list, description="Service codes (CPT/HCPCS) to add."
    )
    remove_service_codes: List[str] = Field(
        default_factory=list, description="Service codes to remove."
    )
    add_diagnosis_codes: List[str] = Field(
        default_factory=list, description="Diagnosis codes (ICD-10) to add."
    )
    remove_diagnosis_codes: List[str] = Field(
        default_factory=list, description="Diagnosis codes to remove."
    )
    set_min_patient_age: Optional[int] = Field(
        default=None, description="New minimum patient age, or null for no change."
    )
    set_max_patient_age: Optional[int] = Field(
        default=None, description="New maximum patient age, or null for no change."
    )
    set_max_units: Optional[int] = Field(
        default=None, description="New maximum units/visit limit, or null for no change."
    )
    add_exclusion_flag_fields: List[str] = Field(
        default_factory=list, description="Exclusion flag claim fields to add."
    )
    remove_exclusion_flag_fields: List[str] = Field(
        default_factory=list, description="Exclusion flag claim fields to remove."
    )
    add_required_documentation_fields: List[str] = Field(
        default_factory=list, description="Documentation claim fields to add."
    )
    remove_required_documentation_fields: List[str] = Field(
        default_factory=list, description="Documentation claim fields to remove."
    )
    set_title: Optional[str] = Field(
        default=None, description="New rule title, or null for no change."
    )
    set_description: Optional[str] = Field(
        default=None, description="New rule description, or null for no change."
    )
