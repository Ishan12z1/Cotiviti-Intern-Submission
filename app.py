"""Streamlit UI for the Policy-to-Rule Claims Compliance Assistant.

One working "draft" flows through four clear steps:

    1. Draft   - LLM turns policy text into a structured rule
    2. Refine  - edit the draft JSON by hand and/or refine it with natural language
    3. Approve - a human activates the draft (this is what bumps the version)
    4. Run     - the deterministic engine decides claims with the active rule

The LLM only drafts/refines; deterministic Python makes every claim decision. Until
a rule is approved, the engine runs the hardcoded SAMPLE_RULE (and says so).
"""

import json
import os

import pandas as pd
import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv optional at runtime
    pass

from src.audit_logger import DEFAULT_LOG_PATH, log_event, log_results, read_log
from src.llm_extractor import DEFAULT_MODEL, active_mode, extract_rule, policy_rule_to_rule
from src.rule_engine import run_batch
from src.rule_patcher import apply_patch, diff_policy_rules, patch_has_changes, propose_patch
from src.sample_rule import SAMPLE_RULE
from src.schemas import Outcome, PolicyRule
from src.validator import validate_policy_rule

CLAIMS_PATH = os.path.join("data", "synthetic_claims.csv")
POLICY_PATH = os.path.join("data", "sample_cms_policy.txt")

OUTCOME_STYLE = {
    Outcome.PASS.value: "✅ PASS",
    Outcome.FAIL.value: "❌ FAIL",
    Outcome.NEEDS_REVIEW.value: "🔎 NEEDS_REVIEW",
    Outcome.NOT_APPLICABLE.value: "➖ NOT_APPLICABLE",
}

st.set_page_config(page_title="Policy-to-Rule Claims Assistant", layout="centered")

# --- Brand styling (navy primary + teal accent) ----------------------------
st.markdown(
    """
    <style>
      :root {
        --color-navy: #1E2761; --color-navy-deep: #16224F; --color-teal: #0F8B8D;
        --color-ice: #CADCFC; --color-bg-light: #F6F8FB; --color-white: #FFFFFF;
        --color-text-muted: #5B6B85; --color-text-dark: #1B2540; --color-warn: #8C6A1B;
      }
      /* Navy, dominant headings */
      h1, h2, h3 { color: var(--color-navy) !important; font-weight: 700; }
      /* Teal links */
      a, a:visited { color: var(--color-teal) !important; }
      /* Muted captions */
      [data-testid="stCaptionContainer"], .stCaption { color: var(--color-text-muted) !important; }
      /* Teal primary buttons, navy on hover */
      .stButton > button[kind="primary"] {
        background-color: var(--color-teal); border-color: var(--color-teal); color: #fff;
      }
      .stButton > button[kind="primary"]:hover {
        background-color: var(--color-navy); border-color: var(--color-navy); color: #fff;
      }
      /* Navy brand sidebar with ice text */
      section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, var(--color-navy) 0%, var(--color-navy-deep) 100%);
      }
      section[data-testid="stSidebar"] h1,
      section[data-testid="stSidebar"] h2,
      section[data-testid="stSidebar"] h3,
      section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
      section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: var(--color-ice) !important;
      }
      section[data-testid="stSidebar"] .stButton > button {
        background-color: var(--color-teal); border-color: var(--color-teal); color: #fff;
      }
      /* Custom, high-contrast status badges for the navy sidebar */
      .side-badge {
        padding: 8px 12px; border-radius: 8px; margin-bottom: 8px;
        font-size: 0.88rem; font-weight: 600; color: #fff; line-height: 1.35;
      }
      .side-badge.ok   { background-color: var(--color-teal); }
      .side-badge.warn { background-color: var(--color-warn); }
      .side-note { color: var(--color-ice); font-size: 0.85rem; }
      .side-hr { border: none; border-top: 1px solid rgba(202,220,252,0.30); margin: 12px 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Session state ---------------------------------------------------------
st.session_state.setdefault("draft", None)                 # working PolicyRule
st.session_state.setdefault("approved_rule", None)         # active engine Rule
st.session_state.setdefault("approved_policy_rule", None)  # PolicyRule behind it
st.session_state.setdefault("approved_version", 0)
st.session_state.setdefault("proposed_patch", None)
st.session_state.setdefault("last_results_df", None)
st.session_state.setdefault("last_run_rule", None)

# --- Claims (columns drive extraction + validation) ------------------------
if not os.path.exists(CLAIMS_PATH):
    st.error(f"Claims file not found: {CLAIMS_PATH}")
    st.stop()
claims_df = pd.read_csv(CLAIMS_PATH, dtype=str).fillna("")
claim_columns = list(claims_df.columns)


# --- Helpers ---------------------------------------------------------------
def _conditions_table(conditions):
    if not conditions:
        return pd.DataFrame([{"field": "(none)", "op": "", "value": "", "description": ""}])
    return pd.DataFrame(
        [
            {
                "field": c.field,
                "op": c.op.value,
                "value": "" if c.value is None else str(c.value),
                "description": c.description,
            }
            for c in conditions
        ]
    )


def _show_rule_definition(rule):
    st.markdown("**Applies when**")
    st.dataframe(_conditions_table(rule.applies_when), hide_index=True, width="stretch")
    st.markdown("**Indications**")
    st.dataframe(_conditions_table(rule.indications), hide_index=True, width="stretch")
    st.markdown("**Exclusions**")
    st.dataframe(_conditions_table(rule.exclusions), hide_index=True, width="stretch")
    st.markdown("**Documentation requirements**")
    st.dataframe(_conditions_table(rule.documentation_requirements), hide_index=True, width="stretch")
    st.markdown("**Timing limits**")
    st.dataframe(_conditions_table(rule.timing_limits), hide_index=True, width="stretch")


def _reset():
    for key in ("draft", "approved_rule", "approved_policy_rule", "proposed_patch",
                "last_results_df", "last_run_rule"):
        st.session_state[key] = None
    st.session_state["approved_version"] = 0


# --- Sidebar: status & controls -------------------------------------------
def _badge(text: str, kind: str = "ok"):
    st.markdown(f"<div class='side-badge {kind}'>{text}</div>", unsafe_allow_html=True)


with st.sidebar:
    st.markdown("### Status")
    mode_choice = st.selectbox(
        "LLM mode",
        options=["auto", "mock", "api"],
        format_func=lambda m: {
            "auto": "Auto (use API if key set)",
            "mock": "Mock (offline, no API)",
            "api": "API (Gemini)",
        }[m],
        help="Mock runs fully offline with a deterministic draft. Choose Mock if you "
             "have no internet/API access.",
    )
    mode = active_mode(mode_choice)
    if mode == "api":
        _badge(f"LLM · Gemini {DEFAULT_MODEL}", "ok")
    else:
        key_hint = "no API key" if mode_choice == "auto" else "selected"
        _badge(f"LLM · mock mode ({key_hint})", "warn")

    approved_rule = st.session_state["approved_rule"]
    if approved_rule is None:
        _badge("Active rule · hardcoded sample (not approved)", "warn")
    else:
        _badge(f"Active rule · {approved_rule.rule_id} v{approved_rule.version} (approved)", "ok")

    st.markdown("<hr class='side-hr'>", unsafe_allow_html=True)
    st.markdown(
        "<p class='side-note'>LLM <b>drafts/refines</b> rules. A human <b>approves</b>. "
        "Deterministic Python <b>decides</b> every claim. Synthetic data only.</p>",
        unsafe_allow_html=True,
    )
    if st.button("↺ Reset all"):
        _reset()
        st.rerun()


st.title("Policy-to-Rule Claims Compliance Assistant")

draft = st.session_state["draft"]

# === Step 1 — Draft ========================================================
st.subheader("1 · Draft a rule from policy text")
default_policy = ""
if os.path.exists(POLICY_PATH):
    with open(POLICY_PATH, "r", encoding="utf-8") as fh:
        default_policy = fh.read()

with st.expander("Policy text", expanded=draft is None):
    policy_text = st.text_area("Policy text", value=default_policy, height=220,
                               label_visibility="collapsed")
    if st.button("Extract rule with LLM", type="primary"):
        with st.spinner("Extracting..."):
            try:
                st.session_state["draft"] = extract_rule(policy_text, claim_columns, mode=mode)
                st.session_state["proposed_patch"] = None
                st.rerun()
            except Exception as exc:
                st.error(f"Extraction failed: {exc}")
                if mode == "api":
                    st.info("This looks like an API/network problem. Switch **LLM mode** to "
                            "**Mock (offline)** in the sidebar to run the demo without internet.")


# === Step 2 — Refine (edit + NL) ===========================================
st.subheader("2 · Review, edit & refine the draft")
if draft is None:
    st.info("Extract a rule above to begin. (You can still run the hardcoded rule in step 4.)")
else:
    # 2a. View + manual JSON edit ------------------------------------------
    st.markdown("**Drafted rule**")
    st.json(draft.model_dump())
    with st.expander("✏️ Edit JSON manually"):
        edited = st.text_area("Draft JSON", value=draft.model_dump_json(indent=2),
                              height=320, label_visibility="collapsed")
        if st.button("Apply manual edits"):
            try:
                st.session_state["draft"] = PolicyRule.model_validate_json(edited)
                st.success("Manual edits applied.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not apply edits — invalid JSON or schema: {exc}")

    # 2b. Natural-language refinement --------------------------------------
    st.markdown("**Refine with natural language** — the LLM proposes a *patch*, not a rewrite.")
    instruction = st.text_input(
        "Revision instruction", label_visibility="collapsed",
        placeholder="e.g. Add 97116 as a covered service code",
    )
    if st.button("Propose refinement"):
        if not instruction.strip():
            st.warning("Enter an instruction first.")
        else:
            with st.spinner("Proposing patch..."):
                try:
                    st.session_state["proposed_patch"] = propose_patch(
                        instruction, draft, claim_columns, mode=mode
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Patch proposal failed: {exc}")

    patch = st.session_state["proposed_patch"]
    if patch is not None:
        st.caption(f"Proposed change: {patch.summary}")
        if not patch_has_changes(patch):
            st.warning("This patch makes no changes. Try rephrasing.")
        else:
            patched = apply_patch(draft, patch)
            diff_rows = diff_policy_rules(draft, patched)
            st.markdown("**Before / after**")
            st.dataframe(
                pd.DataFrame([{"field": r["field"], "before": str(r["before"]),
                               "after": str(r["after"])} for r in diff_rows]),
                hide_index=True, width="stretch",
            )
            c1, c2 = st.columns(2)
            if c1.button("✓ Apply refinement", type="primary"):
                st.session_state["draft"] = patched
                st.session_state["proposed_patch"] = None
                st.rerun()
            if c2.button("✕ Discard"):
                st.session_state["proposed_patch"] = None
                st.rerun()

    # 2c. Validation + engine preview --------------------------------------
    report = validate_policy_rule(draft, claim_columns)
    if report.is_valid:
        st.success("Draft is valid — ready to approve.")
    else:
        st.error(f"Draft has {len(report.errors())} validation issue(s) — fix before approving.")
    with st.expander("Validation details", expanded=not report.is_valid):
        st.dataframe(
            pd.DataFrame([{"check": i.check, "result": "✅" if i.level == "ok" else "❌",
                           "detail": i.message} for i in report.issues]),
            hide_index=True, width="stretch",
        )
    with st.expander("Engine-ready rule (converted from draft)"):
        _show_rule_definition(policy_rule_to_rule(draft))

    # === Step 3 — Approve =================================================
    st.subheader("3 · Approve & activate")
    next_version = st.session_state["approved_version"] + 1
    st.caption(f"Approving will activate **{draft.rule_id}** as **v{next_version}** and log the change.")
    if st.button("✅ Approve & activate", type="primary", disabled=not report.is_valid):
        prev_pr = st.session_state["approved_policy_rule"]
        diff_rows = diff_policy_rules(prev_pr, draft) if prev_pr else []
        st.session_state["approved_rule"] = policy_rule_to_rule(draft, version=next_version)
        st.session_state["approved_policy_rule"] = draft
        st.session_state["approved_version"] = next_version
        log_event({
            "event": "rule_activated",
            "rule_id": draft.rule_id,
            "from_version": next_version - 1,
            "to_version": next_version,
            "mode": mode,
            "changes": diff_rows,
        }, path=DEFAULT_LOG_PATH)
        st.success(f"Activated {draft.rule_id} v{next_version}.")
        st.rerun()


# === Step 4 — Run ==========================================================
st.subheader("4 · Run on claims")
active_rule = st.session_state["approved_rule"] or SAMPLE_RULE
if st.session_state["approved_rule"] is None:
    st.warning(f"⚠️ Running the **hardcoded sample rule** ({SAMPLE_RULE.rule_id}). "
               "Approve a drafted rule above to use it instead.")
else:
    st.info(f"Active rule: **{active_rule.rule_id} v{active_rule.version}** (human-approved).")

with st.expander("Synthetic claims"):
    st.dataframe(claims_df, hide_index=True, width="stretch", height=300)

if st.button("Run rule on claims", type="primary"):
    results = run_batch(active_rule, claims_df)
    log_results(results, path=DEFAULT_LOG_PATH)
    st.session_state["last_results_df"] = pd.DataFrame(
        [{"claim_id": r.claim_id,
          "outcome": OUTCOME_STYLE.get(r.outcome.value, r.outcome.value),
          "reasons": " ; ".join(r.reasons)} for r in results]
    )
    st.session_state["last_run_rule"] = f"{active_rule.rule_id} v{active_rule.version}"

results_df = st.session_state["last_results_df"]
if results_df is not None:
    st.caption(f"Last run: rule `{st.session_state['last_run_rule']}`")
    counts = results_df["outcome"].value_counts().to_dict()
    cols = st.columns(len(OUTCOME_STYLE))
    for col, label in zip(cols, OUTCOME_STYLE.values()):
        col.metric(label, counts.get(label, 0))
    st.dataframe(
        results_df,
        hide_index=True,
        width="stretch",
        height=430,
        column_config={
            "claim_id": st.column_config.TextColumn("Claim", width="small"),
            "outcome": st.column_config.TextColumn("Outcome", width="small"),
            "reasons": st.column_config.TextColumn("Reasons", width="large"),
        },
    )


# === Audit log =============================================================
with st.expander("Audit log"):
    entries = read_log(DEFAULT_LOG_PATH)
    if not entries:
        st.write("No audit entries yet.")
    else:
        display = [
            {k: (v if isinstance(v, (str, int, float, bool)) or v is None else json.dumps(v))
             for k, v in entry.items()}
            for entry in entries[-50:]
        ]
        st.dataframe(pd.DataFrame(display), hide_index=True, width="stretch", height=300)
