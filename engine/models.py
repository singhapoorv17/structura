"""Input and output data structures for the Structura core engine.

Plain frozen dataclasses only - no pydantic, no web framework types. The engine
is a pure library; validation that belongs at the API boundary lives at the API
boundary (SPEC.md §6: "the web app is a thin shell over this").

Vocabulary used throughout (standard project-finance terminology):

CFADS
    Cash Flow Available for Debt Service. Operating revenue less operating
    expense less cash tax, before any financing item. It is the numerator of
    every coverage ratio in the model.
DSCR
    Debt Service Coverage Ratio = CFADS / (interest + scheduled principal) for
    the period. The primary sizing test.
LLCR / PLCR
    Loan Life / Project Life Coverage Ratio. See ``engine.debt``.
DSRA
    Debt Service Reserve Account. Cash trapped at COD (or built from operating
    cashflow) to cover a defined number of months of debt service.
IDC
    Interest During Construction. Interest accrued on construction drawings and
    capitalised into project cost.
Gearing
    Debt / total project cost (funded basis, i.e. including IDC and fees).
Tail
    Project life minus debt tenor. Lenders require the asset to outlive the loan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Sequence

from engine.defaults import (
    CASH_SWEEP_PCT,
    COMMITMENT_FEE,
    DSRA_MONTHS,
    FEDERAL_TAX_RATE,
    MAX_GEARING,
    MONTHS_PER_YEAR,
    TAIL_YEARS,
    UPFRONT_FEE,
    Technology,
)

__all__ = [
    "Technology",
    "AmortizationStyle",
    "TaxTreatment",
    "ProductionCase",
    "SizingConstraint",
    "ProjectInputs",
    "DebtTerms",
    "CashflowResult",
    "DebtResult",
    "ConstraintTest",
    "SizingResult",
    "ConstructionResult",
    "WaterfallResult",
    "ReturnsResult",
]


class AmortizationStyle(str, Enum):
    """How scheduled principal is shaped.

    SCULPTED
        Debt service is solved period by period so that DSCR equals the target
        exactly. The market-standard structure for contracted energy assets,
        because it extracts the maximum debt a given CFADS profile supports.
    LEVEL
        Constant total debt service (mortgage-style annuity). Debt is sized off
        the *minimum* CFADS period, so a lumpy CFADS profile leaves coverage
        unused in every other period.
    FIXED_PRINCIPAL
        Constant principal, declining interest, therefore declining total debt
        service. Front-loaded and correspondingly the least debt of the three.
    """

    SCULPTED = "sculpted"
    LEVEL = "level"
    FIXED_PRINCIPAL = "fixed_principal"


class TaxTreatment(str, Enum):
    """How project-level cash tax is handled inside CFADS.

    NONE
        CFADS is pre-tax (= EBITDA). The default, and the convention in most
        US renewable sizing work, because tax attributes sit in a tax-equity or
        transfer structure modelled above the project (Phases 2-3), not in the
        project's own debt sizing.
    PRE_DEBT
        Cash tax computed on EBITDA less book depreciation, ignoring the
        interest deduction. No circularity; slightly conservative (understates
        CFADS) because it throws away the interest tax shield.
    FULL
        Cash tax computed on EBITDA less depreciation less interest. Correct,
        but circular: interest depends on debt size, which depends on CFADS,
        which depends on tax. Resolved by fixed-point iteration in
        ``engine.circularity.solve_funding``.
    """

    NONE = "none"
    PRE_DEBT = "pre_debt"
    FULL = "full"


class ProductionCase(str, Enum):
    """Exceedance case used to drive the energy production series."""

    P50 = "p50"
    P90 = "p90"
    P99 = "p99"


class SizingConstraint(str, Enum):
    """The sizing tests the engine evaluates and reports on."""

    DSCR = "dscr"
    GEARING = "gearing"
    TENOR = "tenor"
    TAIL = "tail"
    LLCR = "llcr"
    PLCR = "plcr"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProjectInputs:
    """Everything about the asset, before any financing decision.

    Notes
    -----
    * ``periods_per_year`` of 1 gives annual periods, 2 gives semi-annual. The
      engine applies a simple nominal convention: the per-period interest rate
      is the annual rate divided by ``periods_per_year``, and an annual
      cashflow is split into equal sub-periods. There is no seasonality in
      Phase 1 (declared in PHASE1.md).
    * Contracted volume is a *share of production*, not a fixed MWh block. A
      fixed-volume PPA with a shortfall obligation is a Phase 2+ item.
    * Degradation compounds: year-n production = P * (1 - d)^(n-1).
    """

    name: str = "Unnamed project"
    technology: Technology = Technology.STORAGE

    capacity_mw: float = 100.0

    # --- capital cost and construction -------------------------------------
    capex: float = 200_000_000.0
    construction_months: int = 18
    cod_date: date = date(2027, 1, 1)
    #: Monthly capex spend weights over the construction period. ``None`` means
    #: a flat (straight-line) S-curve, which is the neutral assumption.
    capex_curve: tuple[float, ...] | None = None

    # --- operating cost -----------------------------------------------------
    opex_year1: float = 5_000_000.0
    opex_escalation: float = 0.025

    # --- production ---------------------------------------------------------
    production_p50: float = 400_000.0  # MWh in the first operating year
    production_p90: float | None = None
    production_p99: float | None = None
    production_case: ProductionCase = ProductionCase.P50
    degradation: float = 0.005

    # --- revenue ------------------------------------------------------------
    contracted_price: float = 70.0  # $/MWh in the first operating year
    contracted_share: float = 1.0  # fraction of production under contract
    contracted_escalation: float = 0.02
    #: Years the offtake runs. After expiry all volume prices at merchant.
    contract_years: float = 15.0
    merchant_price: float = 45.0  # $/MWh in the first operating year
    merchant_escalation: float = 0.02

    # --- tax ----------------------------------------------------------------
    tax_rate: float = FEDERAL_TAX_RATE.value
    tax_treatment: TaxTreatment = TaxTreatment.NONE
    #: Straight-line book depreciation life used when tax is modelled at the
    #: project level. MACRS and bonus depreciation are Phase 2 (`engine/tax/`).
    depreciation_years: float = 20.0

    # --- horizon ------------------------------------------------------------
    project_life_years: float = 25.0
    periods_per_year: int = 1

    def __post_init__(self) -> None:
        if self.periods_per_year not in (1, 2, 4, 12):
            raise ValueError("periods_per_year must be one of 1, 2, 4, 12")
        if not 0.0 <= self.contracted_share <= 1.0:
            raise ValueError("contracted_share must be between 0 and 1")
        if not 0.0 <= self.degradation < 1.0:
            raise ValueError("degradation must be in [0, 1)")
        if self.project_life_years <= 0:
            raise ValueError("project_life_years must be positive")
        if self.construction_months < 0:
            raise ValueError("construction_months cannot be negative")
        if self.capex_curve is not None:
            if len(self.capex_curve) != self.construction_months:
                raise ValueError(
                    "capex_curve must have one weight per construction month"
                )
            if any(w < 0 for w in self.capex_curve):
                raise ValueError("capex_curve weights must be non-negative")
            if sum(self.capex_curve) <= 0:
                raise ValueError("capex_curve weights must sum to a positive number")

    @property
    def operating_periods(self) -> int:
        """Number of model periods from COD to end of project life."""
        return int(round(self.project_life_years * self.periods_per_year))

    @property
    def production(self) -> float:
        """First-year production (MWh) for the selected exceedance case."""
        if self.production_case is ProductionCase.P50:
            return self.production_p50
        if self.production_case is ProductionCase.P90:
            if self.production_p90 is None:
                raise ValueError("production_p90 not supplied")
            return self.production_p90
        if self.production_p99 is None:
            raise ValueError("production_p99 not supplied")
        return self.production_p99

    def normalised_capex_curve(self) -> tuple[float, ...]:
        """Capex weights normalised to sum to 1.0, one per construction month."""
        if self.construction_months == 0:
            return ()
        if self.capex_curve is None:
            w = 1.0 / self.construction_months
            return tuple(w for _ in range(self.construction_months))
        total = sum(self.capex_curve)
        return tuple(x / total for x in self.capex_curve)


@dataclass(frozen=True, slots=True)
class DebtTerms:
    """Senior debt terms and the credit tests the facility must satisfy.

    ``target_dscr`` accepts a scalar (constant target) or a sequence with one
    entry per debt period (time-varying target). Time-varying targets are real
    market practice: a deal with a merchant tail is commonly sculpted to, say,
    1.30x while contracted and 1.60x once the PPA rolls off.
    """

    target_dscr: float | Sequence[float] = 1.30
    tenor_years: float = 18.0
    #: All-in nominal annual interest rate (base + spread), decimal.
    interest_rate: float = 0.0575
    upfront_fee: float = UPFRONT_FEE.value
    commitment_fee: float = COMMITMENT_FEE.value
    amortization: AmortizationStyle = AmortizationStyle.SCULPTED
    grace_period_months: int = 0
    max_gearing: float = MAX_GEARING.value
    #: Hard DSCR floor for the covenant test. Defaults to the sizing target.
    min_dscr: float | None = None
    tail_years: float = TAIL_YEARS.value
    dsra_months: float = DSRA_MONTHS.value
    #: True sizes the DSRA against the *next* period's debt service (the market
    #: standard "forward-looking" reserve); False uses the current period's.
    dsra_forward_looking: bool = True
    cash_sweep_pct: float = CASH_SWEEP_PCT.value
    min_llcr: float | None = None
    min_plcr: float | None = None
    #: True finances the initial DSRA from the debt facility; False from equity.
    dsra_debt_funded: bool = False

    def __post_init__(self) -> None:
        if self.tenor_years <= 0:
            raise ValueError("tenor_years must be positive")
        if self.interest_rate < 0:
            raise ValueError("interest_rate cannot be negative")
        if not 0.0 < self.max_gearing <= 1.0:
            raise ValueError("max_gearing must be in (0, 1]")
        if not 0.0 <= self.cash_sweep_pct <= 1.0:
            raise ValueError("cash_sweep_pct must be in [0, 1]")
        if self.grace_period_months < 0:
            raise ValueError("grace_period_months cannot be negative")
        if self.dsra_months < 0:
            raise ValueError("dsra_months cannot be negative")

    def periods(self, periods_per_year: int) -> int:
        """Number of debt periods in the tenor."""
        return int(round(self.tenor_years * periods_per_year))

    def rate_per_period(self, periods_per_year: int) -> float:
        """Nominal annual rate divided by periods per year (money-market style).

        Project-finance credit agreements quote a margin over a periodic index
        (SOFR fixings), so a simple nominal division is the right convention
        here - not an effective-annual de-compounding.
        """
        return self.interest_rate / periods_per_year

    def grace_periods(self, periods_per_year: int) -> int:
        """Grace period expressed in model periods (rounded down, never > tenor).

        A grace period is interest-only: interest is paid current out of CFADS,
        principal repayment is deferred. Interest *capitalisation* during
        operations is not modelled in Phase 1.
        """
        g = int(self.grace_period_months * periods_per_year // MONTHS_PER_YEAR)
        return min(g, self.periods(periods_per_year))

    def dscr_profile(self, n_periods: int) -> tuple[float, ...]:
        """Expand ``target_dscr`` to one value per debt period."""
        if isinstance(self.target_dscr, (int, float)):
            value = float(self.target_dscr)
            if value <= 0:
                raise ValueError("target_dscr must be positive")
            return tuple(value for _ in range(n_periods))
        profile = tuple(float(x) for x in self.target_dscr)
        if len(profile) != n_periods:
            raise ValueError(
                f"target_dscr has {len(profile)} entries but the tenor is "
                f"{n_periods} periods"
            )
        if any(x <= 0 for x in profile):
            raise ValueError("every target_dscr entry must be positive")
        return profile

    @property
    def covenant_dscr(self) -> float | None:
        """The DSCR covenant floor, if one is set."""
        if self.min_dscr is not None:
            return self.min_dscr
        if isinstance(self.target_dscr, (int, float)):
            return float(self.target_dscr)
        return min(float(x) for x in self.target_dscr)


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CashflowResult:
    """Period-by-period operating model, from COD to end of project life."""

    periods_per_year: int
    period_index: tuple[int, ...]
    year_fraction: tuple[float, ...]
    production_mwh: tuple[float, ...]
    contracted_revenue: tuple[float, ...]
    merchant_revenue: tuple[float, ...]
    revenue: tuple[float, ...]
    opex: tuple[float, ...]
    ebitda: tuple[float, ...]
    depreciation: tuple[float, ...]
    cash_tax: tuple[float, ...]
    cfads: tuple[float, ...]
    tax_treatment: TaxTreatment

    @property
    def n_periods(self) -> int:
        return len(self.cfads)

    @property
    def merchant_share(self) -> float:
        """Merchant revenue as a share of total revenue over the whole model."""
        total = sum(self.revenue)
        return sum(self.merchant_revenue) / total if total else 0.0


@dataclass(frozen=True, slots=True)
class DebtResult:
    """A fully specified senior debt schedule.

    All series are indexed by debt period 1..n. ``opening_balance[0]`` equals
    the sized debt.
    """

    debt_size: float
    amortization: AmortizationStyle
    rate_per_period: float
    periods_per_year: int
    grace_periods: int
    opening_balance: tuple[float, ...]
    interest: tuple[float, ...]
    principal: tuple[float, ...]
    debt_service: tuple[float, ...]
    closing_balance: tuple[float, ...]
    cfads: tuple[float, ...]
    dscr: tuple[float, ...]
    target_dscr: tuple[float, ...]

    @property
    def n_periods(self) -> int:
        return len(self.debt_service)

    @property
    def min_dscr(self) -> float:
        """Minimum DSCR over periods that carry debt service."""
        live = [d for d, ds in zip(self.dscr, self.debt_service) if ds > 0]
        return min(live) if live else float("inf")

    @property
    def average_life_years(self) -> float:
        """Weighted average life of the loan, in years.

        WAL = sum(t_i * principal_i) / total principal. Lenders price and
        risk-weight off WAL rather than final maturity, because a sculpted
        amortisation profile can have a much shorter WAL than its tenor.
        """
        total = sum(self.principal)
        if total <= 0:
            return 0.0
        return sum(
            (i + 1) / self.periods_per_year * p for i, p in enumerate(self.principal)
        ) / total


@dataclass(frozen=True, slots=True)
class ConstraintTest:
    """The result of one sizing test, and whether it is the binding one."""

    constraint: SizingConstraint
    #: Debt quantum this test on its own would permit. ``inf`` if the test does
    #: not constrain quantum (e.g. a tail test that is simply pass/fail).
    implied_debt: float
    limit: float
    actual: float
    binds: bool
    passes: bool
    note: str = ""

    def describe(self) -> str:
        verdict = "BINDING" if self.binds else ("pass" if self.passes else "FAIL")
        return (
            f"{self.constraint.value}: actual {self.actual:,.4g} vs limit "
            f"{self.limit:,.4g} -> {verdict}"
            + (f" ({self.note})" if self.note else "")
        )


@dataclass(frozen=True, slots=True)
class SizingResult:
    """Sized debt plus the full set of credit tests and which one binds."""

    debt: DebtResult
    binding_constraint: SizingConstraint
    tests: tuple[ConstraintTest, ...]
    min_dscr: float
    llcr: float
    plcr: float
    llcr_series: tuple[float, ...]
    gearing: float
    tail_years: float
    total_project_cost: float
    dsra_target: tuple[float, ...]

    @property
    def debt_size(self) -> float:
        return self.debt.debt_size

    def test(self, constraint: SizingConstraint) -> ConstraintTest:
        for t in self.tests:
            if t.constraint is constraint:
                return t
        raise KeyError(constraint)

    def summary(self) -> str:
        """One-line practitioner summary of which test binds and by how much.

        Example: ``"Debt is DSCR-bound at 1.30x ($412.4m); gearing would have
        allowed 72.1% vs a 75.0% cap."``
        """
        binding = self.test(self.binding_constraint)
        head = (
            f"Debt is {self.binding_constraint.value.upper()}-bound at "
            f"{binding.actual:,.4g} (${self.debt.debt_size / 1e6:,.1f}m)."
        )
        slack: list[str] = []
        for t in self.tests:
            if t.binds or t.constraint is self.binding_constraint:
                continue
            if t.constraint is SizingConstraint.GEARING:
                slack.append(
                    f"gearing would have allowed {t.limit:.1%} vs an achieved "
                    f"{t.actual:.1%}"
                )
            elif t.constraint is SizingConstraint.DSCR:
                slack.append(
                    f"achieved min DSCR {t.actual:.3f}x against a {t.limit:.3f}x target"
                )
            elif t.constraint in (SizingConstraint.LLCR, SizingConstraint.PLCR):
                slack.append(f"{t.constraint.value.upper()} {t.actual:.3f}x")
            elif t.constraint is SizingConstraint.TAIL:
                slack.append(f"tail {t.actual:,.4g}y vs {t.limit:,.4g}y required")
        return head + (" " + "; ".join(slack) + "." if slack else "")


@dataclass(frozen=True, slots=True)
class ConstructionResult:
    """Resolved construction funding: the IDC / fee / DSRA circularity solved."""

    capex: float
    idc: float
    upfront_fee: float
    commitment_fee: float
    dsra_initial: float
    total_project_cost: float
    debt_at_cod: float
    equity_at_cod: float
    gearing: float
    debt_funded_costs: float
    monthly_debt_draw: tuple[float, ...]
    monthly_equity_draw: tuple[float, ...]
    monthly_interest: tuple[float, ...]
    monthly_commitment_fee: tuple[float, ...]
    monthly_closing_balance: tuple[float, ...]
    iterations: int
    converged: bool
    residual: float


@dataclass(frozen=True, slots=True)
class WaterfallResult:
    """Period-by-period cash waterfall from CFADS down to equity distributions.

    Cash conservation is an invariant: for every period,
    ``cfads + dsra_release == interest + principal_scheduled + sweep_prepayment
    + dsra_deposit + distributions`` to within ``CASH_TOLERANCE``.
    """

    period_index: tuple[int, ...]
    cfads: tuple[float, ...]
    interest: tuple[float, ...]
    principal_scheduled: tuple[float, ...]
    sweep_prepayment: tuple[float, ...]
    debt_service: tuple[float, ...]
    opening_balance: tuple[float, ...]
    closing_balance: tuple[float, ...]
    dsra_opening: tuple[float, ...]
    dsra_target: tuple[float, ...]
    dsra_deposit: tuple[float, ...]
    dsra_release: tuple[float, ...]
    dsra_closing: tuple[float, ...]
    mra_deposit: tuple[float, ...]
    mra_release: tuple[float, ...]
    mra_closing: tuple[float, ...]
    cash_available_for_distribution: tuple[float, ...]
    subordinated_service: tuple[float, ...]
    distributions: tuple[float, ...]
    dscr: tuple[float, ...]
    debt_service_shortfall: tuple[float, ...]
    covenant_breach: tuple[bool, ...]
    lockup: tuple[bool, ...]

    @property
    def n_periods(self) -> int:
        return len(self.cfads)

    @property
    def in_default(self) -> bool:
        """True if senior debt service was not met in full in any period."""
        return any(s > 0 for s in self.debt_service_shortfall)

    def sources(self, i: int) -> float:
        return self.cfads[i] + self.dsra_release[i] + self.mra_release[i]

    def uses(self, i: int) -> float:
        return (
            self.interest[i]
            + self.principal_scheduled[i]
            + self.sweep_prepayment[i]
            + self.dsra_deposit[i]
            + self.mra_deposit[i]
            + self.subordinated_service[i]
            + self.distributions[i]
        )


@dataclass(frozen=True, slots=True)
class ReturnsResult:
    """Return metrics for the sponsor and the effective cost of the facility."""

    equity_investment: float
    equity_cashflows: tuple[float, ...]
    equity_irr_pre_tax: float | None
    equity_irr_post_tax: float | None
    equity_npv: float
    equity_moic: float
    payback_years: float | None
    effective_cost_of_debt: float | None
    after_tax_cost_of_debt: float | None
    weighted_average_cost_of_capital: float | None
    dates: tuple[date, ...] = field(default_factory=tuple)
