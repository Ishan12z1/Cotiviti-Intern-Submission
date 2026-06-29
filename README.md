# Policy-to-Rule Claims Compliance Assistant

A proof of concept for the Cotiviti AI/ML intern assessment (topic: *Content
Management in Healthcare — converting written policy into executable claim rules*).

**Core idea:** policy text is written for humans, but claim review needs structured,
testable, auditable logic. In the full vision an LLM *drafts* a structured rule and a
human *approves* it — but **the final claim decision is always made by deterministic
Python**, with a plain-language explanation, source policy evidence, and an audit trail.

> **v1 (this version) is the deterministic core.** It runs a hardcoded, "approved"
> sample rule over synthetic claims and shows PASS / FAIL / NEEDS_REVIEW /
> NOT_APPLICABLE. LLM rule drafting and the human-approval UI are planned for a later
> phase (see *Roadmap*). No real PHI — synthetic data only.

## What it does
- Loads a structured rule (`CMS-DEXA-001`, a synthetic CMS-style DEXA coverage policy).
- Evaluates synthetic claims deterministically with a fixed precedence:
  1. Rule out of scope → **NOT_APPLICABLE**
  2. A needed field missing/unparseable → **NEEDS_REVIEW**
  3. An exclusion applies → **FAIL**
  4. All coverage criteria + limits met → **PASS**, otherwise **FAIL**
- Writes every decision to an append-only JSONL audit log.
- Displays results, reasons, source evidence, and the audit trail in Streamlit.

The `NEEDS_REVIEW`-on-missing-documentation case directly illustrates the report's lead
statistic on improper payments tied to insufficient documentation.

## Project layout
```
app.py                      Streamlit UI
src/schemas.py              Pydantic models (Condition, Rule, EvalResult)
src/sample_rule.py          Hardcoded sample rule (stands in for an LLM draft)
src/rule_engine.py          Deterministic engine (no LLM, no Streamlit)
src/audit_logger.py         Append-only JSONL audit log
data/synthetic_claims.csv   Synthetic claims (no PHI)
tests/test_rule_engine.py   Unit tests
```

## Setup
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Run the tests
```powershell
python -m pytest -q
```

## Run the app
```powershell
streamlit run app.py
```
Then click **Run rule** to evaluate the synthetic claims. Decisions are appended to
`audit_log.jsonl`.

## Roadmap (next phases)
- **Phase 2 — LLM draft + human approval:** `src/llm_extractor.py` (OpenAI API *and* a
  deterministic mock mode for demos), `src/validator.py` (Pydantic + custom checks on
  the draft), `data/sample_cms_policy.txt`, and an approval gate in the UI.
- **Phase 3 (optional) — natural-language rule revision:** `src/rule_patcher.py` with a
  before/after diff shown before approval.

## Notes
Codes, thresholds, and policy text are **illustrative synthetic content** for the POC,
not authoritative clinical or billing guidance.
