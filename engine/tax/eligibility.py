"""§48E ITC and §45Y PTC eligibility, rate build-up and phase-down.

This is the module the whole product hangs off. SPEC §2.1, verified 2026-08-06.

**OBBBA (P.L. 119-21, enacted 2025-07-04) did not repeal §48E/§45Y. It
bifurcated them.**

**Wind and solar** must have **begun construction on or before 2026-07-04**.
Projects that did keep the standard **four-year continuity window** (a project
beginning construction in 2026 has until 2030-12-31 to be placed in service).
Projects that did not have exactly one route left: they must be **placed in
service by 2027-12-31**. Miss both and the credit is **zero** - not reduced,
zero. Both paths are modelled and the result reports which one applies.

**Storage, geothermal, nuclear and hydro** were untouched by the accelerated
cliff. They keep **full §48E for construction begun through 2033**, then **75%
(2034)**, **50% (2035)**, and **zero from 2036**.

**Rate build-up** (§48E(a)(2), §48E(d)(3); §45Y(a)(2), §45Y(g)(9))::

    base 6%                                    (0.3 c/kWh for the PTC)
      x5 if prevailing wage and apprenticeship  -> 30%   (1.5 c/kWh)
      + 10 points domestic content              (or +10% of the PTC amount)
      + 10 points energy community              (or +10% of the PTC amount)
      x  phase-down percentage                  (non-wind/solar, 2034+)
      x  0 if the FEOC / MACR gate fails

The FEOC gate is multiplicative-by-zero on purpose: a MACR failure is a
disqualification, never a haircut (:mod:`engine.tax.feoc`).

**Product consequence, stated because it drives everything downstream (SPEC
§6.4): lead with storage.** Wind and solar's forward pipeline is now
safe-harboured inventory with a 2030 outside date; storage has a seven-year
runway.
"""

from __future__ import annotations

from engine.tax.adders import evaluate_adders
from engine.tax.begin_construction import assess_begin_construction
from engine.tax.constants import (
    ITC_BASE_RATE,
    NON_WIND_SOLAR_FULL_CREDIT_THROUGH_BOC_YEAR,
    NON_WIND_SOLAR_PHASE_DOWN,
    PLACEHOLDER_PTC_INFLATION_ADJUSTMENT,
    PTC_BASE_RATE_PER_KWH,
    PTC_CREDIT_PERIOD_YEARS,
    PWA_MULTIPLIER,
    WIND_SOLAR_BOC_DEADLINE,
    WIND_SOLAR_PIS_BACKSTOP,
)
from engine.tax.feoc import assess_feoc
from engine.tax.models import (
    AdderResult,
    BeginConstructionResult,
    CreditResult,
    CreditType,
    DeterminationStep,
    EligibilityPath,
    FeocResult,
    PhaseDownApplication,
    TaxProject,
    TaxScenario,
)

__all__ = [
    "phase_down_percentage",
    "ptc_rate_per_kwh",
    "evaluate_eligibility",
]

_MWH_TO_KWH = 1_000.0


def phase_down_percentage(boc_year: int) -> float:
    """§48E(e) phase-down for storage/geothermal/nuclear/hydro.

    Keyed on the **begin-construction** year: full credit through 2033, 75% for
    2034, 50% for 2035, zero from 2036.
    """
    if boc_year <= NON_WIND_SOLAR_FULL_CREDIT_THROUGH_BOC_YEAR:
        return 1.0
    years = sorted(NON_WIND_SOLAR_PHASE_DOWN)
    if boc_year >= years[-1]:
        return NON_WIND_SOLAR_PHASE_DOWN[years[-1]]
    return NON_WIND_SOLAR_PHASE_DOWN[boc_year]


def ptc_rate_per_kwh(year: int, is_pwa_compliant: bool) -> float:
    """§45Y credit amount in US$/kWh for a given calendar year.

    ⚠️ The 0.3 c/kWh base amount and the 5x PWA multiplier are statutory and
    certain. The **annual inflation adjustment factor is not shipped** for any
    year after the 2022 base year - the IRS announces it each year and it was
    not sourced in this build.

    Raises
    ------
    NotImplementedError
        If no adjustment factor is available for ``year``. Refusing to guess is
        deliberate: a fabricated PTC rate would flow straight into an IRR.
    """
    factor = PLACEHOLDER_PTC_INFLATION_ADJUSTMENT.get(year)
    if factor is None:
        raise NotImplementedError(
            f"No §45Y(c) inflation adjustment factor is available for {year}. "
            f"The statutory base amount (0.3 c/kWh) and the 5x PWA multiplier "
            f"are implemented, but the annual factor must be supplied before a "
            f"PTC rate can be quoted. See UNVERIFIED.md."
        )
    rate = PTC_BASE_RATE_PER_KWH * factor
    if is_pwa_compliant:
        rate *= PWA_MULTIPLIER
    # §45Y(c)(1) rounds to the nearest 0.05 cent, i.e. $0.0005.
    return round(rate / 0.0005) * 0.0005


def evaluate_eligibility(
    project: TaxProject,
    scenario: TaxScenario | None = None,
    *,
    begin_construction: BeginConstructionResult | None = None,
    feoc: FeocResult | None = None,
) -> CreditResult:
    """Full §48E/§45Y determination for one project.

    ``begin_construction`` and ``feoc`` may be passed in when the caller has
    already run them (as :func:`engine.tax.compute_tax` does) so the audit trail
    is not duplicated; otherwise they are computed here.

    The returned :class:`~engine.tax.models.CreditResult` carries an ordered
    ``steps`` list explaining **why** the answer is what it is - the narrator
    (SPEC §6.6) renders it and is forbidden from adding to it.
    """
    scenario = scenario or TaxScenario()
    boc_result = begin_construction or assess_begin_construction(project, scenario)
    feoc_result = feoc if feoc is not None else assess_feoc(project)

    steps: list[DeterminationStep] = []
    citations: list[str] = ["obbba-bifurcation", "base-and-pwa-rate"]
    warnings: list[str] = []

    # ------------------------------------------------------------------
    # 1. Which statutory path, if any, carries this project?
    # ------------------------------------------------------------------
    path, path_step, path_citations = _determine_path(project, boc_result)
    steps.append(path_step)
    citations.extend(path_citations)

    if path is EligibilityPath.NONE:
        return _zero_credit(
            project,
            path,
            steps,
            citations,
            disqualification_reason=path_step.detail,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # 2. FEOC / MACR gate - pass/fail, and failure is fatal.
    # ------------------------------------------------------------------
    citations.extend(feoc_result.citation_ids)
    if not feoc_result.passes:
        steps.append(
            DeterminationStep(
                label="FEOC gate",
                outcome="FAILED - credit denied",
                detail=feoc_result.reason,
                citation_ids=("macr-failure-is-disqualifying",),
            )
        )
        return _zero_credit(
            project,
            EligibilityPath.NONE,
            steps,
            citations,
            disqualification_reason=feoc_result.reason,
            warnings=warnings,
        )
    if feoc_result.applies and feoc_result.threshold_is_placeholder:
        warnings.append(
            "The MACR threshold applied is a PLACEHOLDER, not sourced law. "
            "See UNVERIFIED.md before relying on the FEOC result."
        )

    # ------------------------------------------------------------------
    # 3. Base rate and the 5x PWA multiplier.
    # ------------------------------------------------------------------
    if project.credit_type is CreditType.ITC:
        base_rate = ITC_BASE_RATE * (PWA_MULTIPLIER if project.is_pwa_compliant else 1.0)
        rate_detail = (
            f"§48E energy percentage of {ITC_BASE_RATE:.0%}"
            + (
                f", multiplied by {PWA_MULTIPLIER:g} to {base_rate:.0%} because "
                f"the prevailing wage and apprenticeship requirements are met."
                if project.is_pwa_compliant
                else ". PWA requirements are NOT met, so the 5x multiplier is "
                "unavailable and the credit stays at the base rate."
            )
        )
    else:
        base_rate = ptc_rate_per_kwh(
            project.placed_in_service_date.year, project.is_pwa_compliant
        )
        citations.append("ptc-inflation-adjustment")
        citations.append("ptc-credit-period")
        rate_detail = (
            f"§45Y credit amount of ${base_rate:.4f}/kWh"
            + (
                " (base amount multiplied by five for PWA compliance)."
                if project.is_pwa_compliant
                else " (base amount; PWA requirements not met)."
            )
        )

    steps.append(
        DeterminationStep(
            label="Base rate",
            outcome=(
                f"{base_rate:.0%}"
                if project.credit_type is CreditType.ITC
                else f"${base_rate:.4f}/kWh"
            ),
            detail=rate_detail,
            citation_ids=("base-and-pwa-rate",),
        )
    )

    # ------------------------------------------------------------------
    # 4. Adders.
    # ------------------------------------------------------------------
    adders: tuple[AdderResult, ...] = evaluate_adders(project)
    for adder in adders:
        citations.extend(adder.citation_ids)
        steps.append(
            DeterminationStep(
                label=f"{adder.adder.value.replace('_', ' ').title()} adder",
                outcome="granted" if adder.granted else "denied",
                detail=adder.reason,
                citation_ids=adder.citation_ids,
            )
        )

    if project.credit_type is CreditType.ITC:
        adder_points = sum(a.itc_percentage_points for a in adders)
        gross_rate = base_rate + adder_points
    else:
        adder_uplift = sum(a.ptc_multiplier for a in adders)
        gross_rate = base_rate * (1.0 + adder_uplift)

    # ------------------------------------------------------------------
    # 5. Phase-down (non-wind/solar only, keyed on BOC year).
    # ------------------------------------------------------------------
    phase_pct = 1.0
    if path is EligibilityPath.NON_WIND_SOLAR_RUNWAY:
        boc_year = (
            project.begin_construction_date.year
            if project.begin_construction_date is not None
            else project.placed_in_service_date.year
        )
        phase_pct = phase_down_percentage(boc_year)
        citations.append("non-wind-solar-runway")
        steps.append(
            DeterminationStep(
                label="§48E(e) phase-down",
                outcome=f"{phase_pct:.0%} of the otherwise-allowable credit",
                detail=(
                    f"{project.technology.value.title()} keeps the full §48E "
                    f"credit for construction begun through "
                    f"{NON_WIND_SOLAR_FULL_CREDIT_THROUGH_BOC_YEAR}, then 75% "
                    f"(2034), 50% (2035) and zero from 2036. Construction began "
                    f"in {boc_year}."
                ),
                citation_ids=("non-wind-solar-runway", "phase-down-application"),
            )
        )
        citations.append("phase-down-application")

    if scenario.phase_down_application is PhaseDownApplication.ALL_CREDIT:
        final_rate = gross_rate * phase_pct
    else:
        # BASE_ONLY: haircut the base rate, leave the bonus amounts whole.
        if project.credit_type is CreditType.ITC:
            adder_points = sum(a.itc_percentage_points for a in adders)
            final_rate = base_rate * phase_pct + adder_points
        else:
            adder_uplift = sum(a.ptc_multiplier for a in adders)
            final_rate = base_rate * phase_pct * (1.0 + adder_uplift)

    eligible = final_rate > 0.0
    if not eligible:
        steps.append(
            DeterminationStep(
                label="Result",
                outcome="ZERO credit",
                detail=(
                    "The phase-down percentage for this begin-construction year "
                    "is zero."
                ),
                citation_ids=("non-wind-solar-runway",),
            )
        )

    # ------------------------------------------------------------------
    # 6. Money.
    # ------------------------------------------------------------------
    if project.credit_type is CreditType.ITC:
        credit_amount = final_rate * project.itc_eligible_basis
        annual_credit = 0.0
        steps.append(
            DeterminationStep(
                label="Credit",
                outcome=f"{final_rate:.1%} of eligible basis = ${credit_amount:,.0f}",
                detail=(
                    f"Eligible basis of ${project.itc_eligible_basis:,.0f} at a "
                    f"final rate of {final_rate:.1%}."
                ),
                citation_ids=("base-and-pwa-rate",),
            )
        )
    else:
        annual_credit = final_rate * project.annual_production_mwh * _MWH_TO_KWH
        credit_amount = annual_credit * PTC_CREDIT_PERIOD_YEARS
        steps.append(
            DeterminationStep(
                label="Credit",
                outcome=(
                    f"${final_rate:.4f}/kWh x "
                    f"{project.annual_production_mwh:,.0f} MWh/yr = "
                    f"${annual_credit:,.0f}/yr"
                ),
                detail=(
                    f"Nominal total of ${credit_amount:,.0f} over the "
                    f"{PTC_CREDIT_PERIOD_YEARS}-year §45Y credit period."
                ),
                citation_ids=("ptc-credit-period",),
            )
        )

    return CreditResult(
        credit_type=project.credit_type,
        credit_section=project.credit_section,
        eligible=eligible,
        path=path,
        base_rate=base_rate,
        pwa_applied=project.is_pwa_compliant,
        adders=adders,
        gross_rate=gross_rate,
        phase_down_pct=phase_pct,
        final_rate=final_rate,
        credit_amount=credit_amount,
        annual_credit_amount=annual_credit,
        credit_period_years=PTC_CREDIT_PERIOD_YEARS,
        disqualification_reason="",
        steps=tuple(steps),
        citation_ids=tuple(dict.fromkeys(citations)),
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Path determination - the heart of SPEC §2.1
# ---------------------------------------------------------------------------


def _determine_path(
    project: TaxProject, boc: BeginConstructionResult
) -> tuple[EligibilityPath, DeterminationStep, tuple[str, ...]]:
    """Which statutory route carries this project - or none of them."""
    if not project.technology.is_wind_or_solar:
        return (
            EligibilityPath.NON_WIND_SOLAR_RUNWAY,
            DeterminationStep(
                label="Statutory path",
                outcome="§48E runway (not subject to the wind/solar cliff)",
                detail=(
                    f"{project.technology.value.title()} was untouched by the "
                    f"OBBBA accelerated cliff. Full §48E for construction begun "
                    f"through {NON_WIND_SOLAR_FULL_CREDIT_THROUGH_BOC_YEAR}, "
                    f"phasing down thereafter."
                ),
                citation_ids=("obbba-bifurcation", "non-wind-solar-runway"),
            ),
            ("non-wind-solar-runway",),
        )

    # --- wind and solar ---------------------------------------------------
    boc_date = boc.begin_construction_date if boc.established else None
    if boc_date is not None and boc_date <= WIND_SOLAR_BOC_DEADLINE:
        return (
            EligibilityPath.WIND_SOLAR_BEGIN_CONSTRUCTION,
            DeterminationStep(
                label="Statutory path",
                outcome="begin-construction path (four-year continuity window)",
                detail=(
                    f"Construction began {boc_date.isoformat()}, on or before "
                    f"the {WIND_SOLAR_BOC_DEADLINE.isoformat()} deadline, by the "
                    f"{'5% cost safe harbor' if boc.method.value.startswith('five') else 'Physical Work Test'}. "
                    f"The facility must be placed in service by "
                    f"{boc.continuity_deadline.isoformat() if boc.continuity_deadline else 'n/a'}."
                ),
                citation_ids=("wind-solar-boc-cliff", "continuity-safe-harbor"),
            ),
            ("wind-solar-boc-cliff", "continuity-safe-harbor"),
        )

    # Did not (or could not) begin construction in time. One route left.
    if project.placed_in_service_date <= WIND_SOLAR_PIS_BACKSTOP:
        return (
            EligibilityPath.WIND_SOLAR_PIS_BACKSTOP,
            DeterminationStep(
                label="Statutory path",
                outcome="placed-in-service backstop",
                detail=(
                    f"Begin construction was not established on or before "
                    f"{WIND_SOLAR_BOC_DEADLINE.isoformat()} ({boc.reason}). The "
                    f"project nevertheless qualifies because it is placed in "
                    f"service {project.placed_in_service_date.isoformat()}, on "
                    f"or before the {WIND_SOLAR_PIS_BACKSTOP.isoformat()} "
                    f"backstop."
                ),
                citation_ids=("wind-solar-pis-backstop",),
            ),
            ("wind-solar-boc-cliff", "wind-solar-pis-backstop"),
        )

    return (
        EligibilityPath.NONE,
        DeterminationStep(
            label="Statutory path",
            outcome="NONE - zero credit",
            detail=(
                f"Begin construction was not established on or before "
                f"{WIND_SOLAR_BOC_DEADLINE.isoformat()} ({boc.reason}), and the "
                f"projected placed-in-service date of "
                f"{project.placed_in_service_date.isoformat()} is after the "
                f"{WIND_SOLAR_PIS_BACKSTOP.isoformat()} backstop. Under OBBBA "
                f"this wind/solar facility receives NO §48E/§45Y credit."
            ),
            citation_ids=("wind-solar-boc-cliff", "wind-solar-pis-backstop"),
        ),
        ("wind-solar-boc-cliff", "wind-solar-pis-backstop"),
    )


def _zero_credit(
    project: TaxProject,
    path: EligibilityPath,
    steps: list[DeterminationStep],
    citations: list[str],
    *,
    disqualification_reason: str,
    warnings: list[str],
) -> CreditResult:
    """Build a zero-credit result that still explains itself fully."""
    return CreditResult(
        credit_type=project.credit_type,
        credit_section=project.credit_section,
        eligible=False,
        path=path,
        base_rate=0.0,
        pwa_applied=project.is_pwa_compliant,
        adders=(),
        gross_rate=0.0,
        phase_down_pct=0.0,
        final_rate=0.0,
        credit_amount=0.0,
        annual_credit_amount=0.0,
        credit_period_years=PTC_CREDIT_PERIOD_YEARS,
        disqualification_reason=disqualification_reason,
        steps=tuple(steps),
        citation_ids=tuple(dict.fromkeys(citations)),
        warnings=tuple(warnings),
    )
