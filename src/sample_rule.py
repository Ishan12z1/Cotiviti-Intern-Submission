"""Hardcoded sample rule for v1.

This stands in for an LLM-extracted rule. It is a simplified, synthetic
representation of a CMS-style coverage policy for DEXA (bone density) screening.
It deliberately exercises every supported operator and includes a documentation
requirement so the demo can show a NEEDS_REVIEW outcome caused by missing
documentation - directly illustrating the report's lead statistic on improper
payments tied to insufficient documentation.

NOTE: codes and thresholds are illustrative for the POC, not authoritative
clinical or billing guidance.
"""

from .schemas import Condition, Operator, Rule

# Diagnosis codes that justify a DEXA screening in this synthetic policy.
ALLOWED_DIAGNOSIS_CODES = ["M81.0", "M80.00", "E21.0", "Z78.0"]

SAMPLE_RULE = Rule(
    rule_id="CMS-DEXA-001",
    version=1,
    title="DEXA Bone Density Screening Coverage",
    description=(
        "Determines whether a claim for a DEXA bone density scan (procedure 77080) "
        "meets coverage criteria, documentation, and frequency limits."
    ),
    applies_when=[
        Condition(
            field="procedure_code",
            op=Operator.EQ,
            value="77080",
            description="Claim is for a DEXA bone density scan (CPT 77080).",
        ),
    ],
    indications=[
        Condition(
            field="patient_age",
            op=Operator.BETWEEN,
            value=[65, 120],
            description="Patient is 65 years or older.",
        ),
        Condition(
            field="diagnosis_code",
            op=Operator.IN,
            value=ALLOWED_DIAGNOSIS_CODES,
            description="Diagnosis is an approved indication for DEXA screening.",
        ),
    ],
    exclusions=[
        Condition(
            field="prior_dexa_within_24mo",
            op=Operator.EQ,
            value="Y",
            description="A prior DEXA scan within 24 months is not separately covered.",
        ),
    ],
    documentation_requirements=[
        Condition(
            field="physician_order",
            op=Operator.PRESENT,
            description="A signed physician order must be on file.",
        ),
    ],
    timing_limits=[
        Condition(
            field="units",
            op=Operator.LTE,
            value=1,
            description="At most one DEXA scan unit per claim.",
        ),
    ],
    source_evidence=(
        "Synthetic policy excerpt: \"Dual-energy x-ray absorptiometry (DEXA, CPT 77080) "
        "is covered once every 24 months for beneficiaries aged 65 and older with an "
        "approved osteoporosis-related indication, when supported by a signed physician "
        "order.\""
    ),
)
