"""Resolving the construction-funding circularity: IDC <-> debt <-> fees <-> DSRA.

THE PROBLEM
-----------
Total project cost is not an input. It is::

    TPC = capex + upfront fee + commitment fee + IDC + initial DSRA

Every term after ``capex`` depends on the size of the debt:

* the **upfront fee** is a percentage of the facility;
* the **commitment fee** accrues on the *undrawn* facility, so it depends on
  both the facility size and the drawdown profile;
* **IDC** is interest on the construction drawings, capitalised - and the
  drawings are the debt-funded share of a cost base that itself includes IDC;
* the **initial DSRA** is months of debt service, which scales with the debt.

And the debt in turn depends on total project cost through the gearing cap::

    D = min( D_DSCR , max_gearing * TPC )

That is a genuine fixed point. In Excel it is solved by switching on iterative
calculation (which is exactly why the Phase 4 workbook must be written with
``iterate="1"``, SPEC.md §5). Here it is solved numerically and deterministically,
so the Python model never depends on Excel's solver.

THE SOLUTION - AN EXPLICIT TWO-LEVEL ITERATION SCHEDULE
-------------------------------------------------------
**Inner solve (draw solve).** For a *trial* facility size ``D``, everything
except the debt-funded share of capex is determined. Let ``X`` be the
debt-funded capex. Simulating the construction period month by month gives a
closing construction balance ``B(X; D)`` that is strictly increasing and
continuous in ``X``. Solve ``B(X; D) = D`` for ``X`` with Brent's method on the
bracket ``[0, D]``. This yields IDC, the commitment fee and the monthly draw
schedule consistent with ``D``.

**Outer solve (facility solve).** Define::

    f(D) = min( D_DSCR , max_gearing * TPC(D) ) - D

``TPC`` is increasing in ``D`` but with slope well below ``1/max_gearing`` for
any realistic rate and construction period, so ``f`` is continuous and strictly
decreasing: it has exactly one root. ``f(0) > 0`` (some debt is always
supportable against a positive capex) and ``f(D_DSCR) <= 0`` whenever the
gearing cap binds, so ``[0, D_DSCR]`` brackets the root and Brent's method
converges. If ``f(D_DSCR) > 0`` the gearing cap is slack, the DSCR test binds,
and ``D = D_DSCR`` exactly - no iteration needed.

**Tax loop (only when ``TaxTreatment.FULL``).** Cash tax deducts interest, so
CFADS depends on the debt schedule which depends on CFADS. This is handled as
an outer fixed-point iteration on the interest series, damped by nothing
because the feedback gain is ``tax_rate x d(interest)/d(CFADS)``, comfortably
inside the unit circle at any plausible tax rate. It is iterated to the same
tolerance and the iteration count is reported.

Determinism: Brent's method on a fixed bracket with a fixed tolerance is
deterministic. Two runs on the same inputs produce bit-identical results.

One simplification is declared: the DSRA target is taken to be **linear in the
facility size**, which it exactly is - ``service_for_debt_size`` scales the
whole service profile linearly in ``D``, and the DSRA is a linear functional of
that profile. So the DSRA is evaluated once at the unconstrained quantum and
scaled, rather than re-derived inside every function evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from scipy.optimize import brentq

from engine.cashflow import build_cashflow
from engine.debt import size_facility
from engine.defaults import (
    BRACKET_PADDING,
    CIRCULARITY_MAX_ITER,
    CIRCULARITY_TOLERANCE,
    MONTHS_PER_YEAR,
)
from engine.models import (
    CashflowResult,
    ConstructionResult,
    DebtTerms,
    ProjectInputs,
    SizingResult,
    TaxTreatment,
)

__all__ = ["FundingSolution", "solve_funding", "simulate_construction"]


@dataclass(frozen=True, slots=True)
class FundingSolution:
    """The resolved model: operating cashflow, construction funding, sized debt."""

    cashflow: CashflowResult
    construction: ConstructionResult
    sizing: SizingResult
    tax_iterations: int
    converged: bool

    @property
    def debt_size(self) -> float:
        return self.sizing.debt_size

    @property
    def equity(self) -> float:
        return self.construction.equity_at_cod


def simulate_construction(
    *,
    capex: float,
    capex_weights: tuple[float, ...],
    debt_funded_capex: float,
    facility_size: float,
    upfront_fee_rate: float,
    commitment_fee_rate: float,
    annual_interest_rate: float,
    dsra_initial: float,
    dsra_debt_funded: bool,
) -> ConstructionResult:
    """Month-by-month construction drawdown for a *given* debt-funded capex.

    Conventions
    -----------
    * Draws occur at the **start** of the month, so interest accrues on the
      balance after the draw. This is the conservative (lender's) convention;
      a mid-month convention would understate IDC by roughly half a month.
    * IDC and the commitment fee are **capitalised** into the construction
      loan, which is standard for non-recourse construction facilities.
    * The upfront fee is drawn in full at first utilisation and is financed by
      the facility itself.
    * The initial DSRA is funded at COD and therefore accrues no IDC.
    """
    months = len(capex_weights)
    monthly_rate = annual_interest_rate / MONTHS_PER_YEAR
    monthly_commitment_rate = commitment_fee_rate / MONTHS_PER_YEAR
    upfront_fee = upfront_fee_rate * facility_size

    debt_draw: list[float] = []
    equity_draw: list[float] = []
    interest: list[float] = []
    commitment: list[float] = []
    closing: list[float] = []

    balance = 0.0
    for m in range(months):
        draw = debt_funded_capex * capex_weights[m] + (upfront_fee if m == 0 else 0.0)
        after_draw = balance + draw
        month_interest = after_draw * monthly_rate
        undrawn = max(facility_size - after_draw, 0.0)
        month_commitment = undrawn * monthly_commitment_rate
        balance = after_draw + month_interest + month_commitment

        debt_draw.append(draw)
        equity_draw.append(capex * capex_weights[m] - debt_funded_capex * capex_weights[m])
        interest.append(month_interest)
        commitment.append(month_commitment)
        closing.append(balance)

    if months == 0:
        # Instantaneous construction: the facility funds capex and fees at COD.
        balance = debt_funded_capex + upfront_fee

    idc = sum(interest)
    commitment_fee_total = sum(commitment)
    if dsra_debt_funded:
        balance += dsra_initial

    total_project_cost = (
        capex + upfront_fee + commitment_fee_total + idc + dsra_initial
    )
    equity_at_cod = total_project_cost - balance

    return ConstructionResult(
        capex=capex,
        idc=idc,
        upfront_fee=upfront_fee,
        commitment_fee=commitment_fee_total,
        dsra_initial=dsra_initial,
        total_project_cost=total_project_cost,
        debt_at_cod=balance,
        equity_at_cod=equity_at_cod,
        gearing=balance / total_project_cost if total_project_cost else 0.0,
        debt_funded_costs=debt_funded_capex,
        monthly_debt_draw=tuple(debt_draw),
        monthly_equity_draw=tuple(equity_draw),
        monthly_interest=tuple(interest),
        monthly_commitment_fee=tuple(commitment),
        monthly_closing_balance=tuple(closing),
        iterations=0,
        converged=True,
        residual=0.0,
    )


def _construction_for_facility(
    project: ProjectInputs,
    terms: DebtTerms,
    facility_size: float,
    dsra_per_unit_debt: float,
    tolerance: float,
) -> ConstructionResult:
    """Inner solve: find the debt-funded capex consistent with ``facility_size``.

    Solves ``B(X) = facility_size`` for the debt-funded capex ``X`` with Brent's
    method. ``B`` is strictly increasing in ``X`` (an extra dollar drawn is an
    extra dollar of balance plus positive interest on it), so the root is
    unique on ``[0, facility_size]``.

    Trial facility sizes above what capex can absorb are *not* rejected here:
    they are legitimate intermediate points of the outer root-find. Feasibility
    (equity contribution >= 0) is checked once, at the solution.
    """
    weights = project.normalised_capex_curve()
    dsra_initial = dsra_per_unit_debt * facility_size

    def closing_balance(x: float) -> ConstructionResult:
        return simulate_construction(
            capex=project.capex,
            capex_weights=weights,
            debt_funded_capex=x,
            facility_size=facility_size,
            upfront_fee_rate=terms.upfront_fee,
            commitment_fee_rate=terms.commitment_fee,
            annual_interest_rate=terms.interest_rate,
            dsra_initial=dsra_initial,
            dsra_debt_funded=terms.dsra_debt_funded,
        )

    if facility_size <= 0.0:
        return closing_balance(0.0)

    def residual(x: float) -> float:
        return closing_balance(x).debt_at_cod - facility_size

    lo, hi = 0.0, facility_size
    if residual(hi) < 0.0:
        # Even funding every dollar of the facility into capex cannot reach the
        # facility size: only possible if the facility exceeds capex + carry.
        raise ValueError(
            "facility size exceeds the total cost it could possibly fund - "
            "check max_gearing and capex"
        )
    if residual(lo) >= 0.0:
        solved_x = 0.0
        iterations = 0
    else:
        solved_x, results = brentq(
            residual, lo, hi, xtol=tolerance, maxiter=CIRCULARITY_MAX_ITER,
            full_output=True,
        )
        iterations = results.iterations
        if not results.converged:  # pragma: no cover - brentq raises instead
            raise RuntimeError("construction draw solve failed to converge")

    result = closing_balance(solved_x)
    return replace(
        result,
        iterations=iterations,
        converged=True,
        residual=abs(residual(solved_x)),
    )


def _solve_for_cashflow(
    project: ProjectInputs,
    terms: DebtTerms,
    cashflow: CashflowResult,
    tolerance: float,
) -> tuple[ConstructionResult, SizingResult]:
    """Outer solve: the facility size that satisfies DSCR *and* gearing."""
    cfads = cashflow.cfads
    ppy = project.periods_per_year
    life = cashflow.n_periods

    # Quantum with the gearing test switched off. This is the upper bracket and
    # also the reference schedule the DSRA is scaled from.
    unconstrained = size_facility(cfads, terms, ppy, life, total_project_cost=None)
    d_max = unconstrained.debt_size
    if d_max <= 0.0:
        raise ValueError("CFADS supports no debt at the target DSCR")
    dsra_per_unit = unconstrained.dsra_target[0] / d_max

    def required_debt(d: float) -> tuple[float, ConstructionResult]:
        construction = _construction_for_facility(
            project, terms, d, dsra_per_unit, tolerance
        )
        capped = min(d_max, terms.max_gearing * construction.total_project_cost)
        return capped, construction

    top_required, top_construction = required_debt(d_max)
    if top_required >= d_max - tolerance:
        # Gearing cap is slack: the DSCR sculpt sets the quantum outright.
        final_debt = d_max
        construction = top_construction
        iterations = top_construction.iterations
        residual = abs(top_required - d_max)
    else:
        def outer_residual(d: float) -> float:
            return required_debt(d)[0] - d

        upper = d_max * (1.0 + BRACKET_PADDING)
        final_debt, results = brentq(
            outer_residual, 0.0, upper, xtol=tolerance,
            maxiter=CIRCULARITY_MAX_ITER, full_output=True,
        )
        iterations = results.iterations
        _, construction = required_debt(final_debt)
        residual = abs(outer_residual(final_debt))

    if construction.equity_at_cod < -max(tolerance, construction.total_project_cost * 1e-9):
        raise ValueError(
            "the solved facility exceeds total project cost - the sponsor would "
            "contribute negative equity; check max_gearing, fees and capex"
        )

    construction = replace(
        construction,
        iterations=iterations,
        converged=residual <= max(tolerance, 1e-6 * max(final_debt, 1.0)),
        residual=residual,
    )
    sizing = size_facility(
        cfads, terms, ppy, life,
        total_project_cost=construction.total_project_cost,
    )
    return construction, sizing


def solve_funding(
    project: ProjectInputs,
    terms: DebtTerms,
    tolerance: float = CIRCULARITY_TOLERANCE,
    max_tax_iterations: int = 50,
) -> FundingSolution:
    """Resolve the full model: operating cashflow, funding circularity, debt.

    Parameters
    ----------
    project, terms:
        Model inputs.
    tolerance:
        Absolute convergence tolerance, in currency units, for both the inner
        draw solve and the outer facility solve. Exposed so that a caller
        running a large sensitivity grid can trade precision for speed.
    max_tax_iterations:
        Cap on the CFADS/interest fixed point used when
        ``project.tax_treatment is TaxTreatment.FULL``.

    Raises
    ------
    RuntimeError
        If the tax fixed point does not converge within ``max_tax_iterations``.
        The engine never returns a silently unconverged answer.
    """
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")

    if project.tax_treatment is not TaxTreatment.FULL:
        cashflow = build_cashflow(project)
        construction, sizing = _solve_for_cashflow(
            project, terms, cashflow, tolerance
        )
        return FundingSolution(
            cashflow=cashflow,
            construction=construction,
            sizing=sizing,
            tax_iterations=0,
            converged=construction.converged,
        )

    interest: tuple[float, ...] = tuple(0.0 for _ in range(project.operating_periods))
    cashflow = build_cashflow(project, interest)
    construction, sizing = _solve_for_cashflow(project, terms, cashflow, tolerance)

    for iteration in range(1, max_tax_iterations + 1):
        new_interest = tuple(sizing.debt.interest) + tuple(
            0.0 for _ in range(project.operating_periods - sizing.debt.n_periods)
        )
        delta = max(
            (abs(a - b) for a, b in zip(new_interest, interest)), default=0.0
        )
        interest = new_interest
        cashflow = build_cashflow(project, interest)
        construction, sizing = _solve_for_cashflow(
            project, terms, cashflow, tolerance
        )
        if delta <= tolerance:
            return FundingSolution(
                cashflow=cashflow,
                construction=construction,
                sizing=sizing,
                tax_iterations=iteration,
                converged=construction.converged,
            )

    raise RuntimeError(
        f"CFADS/interest tax fixed point did not converge in "
        f"{max_tax_iterations} iterations at tolerance {tolerance}"
    )
