"""Deterministic rule engine.

This module makes the FINAL claim decision. It contains no LLM calls and no
Streamlit imports, so it can be unit-tested headlessly and reused unchanged when
the LLM drafting layer is added.

Evaluation precedence (see project plan):
  1. If the rule does not apply to the claim        -> NOT_APPLICABLE
  2. If any needed field is missing/unparseable     -> NEEDS_REVIEW
  3. If any exclusion holds                          -> FAIL
  4. If all indications + timing limits hold         -> PASS, else FAIL

The engine never guesses: anything it cannot determine becomes NEEDS_REVIEW.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Mapping, Tuple

from .schemas import Condition, EvalResult, Operator, Outcome, Rule

# Per-condition check results.
_HOLD = "hold"        # condition is satisfied
_VIOLATE = "violate"  # condition is definitively not satisfied
_MISSING = "missing"  # field absent/unparseable -> cannot decide


def _is_missing(value: Any) -> bool:
    """True if a claim value is absent, NaN, or blank."""
    if value is None:
        return True
    # NaN (from pandas) is the only value not equal to itself.
    if isinstance(value, float) and value != value:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _to_number(value: Any):
    """Coerce a claim value to float, or None if it is not numeric."""
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str:
    """Normalize a code/string value for equality comparison.

    Handles pandas reading numeric-looking codes as ints/floats (e.g. 77080 or
    77080.0) so they still compare equal to the string "77080".
    """
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _check(cond: Condition, claim: Mapping[str, Any]) -> Tuple[str, str]:
    """Evaluate one condition. Returns (status, human-readable reason)."""
    raw = claim.get(cond.field)

    if cond.op == Operator.PRESENT:
        if _is_missing(raw):
            return _MISSING, f"Missing required field '{cond.field}': {cond.description}"
        return _HOLD, f"{cond.description} (found '{_as_text(raw)}')"

    if _is_missing(raw):
        return _MISSING, f"Missing field '{cond.field}' needed to check: {cond.description}"

    if cond.op in (Operator.GTE, Operator.LTE, Operator.BETWEEN):
        num = _to_number(raw)
        if num is None:
            return _MISSING, f"Field '{cond.field}' is not a valid number ({raw!r})"
        if cond.op == Operator.GTE:
            ok = num >= float(cond.value)
        elif cond.op == Operator.LTE:
            ok = num <= float(cond.value)
        else:  # BETWEEN, inclusive
            low, high = cond.value
            ok = float(low) <= num <= float(high)
        return (_HOLD, cond.description) if ok else (
            _VIOLATE, f"{cond.description} (got {_as_text(raw)})")

    if cond.op == Operator.EQ:
        ok = _as_text(raw) == _as_text(cond.value)
        return (_HOLD, cond.description) if ok else (
            _VIOLATE, f"{cond.description} (got '{_as_text(raw)}')")

    if cond.op == Operator.IN:
        allowed = [_as_text(v) for v in (cond.value or [])]
        ok = _as_text(raw) in allowed
        return (_HOLD, cond.description) if ok else (
            _VIOLATE, f"{cond.description} (got '{_as_text(raw)}')")

    # Unknown operator -> never guess.
    return _MISSING, f"Unsupported operator '{cond.op}' for field '{cond.field}'"


def evaluate(rule: Rule, claim: Mapping[str, Any]) -> EvalResult:
    """Evaluate a single claim against a rule and return a decision."""
    claim_id = str(claim.get("claim_id", "UNKNOWN"))
    timestamp = datetime.now(timezone.utc).isoformat()

    def result(outcome: Outcome, reasons: List[str]) -> EvalResult:
        return EvalResult(
            claim_id=claim_id,
            rule_id=rule.rule_id,
            rule_version=rule.version,
            outcome=outcome,
            reasons=reasons,
            evidence=rule.source_evidence,
            timestamp=timestamp,
        )

    # 1. Scope: does this rule apply at all?
    for cond in rule.applies_when:
        status, reason = _check(cond, claim)
        if status != _HOLD:
            return result(
                Outcome.NOT_APPLICABLE,
                [f"Rule {rule.rule_id} does not apply to this claim: {reason}"],
            )

    # 2. Completeness: any needed field missing/unparseable -> NEEDS_REVIEW.
    checks = (
        rule.documentation_requirements
        + rule.indications
        + rule.timing_limits
        + rule.exclusions
    )
    missing = [reason for cond in checks
               for status, reason in [_check(cond, claim)] if status == _MISSING]
    if missing:
        return result(Outcome.NEEDS_REVIEW, missing)

    # 3. Exclusions: any that holds -> FAIL.
    excluded = [reason for cond in rule.exclusions
                for status, reason in [_check(cond, claim)] if status == _HOLD]
    if excluded:
        return result(Outcome.FAIL,
                      [f"Exclusion applies: {r}" for r in excluded])

    # 4. Indications + timing limits: all must hold for PASS.
    violations = []
    satisfied = []
    for cond in rule.indications + rule.timing_limits:
        status, reason = _check(cond, claim)
        (violations if status == _VIOLATE else satisfied).append(reason)

    if violations:
        return result(Outcome.FAIL,
                      [f"Criterion not met: {r}" for r in violations])

    return result(
        Outcome.PASS,
        [f"Met: {r}" for r in satisfied] or ["All criteria met."],
    )


def run_batch(rule: Rule, claims) -> List[EvalResult]:
    """Evaluate every claim in a pandas DataFrame (or iterable of mappings)."""
    if hasattr(claims, "to_dict"):
        records = claims.to_dict(orient="records")
    else:
        records = list(claims)
    return [evaluate(rule, record) for record in records]
