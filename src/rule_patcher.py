"""Natural-language rule revision via a structured RulePatch.

A reviewer types an instruction like "Add 97116 as a covered service code" or
"Change visit limit from 12 to 10". The LLM proposes a structured `RulePatch`
(NOT a rewritten rule). Deterministic Python then applies the patch, the result is
re-validated, a before/after diff is shown, and only on human approval is the
updated rule saved.

Guarantees:
- A patch can never change `rule_id` or `source_evidence` - `RulePatch` has no such
  fields, and `apply_patch` force-restores both from the original rule.
- Nothing here is applied automatically; the app gates application behind approval.
"""

from __future__ import annotations

import os
import re
from typing import List, Sequence

from .schemas import PolicyRule, RulePatch

DEFAULT_MODEL = "gemini-2.5-flash"

# Fields shown in the before/after diff, in display order.
_DIFF_FIELDS = [
    "title",
    "description",
    "service_codes",
    "diagnosis_codes",
    "min_patient_age",
    "max_patient_age",
    "exclusion_flag_fields",
    "required_documentation_fields",
    "max_units",
]

_PATCH_SYSTEM_INSTRUCTION = (
    "You revise a structured claim-review rule based on a reviewer's natural-language "
    "instruction. Return a PARTIAL patch describing only the changes - never a full "
    "rewritten rule. Only fill the patch fields that the instruction asks to change; "
    "leave everything else at its default (empty list or null). You cannot change the "
    "rule's identifier or its source policy evidence. Always set a short 'summary'."
)


def _api_key() -> str:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""


def active_mode(mode: str = "auto") -> str:
    if mode == "auto":
        return "api" if _api_key() else "mock"
    return mode


# --- Mock proposal ---------------------------------------------------------
_CPT_HCPCS_RE = re.compile(r"\b(?:[A-Za-z]\d{4}|\d{5})\b")
# Letter + digit + alnum, with an optional dotted extension (ICD-10-ish). The
# trailing \b prevents matching a prefix of a longer HCPCS code like G0121.
_ICD_RE = re.compile(r"\b[A-Za-z]\d[0-9A-Za-z](?:\.[0-9A-Za-z]{1,4})?\b")


def _mock_patch(instruction: str) -> RulePatch:
    """Deterministic, heuristic patch parser for offline/demo use.

    Handles the common documented cases (add/remove service or diagnosis codes,
    set unit/visit limit, set patient age). For anything it cannot interpret it
    returns an empty patch with an honest summary.
    """
    text = instruction.lower()
    removing = any(w in text for w in ("remove", "delete", "drop", "no longer"))

    service_codes = _CPT_HCPCS_RE.findall(instruction)
    icd_codes = [c for c in _ICD_RE.findall(instruction)
                 if not re.fullmatch(r"\d{5}", c) and c.upper() not in
                 {s.upper() for s in service_codes}]

    is_service = any(k in text for k in ("service", "cpt", "procedure", "hcpcs", "code"))
    is_diag = any(k in text for k in ("diagnos", "icd", "indication"))
    is_units = any(k in text for k in ("unit", "visit", "limit", "frequency", "per claim"))
    is_age = "age" in text

    # "from 12 to 10" / "to 10" -> target is the number after the last 'to'.
    to_nums = re.findall(r"\bto\s+(\d+)", text)
    other_nums = re.findall(r"\b(\d+)\b", text)
    target = int(to_nums[-1]) if to_nums else (int(other_nums[-1]) if other_nums else None)

    kwargs: dict = {}
    changes: List[str] = []

    if service_codes and (is_service or not is_diag):
        key = "remove_service_codes" if removing else "add_service_codes"
        kwargs[key] = service_codes
        changes.append(f"{'remove' if removing else 'add'} service code(s) {service_codes}")

    if icd_codes and (is_diag or not is_service):
        key = "remove_diagnosis_codes" if removing else "add_diagnosis_codes"
        kwargs[key] = icd_codes
        changes.append(f"{'remove' if removing else 'add'} diagnosis code(s) {icd_codes}")

    if is_units and target is not None:
        kwargs["set_max_units"] = target
        changes.append(f"set max units to {target}")
    elif is_age and target is not None:
        kwargs["set_min_patient_age"] = target
        changes.append(f"set minimum patient age to {target}")

    if changes:
        summary = "; ".join(changes)
    else:
        summary = (
            "Mock mode could not interpret this instruction. Set GEMINI_API_KEY to use "
            "the real LLM for free-form revisions."
        )
    return RulePatch(summary=summary, **kwargs)


def _propose_via_api(
    instruction: str, current: PolicyRule, claim_columns: Sequence[str], model: str
) -> RulePatch:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_api_key())
    prompt = (
        f"Current rule (JSON):\n{current.model_dump_json(indent=2)}\n\n"
        f"Available claim fields: {', '.join(claim_columns)}\n\n"
        f"Reviewer instruction:\n\"{instruction.strip()}\"\n\n"
        "Produce a partial RulePatch with only the requested changes."
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_PATCH_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=RulePatch,
            temperature=0,
        ),
    )
    return RulePatch.model_validate_json(response.text)


def propose_patch(
    instruction: str,
    current: PolicyRule,
    claim_columns: Sequence[str],
    mode: str = "auto",
    model: str = DEFAULT_MODEL,
) -> RulePatch:
    """Propose a structured patch for `instruction` against `current`."""
    if active_mode(mode) == "api":
        return _propose_via_api(instruction, current, claim_columns, model)
    return _mock_patch(instruction)


def patch_has_changes(patch: RulePatch) -> bool:
    """True if the patch would change anything."""
    data = patch.model_dump(exclude={"summary"})
    return any(v for v in data.values())


def _merge(existing: Sequence[str], add: Sequence[str], remove: Sequence[str]) -> List[str]:
    result = list(existing)
    for code in add:
        if code not in result:
            result.append(code)
    remove_set = set(remove)
    return [c for c in result if c not in remove_set]


def apply_patch(current: PolicyRule, patch: RulePatch) -> PolicyRule:
    """Apply a patch to a PolicyRule, returning a new rule.

    `rule_id` and `source_evidence` are always preserved from `current`.
    """
    data = current.model_dump()

    data["service_codes"] = _merge(
        current.service_codes, patch.add_service_codes, patch.remove_service_codes
    )
    data["diagnosis_codes"] = _merge(
        current.diagnosis_codes, patch.add_diagnosis_codes, patch.remove_diagnosis_codes
    )
    data["exclusion_flag_fields"] = _merge(
        current.exclusion_flag_fields,
        patch.add_exclusion_flag_fields,
        patch.remove_exclusion_flag_fields,
    )
    data["required_documentation_fields"] = _merge(
        current.required_documentation_fields,
        patch.add_required_documentation_fields,
        patch.remove_required_documentation_fields,
    )

    if patch.set_min_patient_age is not None:
        data["min_patient_age"] = patch.set_min_patient_age
    if patch.set_max_patient_age is not None:
        data["max_patient_age"] = patch.set_max_patient_age
    if patch.set_max_units is not None:
        data["max_units"] = patch.set_max_units
    if patch.set_title is not None:
        data["title"] = patch.set_title
    if patch.set_description is not None:
        data["description"] = patch.set_description

    # Immutable provenance - never patchable.
    data["rule_id"] = current.rule_id
    data["source_evidence"] = current.source_evidence

    return PolicyRule.model_validate(data)


def diff_policy_rules(before: PolicyRule, after: PolicyRule) -> List[dict]:
    """Return a list of {field, before, after} for fields that changed."""
    b = before.model_dump()
    a = after.model_dump()
    rows = []
    for field in _DIFF_FIELDS:
        if b.get(field) != a.get(field):
            rows.append({"field": field, "before": b.get(field), "after": a.get(field)})
    return rows
