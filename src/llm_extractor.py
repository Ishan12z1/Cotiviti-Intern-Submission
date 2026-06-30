"""LLM policy-to-rule extractor (Google Gemini) with a deterministic mock mode.

`extract_rule` converts free-text policy into a structured `PolicyRule` using
Gemini's structured JSON output. When no API key is available (or mock mode is
forced) it returns a fixed, deterministic draft so the app and the recorded demo
work offline.

The LLM only *drafts* a rule. The output must still pass `validator.validate_policy_rule`
and a human approval before `policy_rule_to_rule` produces a `Rule` for the engine.
"""

from __future__ import annotations

import os
from typing import List, Sequence

from .schemas import (
    CLAIM_AGE_FIELD,
    CLAIM_DIAGNOSIS_FIELD,
    CLAIM_PROCEDURE_FIELD,
    CLAIM_UNITS_FIELD,
    Condition,
    Operator,
    PolicyRule,
    Rule,
)

DEFAULT_MODEL = "gemini-2.5-flash"

# Claim fields the mock maps policy concepts onto (must exist in the claims CSV).
_EXCLUSION_FIELD = "prior_dexa_within_24mo"
_DOCUMENTATION_FIELD = "physician_order"

_SYSTEM_INSTRUCTION = (
    "You convert healthcare payment/coding policy text into a single structured "
    "claim-review rule. Extract only what the policy states. Use the provided claim "
    "field names when identifying exclusion flags and documentation requirements. "
    "Always include a verbatim source_evidence snippet copied from the policy text. "
    "Do not invent codes or criteria that are not in the policy."
)


def api_key_available() -> bool:
    """True if a Gemini API key is configured in the environment."""
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def active_mode(mode: str = "auto") -> str:
    """Resolve the effective mode ('api' or 'mock') given a requested mode."""
    if mode == "auto":
        return "api" if api_key_available() else "mock"
    return mode


def _mock_policy_rule() -> PolicyRule:
    """Deterministic draft matching data/sample_cms_policy.txt (no API needed)."""
    return PolicyRule(
        rule_id="CMS-DEXA-001",
        title="DEXA Bone Density Screening Coverage",
        description=(
            "Coverage, documentation, and frequency criteria for DEXA bone density "
            "scans (CPT 77080)."
        ),
        service_codes=["77080"],
        diagnosis_codes=["M81.0", "M80.00", "E21.0", "Z78.0"],
        min_patient_age=65,
        max_patient_age=None,
        exclusion_flag_fields=[_EXCLUSION_FIELD],
        required_documentation_fields=[_DOCUMENTATION_FIELD],
        max_units=1,
        source_evidence=(
            "Dual-energy x-ray absorptiometry (DEXA, procedure code 77080) is covered "
            "for beneficiaries who are 65 years of age or older ... A signed physician "
            "order must be on file ... No more than one (1) unit ... per claim ... not "
            "separately covered when a prior DEXA scan has been performed within the "
            "preceding 24 months."
        ),
    )


def _build_prompt(policy_text: str, claim_columns: Sequence[str]) -> str:
    columns = ", ".join(claim_columns)
    return (
        f"Available claim fields (use these exact names): {columns}\n\n"
        f"Policy text:\n\"\"\"\n{policy_text.strip()}\n\"\"\"\n\n"
        "Produce one structured rule for this policy."
    )


def _extract_via_api(
    policy_text: str, claim_columns: Sequence[str], model: str
) -> PolicyRule:
    """Call Gemini with structured JSON output and parse into a PolicyRule."""
    from google import genai  # imported lazily so mock mode needs no dependency
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=_build_prompt(policy_text, claim_columns),
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=PolicyRule,
            temperature=0,
        ),
    )
    return PolicyRule.model_validate_json(response.text)


def extract_rule(
    policy_text: str,
    claim_columns: Sequence[str],
    mode: str = "auto",
    model: str = DEFAULT_MODEL,
) -> PolicyRule:
    """Convert policy text to a drafted PolicyRule.

    mode: 'auto' (API if a key is set, else mock), 'api', or 'mock'.
    """
    if active_mode(mode) == "api":
        return _extract_via_api(policy_text, claim_columns, model)
    return _mock_policy_rule()


def policy_rule_to_rule(pr: PolicyRule, version: int = 1) -> Rule:
    """Convert a (validated, approved) PolicyRule into an engine-ready Rule."""
    applies_when: List[Condition] = [
        Condition(
            field=CLAIM_PROCEDURE_FIELD,
            op=Operator.IN,
            value=list(pr.service_codes),
            description=f"Claim procedure code is one of {pr.service_codes}.",
        )
    ]

    indications: List[Condition] = []
    if pr.min_patient_age is not None or pr.max_patient_age is not None:
        low = pr.min_patient_age if pr.min_patient_age is not None else 0
        high = pr.max_patient_age if pr.max_patient_age is not None else 200
        if pr.min_patient_age is not None and pr.max_patient_age is not None:
            age_desc = f"Patient is between {low} and {high} years old."
        elif pr.min_patient_age is not None:
            age_desc = f"Patient is {low} years or older."
        else:
            age_desc = f"Patient is {high} years or younger."
        indications.append(
            Condition(
                field=CLAIM_AGE_FIELD,
                op=Operator.BETWEEN,
                value=[low, high],
                description=age_desc,
            )
        )
    if pr.diagnosis_codes:
        indications.append(
            Condition(
                field=CLAIM_DIAGNOSIS_FIELD,
                op=Operator.IN,
                value=list(pr.diagnosis_codes),
                description="Diagnosis is an approved indication.",
            )
        )

    exclusions: List[Condition] = [
        Condition(
            field=field,
            op=Operator.EQ,
            value="Y",
            description=f"Exclusion flag '{field}' is set.",
        )
        for field in pr.exclusion_flag_fields
    ]

    documentation_requirements: List[Condition] = [
        Condition(
            field=field,
            op=Operator.PRESENT,
            description=f"Required documentation '{field}' must be present.",
        )
        for field in pr.required_documentation_fields
    ]

    timing_limits: List[Condition] = []
    if pr.max_units is not None:
        timing_limits.append(
            Condition(
                field=CLAIM_UNITS_FIELD,
                op=Operator.LTE,
                value=pr.max_units,
                description=f"At most {pr.max_units} unit(s) per claim.",
            )
        )

    return Rule(
        rule_id=pr.rule_id,
        version=version,
        title=pr.title,
        description=pr.description,
        applies_when=applies_when,
        indications=indications,
        exclusions=exclusions,
        documentation_requirements=documentation_requirements,
        timing_limits=timing_limits,
        source_evidence=pr.source_evidence,
    )
