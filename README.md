# Policy-to-Rule Claims Compliance Assistant

A proof of concept for the Cotiviti AI/ML intern assessment (topic: *Content
Management in Healthcare — converting written policy into executable claim rules*).

**Core idea:** policy text is written for humans, but claim review needs structured,
testable, auditable logic. An LLM *drafts* a structured rule from policy text and a
human *approves* it — but **the final claim decision is always made by deterministic
Python**, with a plain-language explanation, source policy evidence, and an audit trail.

## The full loop
1. **Draft (LLM):** Google Gemini converts policy text → a structured `PolicyRule`
   using structured JSON output. A **mock mode** returns a deterministic draft when no
   API key is set, so the app always works offline.
2. **Validate:** custom checks confirm the draft is a valid schema, has source evidence,
   uses well-formed service (CPT/HCPCS) and diagnosis (ICD-10) codes, and references only
   real claim fields.
3. **Approve (human):** a reviewer activates a valid draft. Until then the app runs the
   hardcoded `SAMPLE_RULE` and **says so with a warning banner**.
4. **Run (deterministic):** the engine evaluates synthetic claims with a fixed precedence:
   - Rule out of scope → **NOT_APPLICABLE**
   - A needed field missing/unparseable → **NEEDS_REVIEW**
   - An exclusion applies → **FAIL**
   - All coverage criteria + limits met → **PASS**, otherwise **FAIL**
5. **Audit:** every decision is appended to a JSONL audit log.

### Natural-language rule revision
After a rule is approved, a reviewer can revise it in plain English, e.g.
*"Add 97116 as a covered service code"* or *"Change visit limit from 12 to 10"*. The LLM
returns a structured **`RulePatch`** (a partial change, not a rewrite). The app applies it
deterministically, re-validates, shows a **before/after diff**, and saves the updated rule
(version bumped) only after the human clicks **Approve patch**. The change is recorded in
the audit log. By design a patch **cannot** alter the rule id, the source policy evidence,
past audit entries, or prior claim results, and nothing is applied automatically.

The `NEEDS_REVIEW`-on-missing-documentation case directly illustrates the report's lead
statistic on improper payments tied to insufficient documentation.

## Project layout
```
app.py                       Streamlit UI (draft → validate → approve → run → audit)
src/schemas.py               Pydantic models: Condition, Rule, EvalResult, PolicyRule
src/llm_extractor.py         Gemini extractor (+ mock mode) and PolicyRule→Rule converter
src/rule_patcher.py          NL rule revision: propose/apply/diff a structured RulePatch
src/validator.py             Validation checks on the LLM draft
src/rule_engine.py           Deterministic engine (no LLM, no Streamlit)
src/sample_rule.py           Hardcoded fallback rule (active until one is approved)
src/audit_logger.py          Append-only JSONL audit log
data/sample_cms_policy.txt   Synthetic policy text (extractor input)
data/synthetic_claims.csv    Synthetic claims (no PHI)
tests/                       pytest suite (engine, validator, extractor)
```

## Setup
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Optional: enable the real Gemini API
The app runs in **mock mode** with no setup. To use the real API:
```powershell
Copy-Item .env.example .env
# then edit .env and set GEMINI_API_KEY=your_key
```
Get a key from Google AI Studio. With a key present, the extractor calls
`gemini-2.5-flash`; without one, it uses the deterministic mock.

## Run the tests
```powershell
python -m pytest -q
```
Tests run entirely in mock mode — **no network or API key required**.

## Run the app
```powershell
streamlit run app.py
```
Then: **Extract rule (LLM)** → review validation → **Approve & activate** →
*(optional)* **Revise in natural language → Approve patch** → **Run rule on claims**.
Decisions and rule changes are appended to `audit_log.jsonl`.

## Notes
Codes, thresholds, and policy text are **illustrative synthetic content** for the POC,
not authoritative clinical or billing guidance. The LLM never makes a claim decision —
it only drafts a rule that a human must approve before deterministic execution.
