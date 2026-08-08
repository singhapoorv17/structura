"""Begin construction - and the litigation fork that no incumbent models.

**Why this module exists.** Under OBBBA the single most valuable fact about a
wind or solar project is whether it *began construction* on or before
2026-07-04. Whether it did depends on which of two tests it used, and whether
that test was available to it - and that availability is, as of the verification
date, the subject of a live appeal.

The chain of events (SPEC §2.5, verified 2026-08-06):

1. Two long-standing routes establish begin construction: the **5% cost safe
   harbor** (pay or incur at least 5% of total facility cost) and the
   **Physical Work Test** (physical work of a significant nature, on site or at
   a manufacturer under a binding written contract). Both must be followed by
   continuous efforts, deemed satisfied if the facility is placed in service by
   the end of the fourth calendar year after the BOC year - the **four-year
   continuity safe harbor**.
2. **IRS Notice 2025-42** (August 2025) withdrew the 5% safe harbor for wind and
   solar facilities above 1.5 MW nameplate, leaving the Physical Work Test as
   the only route. That is a materially harder test to document, and it
   invalidated a large volume of safe-harboured equipment purchases.
3. On **2026-06-06** the U.S. District Court for the District of Columbia, in
   ***Oregon Environmental Council v. IRS*, No. 25-4400 (CKK)**, **vacated
   Notice 2025-42 in full** as arbitrary and capricious under the APA and
   remanded. **The 5% safe harbor is restored as of the verification date.**
4. A government appeal and/or stay is expected, and the court acknowledged the
   appellate timeline runs past 2026-07-04.

So the correct engineering answer is not to pick a side. It is to make the
notice's status a **scenario input**
(:class:`engine.tax.enums.Notice202542Status`) that flips real eligibility
outcomes, and to say so on the face of the result.
"""

from __future__ import annotations

from datetime import date

from engine.tax.constants import (
    CONTINUITY_SAFE_HARBOR_YEARS,
    FIVE_PERCENT_SAFE_HARBOR_THRESHOLD,
    NOTICE_2025_42_APPLIES_TO_BOC_AFTER,
    NOTICE_2025_42_CAPACITY_THRESHOLD_MW,
)
from engine.tax.models import (
    BeginConstructionMethod,
    BeginConstructionResult,
    DeterminationStep,
    Notice202542Status,
    TaxProject,
    TaxScenario,
)

__all__ = [
    "continuity_deadline",
    "notice_2025_42_applies",
    "assess_begin_construction",
]


def continuity_deadline(boc_date: date) -> date:
    """End of the four-year continuity safe harbor window.

    The facility must be placed in service by the end of the *fourth calendar
    year following* the calendar year in which construction began. A project
    beginning construction on 2026-07-01 therefore has until 2030-12-31.
    """
    return date(boc_date.year + CONTINUITY_SAFE_HARBOR_YEARS, 12, 31)


def notice_2025_42_applies(
    project: TaxProject, scenario: TaxScenario
) -> tuple[bool, str]:
    """Does Notice 2025-42 bite this project under the modelled scenario?

    Three conditions must all hold:

    * the notice is in force under the scenario (it is **not**, under current
      law, because of the *Oregon Environmental Council* vacatur);
    * the technology is wind or solar;
    * nameplate capacity exceeds 1.5 MW.

    Returns ``(applies, reason)`` where ``reason`` is the sentence shown to the
    user.
    """
    if scenario.notice_2025_42_status is Notice202542Status.VACATED:
        return (
            False,
            "Notice 2025-42 was vacated in full by the D.D.C. on 2026-06-06 "
            "(Oregon Environmental Council v. IRS, No. 25-4400 (CKK)), so the "
            "5% cost safe harbor is restored. A government appeal is expected.",
        )
    if not project.technology.is_wind_or_solar:
        return (
            False,
            f"Notice 2025-42 addresses only wind and solar; this is "
            f"{project.technology.value}.",
        )
    if project.capacity_mw <= NOTICE_2025_42_CAPACITY_THRESHOLD_MW:
        return (
            False,
            f"Notice 2025-42 applies only above "
            f"{NOTICE_2025_42_CAPACITY_THRESHOLD_MW} MW; this facility is "
            f"{project.capacity_mw:g} MW.",
        )
    if (
        project.begin_construction_date is not None
        and project.begin_construction_date <= NOTICE_2025_42_APPLIES_TO_BOC_AFTER
    ):
        return (
            False,
            f"Construction began {project.begin_construction_date.isoformat()}, "
            f"on or before the notice's prospective applicability date "
            f"({NOTICE_2025_42_APPLIES_TO_BOC_AFTER.isoformat()}; PLACEHOLDER "
            f"- see UNVERIFIED.md).",
        )
    return (
        True,
        f"Notice 2025-42 is modelled as reinstated on appeal and applies to "
        f"this {project.technology.value} facility of {project.capacity_mw:g} MW "
        f"(> {NOTICE_2025_42_CAPACITY_THRESHOLD_MW} MW): the 5% cost safe "
        f"harbor is unavailable and only the Physical Work Test can establish "
        f"begin construction.",
    )


def assess_begin_construction(
    project: TaxProject, scenario: TaxScenario | None = None
) -> BeginConstructionResult:
    """Determine whether construction was validly begun, and by which route.

    The result reports four things a diligence reader asks in order:

    1. was the chosen method *available* (the Notice 2025-42 question);
    2. was the method's own test *met* (5% incurred / physical work commenced);
    3. what is the continuity deadline;
    4. is continuity satisfied on the projected placed-in-service date.

    A project that fails (1) or (2) has **not** begun construction, which for
    wind and solar pushes it onto the 2027-12-31 placed-in-service backstop in
    :mod:`engine.tax.eligibility` - frequently the difference between a 30%
    credit and zero.
    """
    scenario = scenario or TaxScenario()
    steps: list[DeterminationStep] = []
    citations: list[str] = []
    method = project.begin_construction_method
    boc = project.begin_construction_date

    applies, notice_reason = notice_2025_42_applies(project, scenario)
    citations.extend(("notice-2025-42", "oregon-environmental-council-vacatur"))
    steps.append(
        DeterminationStep(
            label="Notice 2025-42 status",
            outcome=(
                "applies - 5% safe harbor unavailable"
                if applies
                else "does not apply"
            ),
            detail=notice_reason,
            citation_ids=(
                "notice-2025-42",
                "oregon-environmental-council-vacatur",
                "notice-2025-42-applicability-date",
            ),
        )
    )

    if boc is None:
        steps.append(
            DeterminationStep(
                label="Begin construction",
                outcome="not established",
                detail="No begin-construction date was asserted.",
            )
        )
        return BeginConstructionResult(
            established=False,
            method=method,
            method_available=not applies
            or method is BeginConstructionMethod.PHYSICAL_WORK_TEST,
            notice_2025_42_status=scenario.notice_2025_42_status,
            notice_2025_42_applies=applies,
            begin_construction_date=None,
            continuity_deadline=None,
            continuity_satisfied=False,
            reason="No begin-construction date asserted.",
            steps=tuple(steps),
            citation_ids=tuple(dict.fromkeys(citations)),
        )

    # --- (1) method availability -----------------------------------------
    method_available = True
    if method is BeginConstructionMethod.FIVE_PERCENT_SAFE_HARBOR and applies:
        method_available = False

    # --- (2) is the method's own test met? -------------------------------
    if method is BeginConstructionMethod.FIVE_PERCENT_SAFE_HARBOR:
        citations.append("five-percent-safe-harbor")
        test_met = (
            project.cost_incurred_pct_at_boc >= FIVE_PERCENT_SAFE_HARBOR_THRESHOLD
        )
        test_detail = (
            f"{project.cost_incurred_pct_at_boc:.1%} of total facility cost paid "
            f"or incurred as at {boc.isoformat()} against a "
            f"{FIVE_PERCENT_SAFE_HARBOR_THRESHOLD:.0%} threshold."
        )
        test_citation = "five-percent-safe-harbor"
    else:
        citations.append("physical-work-test")
        test_met = project.physical_work_commenced
        if test_met:
            test_detail = (
                project.physical_work_description
                or "Physical work of a significant nature asserted. The test is "
                "facts-and-circumstances with no cost threshold, so the "
                "supporting record is the whole of the defence."
            )
        else:
            test_detail = "No physical work of a significant nature asserted."
        test_citation = "physical-work-test"

    if not method_available:
        established = False
        reason = (
            "The 5% cost safe harbor is unavailable to this project under the "
            "modelled scenario, so begin construction cannot be established by "
            "that route."
        )
        steps.append(
            DeterminationStep(
                label="Method availability",
                outcome="5% cost safe harbor UNAVAILABLE",
                detail=notice_reason,
                citation_ids=("notice-2025-42",),
            )
        )
    else:
        established = test_met
        reason = (
            f"Begin construction established on {boc.isoformat()} by the "
            f"{_method_label(method)}."
            if test_met
            else f"The {_method_label(method)} was not satisfied."
        )
        steps.append(
            DeterminationStep(
                label=f"{_method_label(method)}",
                outcome="satisfied" if test_met else "not satisfied",
                detail=test_detail,
                citation_ids=(test_citation,),
            )
        )

    # --- (3) and (4) continuity ------------------------------------------
    deadline = continuity_deadline(boc)
    citations.append("continuity-safe-harbor")
    cont_ok = project.placed_in_service_date <= deadline
    steps.append(
        DeterminationStep(
            label="Four-year continuity safe harbor",
            outcome="satisfied" if cont_ok else "MISSED",
            detail=(
                f"Construction began {boc.isoformat()}, so the facility must be "
                f"placed in service by {deadline.isoformat()}. Projected PIS is "
                f"{project.placed_in_service_date.isoformat()}."
            ),
            citation_ids=("continuity-safe-harbor",),
        )
    )

    if established and not cont_ok:
        established = False
        reason = (
            f"Begin construction was established on {boc.isoformat()} but the "
            f"four-year continuity window closes {deadline.isoformat()} and the "
            f"projected placed-in-service date is "
            f"{project.placed_in_service_date.isoformat()}."
        )

    return BeginConstructionResult(
        established=established,
        method=method,
        method_available=method_available,
        notice_2025_42_status=scenario.notice_2025_42_status,
        notice_2025_42_applies=applies,
        begin_construction_date=boc,
        continuity_deadline=deadline,
        continuity_satisfied=cont_ok,
        reason=reason,
        steps=tuple(steps),
        citation_ids=tuple(dict.fromkeys(citations)),
    )


def _method_label(method: BeginConstructionMethod) -> str:
    return (
        "5% cost safe harbor"
        if method is BeginConstructionMethod.FIVE_PERCENT_SAFE_HARBOR
        else "Physical Work Test"
    )
