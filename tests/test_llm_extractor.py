"""Tests for the LLM extractor (mock mode) and the PolicyRule -> Rule converter."""

from src.llm_extractor import (
    active_mode,
    extract_rule,
    policy_rule_to_rule,
)
from src.rule_engine import evaluate
from src.schemas import Outcome, PolicyRule
from src.validator import validate_policy_rule

CLAIM_COLUMNS = [
    "claim_id", "patient_age", "procedure_code", "diagnosis_code",
    "prior_ldct_within_12mo", "shared_decision_visit", "units",
]

PASS_CLAIM = {
    "claim_id": "T1",
    "patient_age": 60,
    "procedure_code": "71271",
    "diagnosis_code": "Z87.891",
    "prior_ldct_within_12mo": "N",
    "shared_decision_visit": "SDM-1",
    "units": 1,
}


def test_mock_mode_needs_no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert active_mode("auto") == "mock"
    draft = extract_rule("any policy text", CLAIM_COLUMNS, mode="auto")
    assert isinstance(draft, PolicyRule)
    assert draft.service_codes == ["71271"]


def test_mock_draft_is_valid():
    draft = extract_rule("policy", CLAIM_COLUMNS, mode="mock")
    report = validate_policy_rule(draft, CLAIM_COLUMNS)
    assert report.is_valid, [i.message for i in report.errors()]


def test_converter_produces_runnable_rule():
    draft = extract_rule("policy", CLAIM_COLUMNS, mode="mock")
    rule = policy_rule_to_rule(draft, version=2)
    assert rule.version == 2
    assert rule.source_evidence

    result = evaluate(rule, PASS_CLAIM)
    assert result.outcome == Outcome.PASS


def test_converted_rule_matches_outcomes():
    rule = policy_rule_to_rule(extract_rule("policy", CLAIM_COLUMNS, mode="mock"))

    too_young = {**PASS_CLAIM, "claim_id": "T2", "patient_age": 45}
    assert evaluate(rule, too_young).outcome == Outcome.FAIL

    missing_doc = {**PASS_CLAIM, "claim_id": "T3", "shared_decision_visit": ""}
    assert evaluate(rule, missing_doc).outcome == Outcome.NEEDS_REVIEW

    other_proc = {**PASS_CLAIM, "claim_id": "T4", "procedure_code": "99213"}
    assert evaluate(rule, other_proc).outcome == Outcome.NOT_APPLICABLE
