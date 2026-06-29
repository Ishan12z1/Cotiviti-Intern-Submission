## Project Goal
Build a quick Streamlit proof of concept for the Cotiviti AI/ML intern assessment.

The POC demonstrates a controlled LLM workflow:
1. Load real CMS-style healthcare policy text
2. Extract structured draft claim-review rules
3. Validate the extracted rule with Pydantic and custom checks
4. Allow human approval or rejection
5. Allow natural-language rule revision through a structured patch
6. Run approved rules on synthetic claims
7. Show PASS / FAIL / NEEDS_REVIEW with explanations and source evidence
8. Write an audit log

## Important Constraints
- Do not use real PHI or real patient data.
- Use synthetic claims only.
- The LLM must not make final claim decisions.
- The LLM may only draft rules or propose structured patches.
- Final claim decisions must come from deterministic Python logic.
- Human approval is required before rule execution.
- Every extracted rule should include source evidence.
- Every rule update should show a before/after diff before approval.

## Tech Stack
- Python
- Streamlit
- Pydantic
- Pandas
- OpenAI API or mock LLM mode
- Pytest

## Required Files
- app.py
- src/schemas.py
- src/llm_extractor.py
- src/validator.py
- src/rule_engine.py
- src/rule_patcher.py
- src/audit_logger.py
- data/sample_cms_policy.txt
- data/synthetic_claims.csv
- tests/test_rule_engine.py
- README.md

## Development Rules
Before editing code:
1. List the files you plan to touch.
2. Explain the intended change.
3. Wait for approval if the change affects more than 3 files.

After editing:
1. Summarize what changed.
2. Run tests if possible.
3. Tell me the exact command to run the app.

## POC Scope
Keep this simple. Do not add authentication, database, Docker, FHIR integration, real CMS downloads, or production deployment.