"""Validation of LLM-drafted policy rules.

The LLM may only *propose* a rule. Before a human is allowed to approve it - and
long before the deterministic engine runs it - the draft passes these checks:

  1. valid schema             - parses into the PolicyRule model
  2. source evidence exists   - traceability back to the policy text
  3. service code format       - CPT/HCPCS look right
  4. diagnosis prefix format   - ICD-10 codes look right
  5. required claim fields exist - every field the rule references is a real claim column

This is the guardrail that keeps malformed or ungrounded LLM output from reaching
the engine.
"""

from __future__ import annotations

import re
from typing import Any, List, Mapping, Sequence, Union

from pydantic import BaseModel, ValidationError

from .schemas import (
    CLAIM_AGE_FIELD,
    CLAIM_DIAGNOSIS_FIELD,
    CLAIM_PROCEDURE_FIELD,
    CLAIM_UNITS_FIELD,
    PolicyRule,
)

# CPT: 5 digits (e.g. 77080). HCPCS Level II: 1 letter + 4 digits (e.g. G0121).
_CPT_RE = re.compile(r"^\d{5}$")
_HCPCS_RE = re.compile(r"^[A-Z]\d{4}$")
# ICD-10-CM: a letter (not U placeholder slots aside), a digit, an alphanumeric,
# then an optional dotted extension of up to 4 alphanumerics.
_ICD10_RE = re.compile(r"^[A-TV-Z]\d[0-9A-Z](\.[0-9A-Z]{1,4})?$")

LEVEL_OK = "ok"
LEVEL_ERROR = "error"


class ValidationIssue(BaseModel):
    """One check's outcome."""

    check: str
    level: str  # "ok" | "error"
    message: str


class ValidationReport(BaseModel):
    """Aggregate result of validating a drafted rule."""

    is_valid: bool
    issues: List[ValidationIssue]

    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.level == LEVEL_ERROR]


def validate_policy_rule(
    data: Union[PolicyRule, Mapping[str, Any]],
    claim_columns: Sequence[str],
) -> ValidationReport:
    """Validate a drafted PolicyRule against schema, formats, and claim columns."""
    issues: List[ValidationIssue] = []

    # 1. Valid schema -------------------------------------------------------
    if isinstance(data, PolicyRule):
        rule = data
    else:
        try:
            rule = PolicyRule.model_validate(data)
        except ValidationError as exc:
            return ValidationReport(
                is_valid=False,
                issues=[
                    ValidationIssue(
                        check="valid schema",
                        level=LEVEL_ERROR,
                        message=f"Draft does not match PolicyRule schema: {exc.error_count()} "
                        f"error(s). First: {exc.errors()[0]['loc']} -> {exc.errors()[0]['msg']}",
                    )
                ],
            )
    issues.append(ValidationIssue(
        check="valid schema", level=LEVEL_OK,
        message="Draft parses into the PolicyRule schema.",
    ))

    # 2. Source evidence exists --------------------------------------------
    if rule.source_evidence and rule.source_evidence.strip():
        issues.append(ValidationIssue(
            check="source evidence exists", level=LEVEL_OK,
            message="Source evidence is present.",
        ))
    else:
        issues.append(ValidationIssue(
            check="source evidence exists", level=LEVEL_ERROR,
            message="Source evidence is empty - rule is not traceable to policy text.",
        ))

    # 3. Service code format -----------------------------------------------
    if not rule.service_codes:
        issues.append(ValidationIssue(
            check="service code format", level=LEVEL_ERROR,
            message="No service codes - rule has nothing to scope to.",
        ))
    else:
        bad = [c for c in rule.service_codes
               if not (_CPT_RE.match(c) or _HCPCS_RE.match(c))]
        if bad:
            issues.append(ValidationIssue(
                check="service code format", level=LEVEL_ERROR,
                message=f"Invalid CPT/HCPCS code(s): {', '.join(bad)}.",
            ))
        else:
            issues.append(ValidationIssue(
                check="service code format", level=LEVEL_OK,
                message=f"All {len(rule.service_codes)} service code(s) well-formed.",
            ))

    # 4. Diagnosis prefix format -------------------------------------------
    if not rule.diagnosis_codes:
        issues.append(ValidationIssue(
            check="diagnosis prefix format", level=LEVEL_OK,
            message="No diagnosis codes to check.",
        ))
    else:
        bad_dx = [c for c in rule.diagnosis_codes if not _ICD10_RE.match(c)]
        if bad_dx:
            issues.append(ValidationIssue(
                check="diagnosis prefix format", level=LEVEL_ERROR,
                message=f"Invalid ICD-10 code(s): {', '.join(bad_dx)}.",
            ))
        else:
            issues.append(ValidationIssue(
                check="diagnosis prefix format", level=LEVEL_OK,
                message=f"All {len(rule.diagnosis_codes)} diagnosis code(s) well-formed.",
            ))

    # 5. Required claim fields exist ---------------------------------------
    columns = set(claim_columns)
    referenced: List[str] = [CLAIM_PROCEDURE_FIELD]
    if rule.diagnosis_codes:
        referenced.append(CLAIM_DIAGNOSIS_FIELD)
    if rule.min_patient_age is not None or rule.max_patient_age is not None:
        referenced.append(CLAIM_AGE_FIELD)
    if rule.max_units is not None:
        referenced.append(CLAIM_UNITS_FIELD)
    referenced.extend(rule.exclusion_flag_fields)
    referenced.extend(rule.required_documentation_fields)

    missing = [f for f in referenced if f not in columns]
    if missing:
        issues.append(ValidationIssue(
            check="required claim fields exist", level=LEVEL_ERROR,
            message=f"Rule references claim field(s) not in the data: {', '.join(missing)}.",
        ))
    else:
        issues.append(ValidationIssue(
            check="required claim fields exist", level=LEVEL_OK,
            message="All referenced claim fields exist in the claim data.",
        ))

    is_valid = all(i.level != LEVEL_ERROR for i in issues)
    return ValidationReport(is_valid=is_valid, issues=issues)
