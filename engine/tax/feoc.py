"""FEOC and the Material Assistance Cost Ratio - a pass/fail gate, not a warning.

**The law (verified 2026-08-06).** OBBBA §70512 introduced foreign
entity of concern (FEOC) restrictions effective **2026-01-01**. IRS **Notice
2026-15**, released **2026-02-12**, is the interim guidance. It defines the
**Material Assistance Cost Ratio (MACR)** methodology, provides interim safe
harbors, permits reliance on supplier certifications, and supplies DOE-derived
default cost tables. Broader prohibited-foreign-entity status guidance was
deferred.

**What a MACR is.** Broadly, the share of a facility's (or eligible component's)
total direct costs that is *not* attributable to a prohibited foreign entity::

    MACR = (total direct costs - PFE-attributable costs) / total direct costs

The taxpayer must **meet or exceed** a technology- and year-specific threshold.
Fail it and the credit is **denied**. This module therefore returns a hard
disqualification that :mod:`engine.tax.eligibility` propagates into a zero
credit - never a warning flag.

**⚠️ Threshold honesty.** Exactly one cell of the threshold table is carried by
the verified rulebook: solar eligible components sold in CY2026 must reach a
MACR of at least 50%. Every other cell in
:data:`engine.tax.constants.PROVISIONAL_MACR_THRESHOLDS` is a **placeholder**.
Every lookup returns ``threshold_is_placeholder`` so the UI can say so, and the
gaps are itemised in ``UNVERIFIED.md``. The table is structured exactly as the
statutory table is - ``{technology: {year: threshold}}`` - so real values drop
straight in.

**§70512(h).** Separately from the MACR gate, §70512(h) prohibits *transferring*
a §45Q/45X/45Y/45Z/48E credit to a **specified foreign entity** within the
meaning of §7701(a)(51)(B), effective for taxable years beginning after
2025-07-04 - first tested 2026-01-01 for a calendar-year taxpayer. That test
lives here (it is a FEOC rule) and is enforced by :mod:`engine.tax.transfer`.
"""

from __future__ import annotations

from datetime import date

from engine.tax.constants import (
    FEOC_EFFECTIVE_DATE,
    PROVISIONAL_MACR_THRESHOLDS,
    SECTION_70512H_EFFECTIVE_FOR_TY_BEGINNING_AFTER,
    SECTION_70512H_PROHIBITED_SECTIONS,
    VERIFIED_MACR_CELLS,
)
from engine.tax.models import (
    ComponentCost,
    CreditSection,
    DeterminationStep,
    FeocResult,
    ForeignEntityStatus,
    MacrInputs,
    MacrMethod,
    TaxProject,
    Technology,
)

__all__ = [
    "MacrThreshold",
    "macr_threshold",
    "compute_macr",
    "assess_feoc",
    "transfer_to_foreign_entity_prohibited",
]


class MacrThreshold:
    """A threshold lookup result that knows how much to trust itself.

    Deliberately not a bare ``float``: every caller is forced to acknowledge
    whether the number is law or a stand-in.
    """

    __slots__ = ("technology", "year", "value", "is_placeholder", "note")

    def __init__(
        self,
        technology: Technology,
        year: int,
        value: float,
        is_placeholder: bool,
        note: str,
    ) -> None:
        self.technology = technology
        self.year = year
        self.value = value
        self.is_placeholder = is_placeholder
        self.note = note

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        flag = "PLACEHOLDER" if self.is_placeholder else "verified"
        return (
            f"MacrThreshold({self.technology.value}, {self.year}, "
            f"{self.value:.0%}, {flag})"
        )


def macr_threshold(technology: Technology, year: int) -> MacrThreshold:
    """Minimum Material Assistance Cost Ratio for a technology and year.

    Years beyond the last tabulated year inherit the last value; years before
    the first inherit the first (the restrictions do not bite before
    2026-01-01, which :func:`assess_feoc` checks separately).

    Only ``(SOLAR, 2026) -> 50%`` is verified. Everything else is a placeholder
    and says so.
    """
    table = PROVISIONAL_MACR_THRESHOLDS[technology]
    years = sorted(table)
    if year <= years[0]:
        key = years[0]
    elif year >= years[-1]:
        key = years[-1]
    else:
        key = max(y for y in years if y <= year)

    verified = (technology, year) in VERIFIED_MACR_CELLS
    note = (
        "Threshold carried by the verified rulebook: solar eligible "
        "components sold in CY2026 require MACR >= 50%."
        if verified
        else "PLACEHOLDER threshold. The statutory MACR table in OBBBA §70512 "
        "was not sourced in this build. Structure is correct; the value is not "
        "authority. See UNVERIFIED.md."
    )
    return MacrThreshold(
        technology=technology,
        year=year,
        value=table[key],
        is_placeholder=not verified,
        note=note,
    )


def compute_macr(inputs: MacrInputs) -> tuple[float, str]:
    """Compute the MACR from the supplied evidence.

    Returns ``(ratio, basis_description)``.

    * ``SUPPLIER_CERTIFICATION`` builds the ratio from the component cost
      schedule: ``(total direct costs - PFE-attributable costs) / total direct
      costs``. Components without a supplier certification are treated
      conservatively as **fully PFE-attributable**, which is the diligence
      default a tax-equity investor will insist on.
    * ``DEFAULT_COST_TABLE`` is the DOE-derived safe harbor. The real tables are
      not shipped; the code path exists and refuses to guess.
    * ``INTERIM_SAFE_HARBOR`` treats a qualifying pre-effective-date binding
      contract as satisfying the test.
    * ``USER_ASSERTED`` takes the modeller's number.
    """
    if inputs.method is MacrMethod.USER_ASSERTED:
        assert inputs.asserted_ratio is not None  # enforced by MacrInputs
        return inputs.asserted_ratio, (
            f"MACR asserted by the modeller at {inputs.asserted_ratio:.1%}"
            + (f" ({inputs.basis_note})" if inputs.basis_note else "")
        )

    if inputs.method is MacrMethod.INTERIM_SAFE_HARBOR:
        if inputs.asserted_ratio is not None:
            return inputs.asserted_ratio, (
                "Interim safe harbor (Notice 2026-15) relied upon, with an "
                f"asserted ratio of {inputs.asserted_ratio:.1%}."
            )
        return 1.0, (
            "Interim safe harbor (Notice 2026-15) relied upon: property "
            "acquired under a binding written contract predating the "
            f"{FEOC_EFFECTIVE_DATE.isoformat()} effective date is treated as "
            "satisfying the material assistance requirement."
        )

    if inputs.method is MacrMethod.DEFAULT_COST_TABLE:
        if inputs.asserted_ratio is None:
            raise NotImplementedError(
                "The DOE-derived default cost tables published with IRS Notice "
                "2026-15 are not shipped with this build (see UNVERIFIED.md). "
                "Supply asserted_ratio, or use MacrMethod.SUPPLIER_CERTIFICATION "
                "with a component cost schedule."
            )
        return inputs.asserted_ratio, (
            "DOE-derived default cost table relied upon; ratio supplied by the "
            "caller because the tables are not shipped."
        )

    # SUPPLIER_CERTIFICATION - actual cost build-up.
    total = sum(c.total_direct_cost for c in inputs.components)
    if total <= 0:
        raise ValueError("Component schedule has zero total direct cost")
    excluded = sum(_pfe_cost(c) for c in inputs.components)
    ratio = (total - excluded) / total
    uncertified = [c.name for c in inputs.components if not c.supplier_certification_obtained]
    basis = (
        f"Cost build-up over {len(inputs.components)} components: "
        f"{total - excluded:,.0f} of {total:,.0f} total direct costs are not "
        f"attributable to a prohibited foreign entity."
    )
    if uncertified:
        basis += (
            " Components without a supplier certification were treated as fully "
            "PFE-attributable: " + ", ".join(uncertified) + "."
        )
    return ratio, basis


def _pfe_cost(component: ComponentCost) -> float:
    """PFE-attributable cost of a component, conservatively determined."""
    if not component.supplier_certification_obtained:
        return component.total_direct_cost
    return component.pfe_attributable_cost


def assess_feoc(project: TaxProject) -> FeocResult:
    """Run the MACR gate for one project.

    The applicable year is the **placed-in-service** year, which is the year the
    §48E credit is determined. (For §45X eligible components the statute tests
    the year of *sale*; Structura models facilities, not component manufacture,
    so PIS year is used and the simplification is declared in ``UNVERIFIED.md``.)

    A failure returns ``passes=False`` with a reason. Callers must treat that as
    **credit ineligibility**, not a warning.
    """
    steps: list[DeterminationStep] = []
    citations = ["feoc-effective-date", "notice-2026-15-macr", "macr-thresholds"]
    year = project.placed_in_service_date.year

    if project.placed_in_service_date < FEOC_EFFECTIVE_DATE:
        steps.append(
            DeterminationStep(
                label="FEOC / material assistance",
                outcome="not applicable",
                detail=(
                    f"FEOC restrictions take effect "
                    f"{FEOC_EFFECTIVE_DATE.isoformat()}; this facility is placed "
                    f"in service {project.placed_in_service_date.isoformat()}."
                ),
                citation_ids=("feoc-effective-date",),
            )
        )
        return FeocResult(
            applies=False,
            passes=True,
            macr=None,
            threshold=None,
            threshold_is_placeholder=False,
            method=None,
            applicable_year=year,
            reason="FEOC restrictions not yet in effect for this project.",
            steps=tuple(steps),
            citation_ids=("feoc-effective-date",),
        )

    flags = project.foreign_entity_flags
    if not flags.received_material_assistance_from_pfe:
        steps.append(
            DeterminationStep(
                label="FEOC / material assistance",
                outcome="passes",
                detail=(
                    "The taxpayer affirmatively represents that no material "
                    "assistance was received from a prohibited foreign entity, "
                    "so the Material Assistance Cost Ratio is 100%."
                ),
                citation_ids=("notice-2026-15-macr",),
            )
        )
        threshold = macr_threshold(project.technology, year)
        return FeocResult(
            applies=True,
            passes=True,
            macr=1.0,
            threshold=threshold.value,
            threshold_is_placeholder=threshold.is_placeholder,
            method=None,
            applicable_year=year,
            reason="No material assistance from a prohibited foreign entity.",
            steps=tuple(steps),
            citation_ids=tuple(citations),
        )

    if project.macr_inputs is None:
        steps.append(
            DeterminationStep(
                label="FEOC / Material Assistance Cost Ratio",
                outcome="FAILS - cannot be established",
                detail=(
                    "The project represents that it received material assistance "
                    "from a prohibited foreign entity but supplied no MACR "
                    "evidence. Under OBBBA §70512 the credit is denied unless "
                    "the ratio is established."
                ),
                citation_ids=("macr-failure-is-disqualifying",),
            )
        )
        citations.append("macr-failure-is-disqualifying")
        return FeocResult(
            applies=True,
            passes=False,
            macr=None,
            threshold=None,
            threshold_is_placeholder=False,
            method=None,
            applicable_year=year,
            reason=(
                "No Material Assistance Cost Ratio evidence supplied for a "
                "project that received material assistance from a prohibited "
                "foreign entity."
            ),
            steps=tuple(steps),
            citation_ids=tuple(citations),
        )

    ratio, basis = compute_macr(project.macr_inputs)
    threshold = macr_threshold(project.technology, year)
    passes = ratio >= threshold.value

    steps.append(
        DeterminationStep(
            label="Material Assistance Cost Ratio",
            outcome=f"{ratio:.1%}",
            detail=basis,
            citation_ids=("notice-2026-15-macr",),
        )
    )
    steps.append(
        DeterminationStep(
            label=f"MACR threshold, {project.technology.value} CY{year}",
            outcome="PASS" if passes else "FAIL - credit denied",
            detail=(
                f"Required MACR is {threshold.value:.0%}; the project achieves "
                f"{ratio:.1%}. {threshold.note}"
            ),
            citation_ids=("macr-thresholds", "macr-failure-is-disqualifying"),
        )
    )
    citations.append("macr-failure-is-disqualifying")

    reason = (
        f"MACR of {ratio:.1%} meets the {threshold.value:.0%} threshold for "
        f"{project.technology.value} in CY{year}."
        if passes
        else f"MACR of {ratio:.1%} falls below the {threshold.value:.0%} "
        f"threshold for {project.technology.value} in CY{year}. Under OBBBA "
        f"§70512 the credit is DENIED."
    )

    return FeocResult(
        applies=True,
        passes=passes,
        macr=ratio,
        threshold=threshold.value,
        threshold_is_placeholder=threshold.is_placeholder,
        method=project.macr_inputs.method,
        applicable_year=year,
        reason=reason,
        steps=tuple(steps),
        citation_ids=tuple(citations),
    )


def transfer_to_foreign_entity_prohibited(
    credit_section: CreditSection,
    transferee_status: ForeignEntityStatus,
    taxable_year_begin: date,
) -> tuple[bool, str]:
    """§70512(h): may this credit be transferred to this counterparty?

    Returns ``(prohibited, reason)``.

    The prohibition covers §45Q, §45X, §45Y, §45Z and §48E credits, bars only a
    **specified foreign entity** within the meaning of §7701(a)(51)(B), and is
    effective for **taxable years beginning after 2025-07-04** - so a
    calendar-year taxpayer is first tested on 2026-01-01.

    Note the asymmetry a practitioner will check for: a *foreign-influenced
    entity* under §7701(a)(51)(D) is a different (and, for the transfer ban, not
    directly named) category. Structura does not extend the ban to it.
    """
    if taxable_year_begin <= SECTION_70512H_EFFECTIVE_FOR_TY_BEGINNING_AFTER:
        return (
            False,
            f"§70512(h) applies to taxable years beginning after "
            f"{SECTION_70512H_EFFECTIVE_FOR_TY_BEGINNING_AFTER.isoformat()}; "
            f"this taxable year began {taxable_year_begin.isoformat()}.",
        )
    if credit_section not in SECTION_70512H_PROHIBITED_SECTIONS:
        return (
            False,
            f"§70512(h) names §45Q, §45X, §45Y, §45Z and §48E; this is "
            f"§{credit_section.value}.",
        )
    if transferee_status is not ForeignEntityStatus.SPECIFIED_FOREIGN_ENTITY:
        return (
            False,
            f"The transferee is not a specified foreign entity within the "
            f"meaning of §7701(a)(51)(B) (status: {transferee_status.value}).",
        )
    return (
        True,
        f"§70512(h) PROHIBITS the transfer of a §{credit_section.value} credit "
        f"to a specified foreign entity (§7701(a)(51)(B)) for a taxable year "
        f"beginning {taxable_year_begin.isoformat()}.",
    )
