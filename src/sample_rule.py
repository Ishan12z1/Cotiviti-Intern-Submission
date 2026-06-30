"""Hardcoded sample rule for v1.

This stands in for an LLM-extracted rule. It is a structured representation of
CMS NCD 210.14 (Screening for Lung Cancer with Low Dose CT) for LDCT lung cancer
screening (CPT 71271). It deliberately exercises the supported operators and
includes a documentation requirement so the demo can show a NEEDS_REVIEW outcome
caused by missing documentation - directly illustrating the report's lead
statistic on improper payments tied to insufficient documentation.

NOTE: the policy's pack-year smoking history and quit-within-15-years criteria
are not codeable from the available claim fields; per NCD 210.14 they are
established and recorded during the required shared-decision-making visit, so the
rule checks that the visit was documented and leaves that clinical determination
to human review. Codes and thresholds are reproduced for the POC, not
authoritative billing guidance.
"""

from .schemas import Condition, Operator, Rule

SAMPLE_RULE = Rule(
    rule_id="CMS-LDCT-001",
    version=1,
    title="Lung Cancer Screening with LDCT Coverage",
    description=(
        "Determines whether a claim for low dose CT lung cancer screening "
        "(procedure 71271) meets NCD 210.14 age, documentation, and frequency "
        "criteria."
    ),
    applies_when=[
        Condition(
            field="procedure_code",
            op=Operator.IN,
            value=["71271"],
            description="Claim is for low dose CT lung cancer screening (CPT 71271).",
        ),
    ],
    indications=[
        Condition(
            field="patient_age",
            op=Operator.BETWEEN,
            value=[50, 77],
            description="Beneficiary is aged 50 to 77 years.",
        ),
    ],
    exclusions=[
        Condition(
            field="prior_ldct_within_12mo",
            op=Operator.EQ,
            value="Y",
            description="A prior LDCT screening within the last 12 months is not separately covered.",
        ),
    ],
    documentation_requirements=[
        Condition(
            field="shared_decision_visit",
            op=Operator.PRESENT,
            description="A documented counseling and shared decision-making visit must be on file.",
        ),
    ],
    timing_limits=[
        Condition(
            field="units",
            op=Operator.LTE,
            value=1,
            description="At most one LDCT screening unit per claim.",
        ),
    ],
    source_evidence=(
        "CMS NCD 210.14 (Screening for Lung Cancer with LDCT): Medicare covers "
        "annual screening for lung cancer with LDCT when the beneficiary is "
        "\"aged 50 to 77 years\", \"asymptomatic\", and meets the tobacco smoking "
        "history criteria. Before the first screening the beneficiary \"must receive "
        "a counseling and shared decision-making visit\" that is \"appropriately "
        "documented in the beneficiary's medical record.\" Covered \"no more "
        "frequently than once per year.\" The LDCT scan is reported with CPT 71271."
    ),
)
