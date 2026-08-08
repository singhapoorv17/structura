"""Request -> engine inputs.

Everything starts from a calibrated :class:`engine.reference_deals.ReferenceDeal`
— a complete, internally consistent capital structure — and the overrides are
applied on top with :func:`dataclasses.replace`. Nothing is constructed from
scratch, because a bare ``ProjectInputs()`` is not a deal: it has no tax facts,
no sponsor profile and no investor commitments, and it would produce exactly the
kind of unbelievable number the calibration work existed to eliminate.

The honest consequence, and it is stated in the response rather than hidden:
**overriding a reference deal does not re-solve its capital structure.** The
tax-equity cheque, the preferred commitment, the DRO caps and the gearing cap
are fixed dollar amounts chosen so that sources equal uses on the *base* deal.
Move the capex and they no longer do. The engine detects that itself
(``StructureComparison.funding_failures``) and this module adds a warning saying
what happened, so nobody reads a re-scaled deal as if it were calibrated.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from engine.defaults import Technology as EngineTechnology
from engine.reference_deals import (
    REFERENCE_DEALS,
    ReferenceDeal,
    reference_deal,
    reference_deal_keys,
)
from engine.tax import MacrInputs, MacrMethod, Technology as TaxTechnology
from engine.tax.enums import Notice202542Status

from lib_api.errors import ApiError
from lib_api.validate import MAX_PERIODS

__all__ = [
    "DEFAULT_DEAL_KEY",
    "TECHNOLOGY_MAP",
    "deal_keys",
    "resolve_deal",
    "apply_overrides",
]

#: Used when the caller sends no ``deal_key``. SPEC §6.4 says lead with storage,
#: and it is the deal the calibration was anchored on.
DEFAULT_DEAL_KEY = "storage_bess_contracted"

#: contract technology -> (engine technology, tax technology, credit-eligible).
#: ``engine.tax`` carries no DATA_CENTER member because no credit section
#: reaches a powered shell; the reference deal expresses that as
#: ``eligible_basis=0`` on an otherwise inert tag, and so does this map.
TECHNOLOGY_MAP: Mapping[str, tuple[EngineTechnology, TaxTechnology, bool]] = {
    "STORAGE": (EngineTechnology.STORAGE, TaxTechnology.STORAGE, True),
    "SOLAR": (EngineTechnology.SOLAR, TaxTechnology.SOLAR, True),
    "WIND": (EngineTechnology.WIND, TaxTechnology.WIND, True),
    "DATA_CENTER": (EngineTechnology.DATA_CENTER, TaxTechnology.STORAGE, False),
}


def deal_keys() -> tuple[str, ...]:
    return reference_deal_keys()


def resolve_deal(deal_key: str | None) -> tuple[ReferenceDeal, list[str]]:
    """Look up the base deal, defaulting loudly rather than silently."""
    warnings: list[str] = []
    if deal_key is None:
        deal_key = DEFAULT_DEAL_KEY
        warnings.append(
            f"api: no 'deal_key' was supplied, so the run below starts from the "
            f"calibrated reference deal '{DEFAULT_DEAL_KEY}'. Every input not "
            f"named in 'overrides' is that deal's, including its tax-equity "
            f"cheque, sponsor tax profile and gearing cap."
        )
    try:
        return reference_deal(deal_key), warnings
    except KeyError as exc:  # pragma: no cover - validate.py checks first
        raise ApiError(str(exc), field="deal_key") from exc


def apply_overrides(
    deal: ReferenceDeal, overrides: Mapping[str, Any]
) -> tuple[ReferenceDeal, list[str]]:
    """Return a new :class:`ReferenceDeal` with the overrides applied.

    Also returns the warnings the caller must see about what the override did
    *not* do — chiefly that the capital structure was not re-solved.
    """
    warnings: list[str] = []
    if not overrides:
        return deal, warnings

    project = deal.project
    terms = deal.debt_terms
    tax_project = deal.tax_project
    scenario = deal.tax_scenario

    # -- project ---------------------------------------------------------
    if "capex" in overrides:
        project = replace(project, capex=overrides["capex"])
        tax_project = replace(tax_project, capex=overrides["capex"])
    if "opex_year1" in overrides:
        project = replace(project, opex_year1=overrides["opex_year1"])
    if "production_p50" in overrides:
        project = replace(project, production_p50=overrides["production_p50"])
    if "contracted_price" in overrides:
        project = replace(project, contracted_price=overrides["contracted_price"])
    if "contract_years" in overrides:
        project = replace(project, contract_years=overrides["contract_years"])
    if "project_life_years" in overrides:
        project = replace(project, project_life_years=overrides["project_life_years"])

    # -- debt ------------------------------------------------------------
    if "target_dscr" in overrides:
        terms = replace(terms, target_dscr=overrides["target_dscr"])
    if "interest_rate" in overrides:
        terms = replace(terms, interest_rate=overrides["interest_rate"])
    if "tenor_years" in overrides:
        terms = replace(terms, tenor_years=overrides["tenor_years"])

    # -- technology ------------------------------------------------------
    if "technology" in overrides:
        engine_tech, tax_tech, credit_eligible = TECHNOLOGY_MAP[
            overrides["technology"]
        ]
        project = replace(project, technology=engine_tech)
        tax_project = replace(
            tax_project,
            technology=tax_tech,
            eligible_basis=0.0 if not credit_eligible else None,
        )
        if not credit_eligible:
            warnings.append(
                "api: technology DATA_CENTER carries no §48E eligible basis "
                "(eligible_basis=0). A powered shell is neither a qualified "
                "clean electricity facility nor energy storage technology, so "
                "the selector's credit gate will disqualify the direct "
                "transfer and the T-flip. That is the correct answer, not a "
                "modelling gap."
            )
        else:
            warnings.append(
                "api: technology was overridden. The eligible basis reverts to "
                "full capex and the depreciation method, sponsor tax profile "
                "and investor commitments remain those of the base reference "
                "deal - they were NOT re-derived for the new technology."
            )

    # -- tax facts -------------------------------------------------------
    if "placed_in_service_date" in overrides:
        pis = overrides["placed_in_service_date"]
        tax_project = replace(tax_project, placed_in_service_date=pis)
        # COD and placed-in-service are the same event in every reference deal.
        # Moving one without the other would put the tax year and the cashflow
        # on different clocks, which is worse than moving both.
        project = replace(project, cod_date=pis)
        warnings.append(
            "api: 'placed_in_service_date' also moved the project's COD date - "
            "they are the same event in every reference deal. Construction "
            "months were left unchanged."
        )
    if "begin_construction_date" in overrides:
        tax_project = replace(
            tax_project, begin_construction_date=overrides["begin_construction_date"]
        )
    if "is_pwa_compliant" in overrides:
        tax_project = replace(
            tax_project, is_pwa_compliant=overrides["is_pwa_compliant"]
        )
    if "domestic_content_pct" in overrides:
        tax_project = replace(
            tax_project, domestic_content_pct=overrides["domestic_content_pct"]
        )
    if "energy_community" in overrides:
        tax_project = replace(
            tax_project, energy_community=overrides["energy_community"]
        )
    if "macr_ratio" in overrides:
        tax_project = replace(
            tax_project,
            macr_inputs=MacrInputs(
                method=MacrMethod.USER_ASSERTED,
                asserted_ratio=overrides["macr_ratio"],
                basis_note="Asserted through the Structura API.",
            ),
        )

    # -- scenario --------------------------------------------------------
    if "bonus_rate" in overrides:
        scenario = replace(scenario, bonus_rate=overrides["bonus_rate"])
    if "notice_2025_42_status" in overrides:
        scenario = replace(
            scenario,
            notice_2025_42_status=Notice202542Status(
                overrides["notice_2025_42_status"]
            ),
        )

    _guard_periods(project)

    warnings.append(
        f"api: {len(overrides)} override(s) were applied on top of reference "
        f"deal '{deal.key}' and its capital structure was NOT re-solved. The "
        f"tax-equity commitment, preferred commitment, deficit-restoration "
        f"caps and gearing cap are fixed dollar amounts calibrated to the base "
        f"deal, so sources may no longer equal uses. Any imbalance is reported "
        f"by the engine itself and appears in this response."
    )

    return (
        replace(
            deal,
            project=project,
            debt_terms=terms,
            tax_project=tax_project,
            tax_scenario=scenario,
        ),
        warnings,
    )


def _guard_periods(project) -> None:
    """The DoS guardrail: refuse a run that would build unbounded arrays."""
    periods = project.project_life_years * max(1, project.periods_per_year)
    if periods > MAX_PERIODS:
        raise ApiError(
            f"The requested project would run {periods:.0f} periods; the API "
            f"caps a single run at {MAX_PERIODS}.",
            field="project_life_years",
        )
    if project.construction_months > 120:
        raise ApiError(
            "Construction period exceeds the 120-month API cap.",
            field="project_life_years",
        )


#: Re-exported so ``/api/reference-deals`` does not have to import the engine
#: registry directly.
ALL_DEALS: Mapping[str, ReferenceDeal] = REFERENCE_DEALS
