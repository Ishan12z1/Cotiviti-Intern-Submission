"""Streamlit UI for the Policy-to-Rule Claims Compliance Assistant (v1).

v1 scope: show a (hardcoded) approved rule, run it deterministically over synthetic
claims, and display PASS / FAIL / NEEDS_REVIEW / NOT_APPLICABLE with explanations,
source evidence, and an audit trail. The LLM drafting + human-approval steps are
planned for a later phase; the layout leaves room for them.
"""

import os

import pandas as pd
import streamlit as st

from src.audit_logger import DEFAULT_LOG_PATH, log_results, read_log
from src.rule_engine import run_batch
from src.sample_rule import SAMPLE_RULE
from src.schemas import Outcome

CLAIMS_PATH = os.path.join("data", "synthetic_claims.csv")

OUTCOME_STYLE = {
    Outcome.PASS.value: "✅ PASS",
    Outcome.FAIL.value: "❌ FAIL",
    Outcome.NEEDS_REVIEW.value: "🔎 NEEDS_REVIEW",
    Outcome.NOT_APPLICABLE.value: "➖ NOT_APPLICABLE",
}

st.set_page_config(page_title="Policy-to-Rule Claims Assistant", layout="wide")

st.title("Policy-to-Rule Claims Compliance Assistant")
st.caption(
    "v1 — deterministic core. The LLM may only draft rules; **final claim "
    "decisions are made by deterministic Python.** Synthetic data only."
)


def _conditions_table(conditions):
    if not conditions:
        return pd.DataFrame([{"field": "(none)", "op": "", "value": "", "description": ""}])
    return pd.DataFrame(
        [
            {
                "field": c.field,
                "op": c.op.value,
                "value": "" if c.value is None else c.value,
                "description": c.description,
            }
            for c in conditions
        ]
    )


# --- Active rule -----------------------------------------------------------
st.header("1. Active rule")
rule = SAMPLE_RULE
st.subheader(f"{rule.rule_id} v{rule.version} — {rule.title}")
st.write(rule.description)
st.info(f"**Source evidence:** {rule.source_evidence}")

with st.expander("Structured rule definition", expanded=False):
    st.markdown("**Applies when**")
    st.dataframe(_conditions_table(rule.applies_when), hide_index=True, use_container_width=True)
    st.markdown("**Indications (coverage criteria)**")
    st.dataframe(_conditions_table(rule.indications), hide_index=True, use_container_width=True)
    st.markdown("**Exclusions**")
    st.dataframe(_conditions_table(rule.exclusions), hide_index=True, use_container_width=True)
    st.markdown("**Documentation requirements**")
    st.dataframe(_conditions_table(rule.documentation_requirements), hide_index=True, use_container_width=True)
    st.markdown("**Timing limits**")
    st.dataframe(_conditions_table(rule.timing_limits), hide_index=True, use_container_width=True)


# --- Claims ----------------------------------------------------------------
st.header("2. Synthetic claims")
if not os.path.exists(CLAIMS_PATH):
    st.error(f"Claims file not found: {CLAIMS_PATH}")
    st.stop()

claims_df = pd.read_csv(CLAIMS_PATH, dtype=str).fillna("")
st.dataframe(claims_df, hide_index=True, use_container_width=True)


# --- Run -------------------------------------------------------------------
st.header("3. Run rule on claims")
if st.button("Run rule", type="primary"):
    results = run_batch(rule, claims_df)
    log_results(results, path=DEFAULT_LOG_PATH)

    results_df = pd.DataFrame(
        [
            {
                "claim_id": r.claim_id,
                "outcome": OUTCOME_STYLE.get(r.outcome.value, r.outcome.value),
                "reasons": " ; ".join(r.reasons),
            }
            for r in results
        ]
    )

    counts = results_df["outcome"].value_counts().to_dict()
    cols = st.columns(len(OUTCOME_STYLE))
    for col, (label) in zip(cols, OUTCOME_STYLE.values()):
        col.metric(label, counts.get(label, 0))

    st.dataframe(results_df, hide_index=True, use_container_width=True)
    st.success(f"Evaluated {len(results)} claims and wrote them to the audit log.")
else:
    st.write("Click **Run rule** to evaluate the claims above.")


# --- Audit log -------------------------------------------------------------
st.header("4. Audit log")
with st.expander("Recent audit entries", expanded=False):
    entries = read_log(DEFAULT_LOG_PATH)
    if not entries:
        st.write("No audit entries yet.")
    else:
        st.dataframe(
            pd.DataFrame(entries[-50:]), hide_index=True, use_container_width=True
        )
