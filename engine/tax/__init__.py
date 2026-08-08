"""``engine.tax`` - the current-law tax engine.

Implements the 2025-26 US federal regime for clean-electricity credits: the
OBBBA bifurcation of §48E/§45Y, the domestic content and energy community
adders, FEOC/MACR, begin-construction, depreciation with the §50(c)(3) basis
reduction, and §6418/§6417 monetisation. Every rule carries a citation and a
verified-on date.

Law state encoded here was verified on **2026-08-06**. Re-verify before use:
begin construction is in active litigation, and the FEOC guidance is expressly
interim.

Modules
-------
``constants``
    Every number, with its authority and confidence level. No magic numbers
    anywhere else.
``citations``
    The structured citation registry. ``get_all_citations()`` feeds the
    ``/current-law`` page.
``eligibility``
    §48E / §45Y eligibility, the wind/solar cliff and backstop, the non-wind/
    solar runway and phase-down, and the base/PWA rate build-up.
``adders``
    Domestic content (50% threshold in 2026) and energy community.
``feoc``
    Material Assistance Cost Ratio pass/fail, and §70512(h).
``begin_construction``
    5% cost safe harbor vs Physical Work Test, four-year continuity, and the
    *Oregon Environmental Council* vacatur as a toggleable scenario.
``depreciation``
    MACRS 5/15, straight line 5/15/20/39, bonus, and the §50(c)(3) 50% ITC
    basis reduction.
``transfer``
    §6418 transfer economics and §6417 direct pay.

Quick start
-----------
::

    from datetime import date
    from engine.tax import (
        BeginConstructionMethod, MacrInputs, MacrMethod,
        TaxProject, Technology, compute_tax,
    )

    project = TaxProject(
        technology=Technology.STORAGE,
        capacity_mw=100.0,
        capex=200_000_000.0,
        placed_in_service_date=date(2028, 6, 30),
        begin_construction_date=date(2026, 3, 1),
        begin_construction_method=BeginConstructionMethod.PHYSICAL_WORK_TEST,
        physical_work_commenced=True,
        is_pwa_compliant=True,
        domestic_content_pct=0.55,
        # A project that received material assistance from a prohibited foreign
        # entity must clear the MACR gate, so supply the evidence. Where there
        # was none, say so instead:
        #   foreign_entity_flags=ForeignEntityFlags(
        #       received_material_assistance_from_pfe=False)
        macr_inputs=MacrInputs(
            method=MacrMethod.USER_ASSERTED, asserted_ratio=0.70
        ),
    )
    result = compute_tax(project)
    print(result.credit.final_rate, result.credit.credit_amount)  # 0.40, $80m
    for step in result.steps:
        print(step)
    for warning in result.credit.warnings:
        print("!", warning)  # e.g. the MACR threshold is a PLACEHOLDER

Not advice. Illustrative modelling only.
"""

from __future__ import annotations

from engine.tax.adders import (
    domestic_content_adder,
    domestic_content_threshold,
    energy_community_adder,
    evaluate_adders,
)
from engine.tax.begin_construction import (
    assess_begin_construction,
    continuity_deadline,
    notice_2025_42_applies,
)
from engine.tax.citations import (
    Citation,
    citations_for_ids,
    get_all_citations,
    get_citation,
    unverified_citations,
)
from engine.tax.constants import LAW_VERIFIED_ON
from engine.tax.depreciation import build_schedule, recovery_percentages, reduced_basis
from engine.tax.eligibility import (
    evaluate_eligibility,
    phase_down_percentage,
    ptc_rate_per_kwh,
)
from engine.tax.enums import (
    AdderType,
    BeginConstructionMethod,
    Confidence,
    CreditSection,
    CreditType,
    DepreciationMethod,
    EligibilityPath,
    ForeignEntityStatus,
    MacrMethod,
    Notice202542Status,
    PhaseDownApplication,
    Technology,
)
from engine.tax.feoc import (
    assess_feoc,
    compute_macr,
    macr_threshold,
    transfer_to_foreign_entity_prohibited,
)
from engine.tax.models import (
    AdderResult,
    BeginConstructionResult,
    ComponentCost,
    CreditResult,
    DepreciationPeriod,
    DepreciationSchedule,
    DeterminationStep,
    FeocResult,
    ForeignEntityFlags,
    MacrInputs,
    TaxProject,
    TaxResult,
    TaxScenario,
    TransferResult,
)
from engine.tax.transfer import (
    default_transfer_price,
    is_direct_pay_eligible,
    model_transfer,
)

__all__ = [
    "LAW_VERIFIED_ON",
    "compute_tax",
    # enums
    "AdderType",
    "BeginConstructionMethod",
    "Confidence",
    "CreditSection",
    "CreditType",
    "DepreciationMethod",
    "EligibilityPath",
    "ForeignEntityStatus",
    "MacrMethod",
    "Notice202542Status",
    "PhaseDownApplication",
    "Technology",
    # models
    "AdderResult",
    "BeginConstructionResult",
    "Citation",
    "ComponentCost",
    "CreditResult",
    "DepreciationPeriod",
    "DepreciationSchedule",
    "DeterminationStep",
    "FeocResult",
    "ForeignEntityFlags",
    "MacrInputs",
    "TaxProject",
    "TaxResult",
    "TaxScenario",
    "TransferResult",
    # rules
    "assess_begin_construction",
    "assess_feoc",
    "build_schedule",
    "citations_for_ids",
    "compute_macr",
    "continuity_deadline",
    "default_transfer_price",
    "domestic_content_adder",
    "domestic_content_threshold",
    "energy_community_adder",
    "evaluate_adders",
    "evaluate_eligibility",
    "get_all_citations",
    "get_citation",
    "is_direct_pay_eligible",
    "macr_threshold",
    "model_transfer",
    "notice_2025_42_applies",
    "phase_down_percentage",
    "ptc_rate_per_kwh",
    "recovery_percentages",
    "reduced_basis",
    "transfer_to_foreign_entity_prohibited",
    "unverified_citations",
]


def compute_tax(
    project: TaxProject,
    scenario: TaxScenario | None = None,
    *,
    include_transfer: bool = True,
) -> TaxResult:
    """Run the whole current-law determination for one project.

    Order of operations mirrors how a tax lawyer reasons and how the audit trail
    reads:

    1. **Begin construction** - was it established, by which method, was that
       method available under the modelled litigation scenario, and does the
       four-year continuity window reach the placed-in-service date?
    2. **FEOC / MACR** - does the supply chain clear the material assistance
       gate? A failure here denies the credit outright.
    3. **Eligibility** - which statutory path applies, what is the rate after
       PWA, adders and any phase-down, and what is the credit worth?
    4. **Depreciation** - the §50(c)(3) reduced basis and the recovery schedule.
    5. **Transfer** - §6418 economics, subject to the §70512(h) gate.

    Passing ``include_transfer=False`` skips step 5 (a partnership-flip run does
    not need it).
    """
    scenario = scenario or TaxScenario()
    boc = assess_begin_construction(project, scenario)
    feoc = assess_feoc(project)
    credit = evaluate_eligibility(
        project, scenario, begin_construction=boc, feoc=feoc
    )
    itc_amount = credit.credit_amount if credit.credit_type is CreditType.ITC else 0.0
    depreciation = build_schedule(
        original_basis=project.capex,
        itc_amount=itc_amount,
        method=scenario.depreciation_method,
        bonus_rate=scenario.bonus_rate,
        start_year=project.placed_in_service_date.year,
    )
    transfer = model_transfer(project, credit) if include_transfer else None
    return TaxResult(
        project=project,
        scenario=scenario,
        begin_construction=boc,
        feoc=feoc,
        credit=credit,
        depreciation=depreciation,
        transfer=transfer,
    )
