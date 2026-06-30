"""Tests for the policy-rule validator."""

import copy

from src.validator import validate_policy_rule

CLAIM_COLUMNS = [
    "claim_id", "patient_age", "procedure_code", "diagnosis_code",
    "prior_ldct_within_12mo", "shared_decision_visit", "units",
]

VALID_DRAFT = {
    "rule_id": "CMS-LDCT-001",
    "title": "Lung Cancer Screening Coverage",
    "description": "LDCT lung cancer screening coverage criteria.",
    "service_codes": ["71271"],
    "diagnosis_codes": [],
    "min_patient_age": 50,
    "max_patient_age": 77,
    "exclusion_flag_fields": ["prior_ldct_within_12mo"],
    "required_documentation_fields": ["shared_decision_visit"],
    "max_units": 1,
    "source_evidence": "LDCT (71271) covered annually for beneficiaries aged 50 to 77...",
}


def _draft(**overrides):
    d = copy.deepcopy(VALID_DRAFT)
    d.update(overrides)
    return d


def test_valid_draft_passes():
    report = validate_policy_rule(_draft(), CLAIM_COLUMNS)
    assert report.is_valid, [i.message for i in report.errors()]


def test_missing_source_evidence_fails():
    report = validate_policy_rule(_draft(source_evidence="  "), CLAIM_COLUMNS)
    assert not report.is_valid
    assert any(i.check == "source evidence exists" for i in report.errors())


def test_bad_service_code_fails():
    report = validate_policy_rule(_draft(service_codes=["7708"]), CLAIM_COLUMNS)
    assert not report.is_valid
    assert any(i.check == "service code format" for i in report.errors())


def test_hcpcs_service_code_passes():
    report = validate_policy_rule(_draft(service_codes=["G0296"]), CLAIM_COLUMNS)
    assert report.is_valid, [i.message for i in report.errors()]


def test_bad_diagnosis_code_fails():
    report = validate_policy_rule(_draft(diagnosis_codes=["123.4"]), CLAIM_COLUMNS)
    assert not report.is_valid
    assert any(i.check == "diagnosis prefix format" for i in report.errors())


def test_unknown_claim_field_fails():
    report = validate_policy_rule(
        _draft(required_documentation_fields=["nonexistent_field"]), CLAIM_COLUMNS
    )
    assert not report.is_valid
    assert any(i.check == "required claim fields exist" for i in report.errors())


def test_schema_error_short_circuits():
    bad = _draft(service_codes="71271")  # should be a list, not a str
    report = validate_policy_rule(bad, CLAIM_COLUMNS)
    assert not report.is_valid
    assert any(i.check == "valid schema" for i in report.errors())
