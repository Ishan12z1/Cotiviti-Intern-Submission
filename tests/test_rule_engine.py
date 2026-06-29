"""Unit tests for the deterministic rule engine and audit logger."""

import copy

from src.audit_logger import log_results, read_log
from src.rule_engine import evaluate, run_batch
from src.sample_rule import SAMPLE_RULE
from src.schemas import Outcome

# A claim that satisfies every criterion.
BASE_PASS_CLAIM = {
    "claim_id": "T-PASS",
    "patient_age": 70,
    "procedure_code": "77080",
    "diagnosis_code": "M81.0",
    "prior_dexa_within_24mo": "N",
    "physician_order": "ORD-1",
    "units": 1,
}


def _claim(**overrides):
    claim = copy.deepcopy(BASE_PASS_CLAIM)
    claim.update(overrides)
    return claim


def test_satisfying_claim_passes():
    result = evaluate(SAMPLE_RULE, _claim())
    assert result.outcome == Outcome.PASS
    assert result.reasons
    assert result.evidence  # source evidence carried through


def test_age_out_of_range_fails():
    result = evaluate(SAMPLE_RULE, _claim(claim_id="T-AGE", patient_age=54))
    assert result.outcome == Outcome.FAIL


def test_disallowed_diagnosis_fails():
    result = evaluate(SAMPLE_RULE, _claim(claim_id="T-DX", diagnosis_code="J45.909"))
    assert result.outcome == Outcome.FAIL


def test_units_over_limit_fails():
    result = evaluate(SAMPLE_RULE, _claim(claim_id="T-UNITS", units=2))
    assert result.outcome == Outcome.FAIL


def test_exclusion_fails():
    result = evaluate(SAMPLE_RULE, _claim(claim_id="T-EXCL", prior_dexa_within_24mo="Y"))
    assert result.outcome == Outcome.FAIL
    assert any("Exclusion" in r for r in result.reasons)


def test_missing_documentation_needs_review():
    result = evaluate(SAMPLE_RULE, _claim(claim_id="T-DOC", physician_order=""))
    assert result.outcome == Outcome.NEEDS_REVIEW
    assert any("physician_order" in r for r in result.reasons)


def test_missing_age_needs_review_not_crash():
    result = evaluate(SAMPLE_RULE, _claim(claim_id="T-NOAGE", patient_age=None))
    assert result.outcome == Outcome.NEEDS_REVIEW


def test_age_lower_boundary_passes():
    result = evaluate(SAMPLE_RULE, _claim(claim_id="T-65", patient_age=65))
    assert result.outcome == Outcome.PASS


def test_age_upper_boundary_passes():
    result = evaluate(SAMPLE_RULE, _claim(claim_id="T-120", patient_age=120))
    assert result.outcome == Outcome.PASS


def test_different_procedure_not_applicable():
    result = evaluate(SAMPLE_RULE, _claim(claim_id="T-NA", procedure_code="99213"))
    assert result.outcome == Outcome.NOT_APPLICABLE


def test_every_result_has_reasons_and_evidence():
    claims = [
        _claim(),
        _claim(patient_age=54),
        _claim(physician_order=""),
        _claim(procedure_code="99213"),
    ]
    for result in run_batch(SAMPLE_RULE, claims):
        assert result.reasons, f"no reasons for {result.claim_id}"
        assert result.evidence


def test_audit_log_round_trip(tmp_path):
    log_path = str(tmp_path / "audit.jsonl")
    results = run_batch(SAMPLE_RULE, [_claim(), _claim(patient_age=54)])
    written = log_results(results, path=log_path)
    assert written == 2

    entries = read_log(log_path)
    assert len(entries) == 2
    assert entries[0]["rule_id"] == SAMPLE_RULE.rule_id
    assert entries[0]["outcome"] in {o.value for o in Outcome}
