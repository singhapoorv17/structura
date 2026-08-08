"""``engine.structures`` — the five live 2026 capital structures, and a selector.

The structure selector, and the partnership-tax layer underneath it.

Market context
--------------
Norton Rose Fulbright's *Cost of Capital: 2026 Outlook* (2026-01-29) records
five live structures — partnership flip, hybrid T-flip, preferred equity
partnership, direct transfer and sale-leaseback. Traditional tax equity, where
the investor retains the credits, was around 30% of the 2024 market and less in
2025; *"most current deals employ hybrid or preferred equity structures."*

The package models all five against the same project economics, and implements
the partnership-tax layer the comparison depends on: §704(b) capital accounts,
DRO caps, outside basis and §704(d) suspended losses live in
:mod:`engine.structures.partnership`.

Module map
----------
=========================== ==================================================
``partnership``             §704(b) capital accounts, DRO caps and
                            reallocation, outside basis, §704(d) suspended
                            losses, minimum gain chargeback, §50(c)(3).
``flip``                    Partnership flip: yield-based (solved with
                            ``scipy.optimize.brentq``) and fixed-date.
``tflip``                   T-flip / hybrid: a flip with a §6418 transfer
                            bolted on, and the flip-point movement it causes.
``preferred``               Preferred equity partnership: priority return,
                            redemption, then common.
``transfer``                Direct transfer under §6418.
``sale_leaseback``          Sale at FMV, rent solved to the lessor's yield,
                            true-lease screen, §50(d)(4) window.
``selector``                ``compare_structures`` — the headline feature.
``models``                  Configs, shared context, result types.
``defaults``                Market heuristics and tolerances. Every
                            unsourced number is a labelled placeholder.
=========================== ==================================================

Quick start
-----------
::

    from datetime import date
    from engine import DebtTerms, ProjectInputs
    from engine.tax import MacrInputs, MacrMethod, TaxProject
    from engine.tax import Technology as TaxTechnology
    from engine.structures import compare_structures

    comparison = compare_structures(
        ProjectInputs(),
        DebtTerms(),
        TaxProject(
            technology=TaxTechnology.STORAGE,
            capacity_mw=100.0,
            capex=200_000_000.0,
            placed_in_service_date=date(2027, 1, 1),
            begin_construction_date=date(2026, 3, 1),
            macr_inputs=MacrInputs(
                method=MacrMethod.USER_ASSERTED, asserted_ratio=0.80
            ),
        ),
    )

    for row in comparison.table():
        print(row["rank"], row["label"], row["sponsor_after_tax_irr"])
    print(comparison.why_this_wins.margin)

Not advice. Illustrative modelling only. Read
``LIMITS_STRUCTURES.md`` before relying on any number in here.
"""

from __future__ import annotations

from engine.structures import (
    defaults,
    flip,
    models,
    partnership,
    preferred,
    sale_leaseback,
    selector,
    tflip,
    transfer,
)
from engine.structures.flip import (
    FlipSolve,
    build_flip_partnership,
    flip_sharing_ratios,
    run_flip,
    solve_flip_point,
)
from engine.structures.models import (
    PROJECT_STRUCTURES,
    CashTiming,
    FlipConfig,
    FlipTrigger,
    PreferredConfig,
    ProjectEconomics,
    RiskFlag,
    RiskSeverity,
    SaleLeasebackConfig,
    SourcesAndUses,
    SponsorTaxProfile,
    StructureConfigs,
    StructureContext,
    StructureKey,
    StructureResult,
    TFlipConfig,
    TransferConfig,
    build_context,
    build_project_economics,
    build_sources_and_uses,
    irr_meaningfulness,
)
from engine.structures.partnership import (
    CapitalAccountBreach,
    PartnerPeriod,
    PartnerRole,
    PartnershipPeriod,
    PartnershipResult,
    PartnerTerms,
    PeriodInputs,
    ReallocationEvent,
    SharingRatios,
    assert_capital_account_integrity,
    run_partnership,
)
from engine.structures.preferred import run_preferred
from engine.structures.sale_leaseback import (
    TrueLeaseTests,
    run_sale_leaseback,
    solve_level_rent,
)
from engine.structures.selector import (
    Driver,
    RankedStructure,
    StructureComparison,
    WhyThisWins,
    compare_structures,
    run_all_structures,
)
from engine.structures.tflip import run_tflip
from engine.structures.transfer import run_transfer

__all__ = [
    # modules
    "defaults",
    "flip",
    "models",
    "partnership",
    "preferred",
    "sale_leaseback",
    "selector",
    "tflip",
    "transfer",
    # partnership core
    "CapitalAccountBreach",
    "PartnerPeriod",
    "PartnerRole",
    "PartnerTerms",
    "PartnershipPeriod",
    "PartnershipResult",
    "PeriodInputs",
    "ReallocationEvent",
    "SharingRatios",
    "assert_capital_account_integrity",
    "run_partnership",
    # context and configs
    "CashTiming",
    "FlipConfig",
    "FlipTrigger",
    "PreferredConfig",
    "ProjectEconomics",
    "RiskFlag",
    "RiskSeverity",
    "SaleLeasebackConfig",
    "SourcesAndUses",
    "SponsorTaxProfile",
    "StructureConfigs",
    "StructureContext",
    "PROJECT_STRUCTURES",
    "StructureKey",
    "StructureResult",
    "TFlipConfig",
    "TransferConfig",
    "build_context",
    "build_project_economics",
    "build_sources_and_uses",
    "irr_meaningfulness",
    # structures
    "FlipSolve",
    "TrueLeaseTests",
    "build_flip_partnership",
    "flip_sharing_ratios",
    "run_flip",
    "run_preferred",
    "run_sale_leaseback",
    "run_tflip",
    "run_transfer",
    "solve_flip_point",
    "solve_level_rent",
    # selector
    "Driver",
    "RankedStructure",
    "StructureComparison",
    "WhyThisWins",
    "compare_structures",
    "run_all_structures",
]

from engine.structures.equipment_lease import (  # noqa: E402
    EquipmentLeaseConfig,
    EquipmentLeaseResult,
    LeaseTranche,
    PartyLedger,
    run_equipment_lease,
)
