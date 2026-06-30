"""Tests for natural-language rule revision (RulePatch)."""

from src.llm_extractor import extract_rule
from src.rule_patcher import (
    apply_patch,
    diff_policy_rules,
    patch_has_changes,
    propose_patch,
)
from src.schemas import RulePatch

CLAIM_COLUMNS = [
    "claim_id", "patient_age", "procedure_code", "diagnosis_code",
    "prior_dexa_within_24mo", "physician_order", "units",
]


def _current():
    return extract_rule("policy", CLAIM_COLUMNS, mode="mock")


def test_mock_add_service_code():
    patch = propose_patch("Add 97116 as a covered service code", _current(), CLAIM_COLUMNS, mode="mock")
    assert "97116" in patch.add_service_codes
    assert patch_has_changes(patch)


def test_mock_change_visit_limit():
    patch = propose_patch("Change visit limit from 12 to 10", _current(), CLAIM_COLUMNS, mode="mock")
    assert patch.set_max_units == 10


def test_mock_remove_service_code():
    patch = propose_patch("Remove 77080 from the service codes", _current(), CLAIM_COLUMNS, mode="mock")
    assert "77080" in patch.remove_service_codes


def test_apply_add_service_code():
    current = _current()
    patched = apply_patch(current, RulePatch(add_service_codes=["97116"]))
    assert "97116" in patched.service_codes
    assert "77080" in patched.service_codes  # original preserved


def test_apply_set_max_units():
    patched = apply_patch(_current(), RulePatch(set_max_units=3))
    assert patched.max_units == 3


def test_patch_cannot_change_rule_id_or_source_evidence():
    current = _current()
    # Even if a malicious dict tried, the model has no such fields; and apply_patch
    # force-restores them. Verify they are unchanged after a real patch.
    patched = apply_patch(current, RulePatch(add_service_codes=["97116"]))
    assert patched.rule_id == current.rule_id
    assert patched.source_evidence == current.source_evidence


def test_diff_reports_only_changed_fields():
    current = _current()
    patched = apply_patch(current, RulePatch(add_service_codes=["97116"], set_max_units=2))
    rows = diff_policy_rules(current, patched)
    changed = {r["field"] for r in rows}
    assert changed == {"service_codes", "max_units"}


def test_empty_patch_has_no_changes():
    assert not patch_has_changes(RulePatch(summary="nothing"))
