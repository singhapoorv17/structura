"""Operating cashflow model: revenue -> opex -> EBITDA -> tax -> CFADS.

This module is deliberately dumb and deterministic. It knows nothing about
debt; it produces the CFADS series that every coverage test in
``engine.debt`` divides into. Keeping the operating model free of financing is
what makes the debt sizing auditable - a reviewer can check CFADS on its own
before looking at a single sculpting formula.

Conventions
-----------
* Period 1 is the first operating period after COD.
* Escalation and degradation compound annually and are applied on an
  *operating-year* basis, so with ``periods_per_year = 2`` both sub-periods of
  operating year 3 carry the same price and the same degradation factor.
* An annual quantity is divided evenly across the sub-periods of its year. No
  seasonality; see LIMITS.md.
"""

from __future__ import annotations

from engine.defaults import CASH_TOLERANCE
from engine.models import CashflowResult, ProjectInputs, TaxTreatment

__all__ = ["build_cashflow", "flat_cashflow"]


def _operating_year(period: int, periods_per_year: int) -> int:
    """1-based operating year containing 1-based ``period``."""
    return (period - 1) // periods_per_year + 1


def build_cashflow(
    project: ProjectInputs,
    interest: tuple[float, ...] | None = None,
) -> CashflowResult:
    """Build the period-by-period operating model and CFADS series.

    Parameters
    ----------
    project:
        Asset inputs. ``project.tax_treatment`` selects the CFADS tax basis.
    interest:
        Senior interest per period, required only when the tax treatment is
        ``TaxTreatment.FULL`` (interest is deductible, so cash tax depends on
        the debt schedule, which depends on CFADS - the fixed point is resolved
        in ``engine.circularity.solve_funding``). Shorter sequences are padded
        with zeros, which is the correct behaviour after debt maturity.

    Returns
    -------
    CashflowResult
        Every line item of the operating model, period by period.

    Notes
    -----
    **Revenue split.** ``contracted_share`` of production prices at the
    contracted price for ``contract_years``; the balance, and everything after
    contract expiry, prices at the merchant price. Both prices escalate from
    their own year-1 level.

    **Tax.** Taxable income is EBITDA less straight-line book depreciation
    (less interest under ``FULL``). Negative taxable income is carried forward
    as a net operating loss and offsets later income in full. Federal only; no
    state tax, no MACRS, no bonus depreciation - those live in ``engine/tax/``
    because they are tax-law-dependent and therefore need dated citations.
    """
    ppy = project.periods_per_year
    n = project.operating_periods
    if n <= 0:
        raise ValueError("project_life_years x periods_per_year must be >= 1")

    interest_series = tuple(interest or ())

    base_production = project.production
    contract_periods = int(round(project.contract_years * ppy))

    period_index: list[int] = []
    year_fraction: list[float] = []
    production: list[float] = []
    contracted_rev: list[float] = []
    merchant_rev: list[float] = []
    revenue: list[float] = []
    opex: list[float] = []
    ebitda: list[float] = []
    depreciation: list[float] = []
    cash_tax: list[float] = []
    cfads: list[float] = []

    annual_depreciation = (
        project.capex / project.depreciation_years
        if project.depreciation_years > 0
        else 0.0
    )
    nol_carryforward = 0.0

    for t in range(1, n + 1):
        year = _operating_year(t, ppy)
        esc = year - 1  # number of full escalation steps applied

        annual_production = base_production * (1.0 - project.degradation) ** esc
        period_production = annual_production / ppy

        contracted_price = project.contracted_price * (
            1.0 + project.contracted_escalation
        ) ** esc
        merchant_price = project.merchant_price * (
            1.0 + project.merchant_escalation
        ) ** esc

        under_contract = t <= contract_periods
        contracted_volume = (
            period_production * project.contracted_share if under_contract else 0.0
        )
        merchant_volume = period_production - contracted_volume

        c_rev = contracted_volume * contracted_price
        m_rev = merchant_volume * merchant_price
        total_rev = c_rev + m_rev

        annual_opex = project.opex_year1 * (1.0 + project.opex_escalation) ** esc
        period_opex = annual_opex / ppy

        period_ebitda = total_rev - period_opex

        # Depreciation only runs for the depreciable life, then stops.
        depreciable = (year - 1) < project.depreciation_years
        period_depreciation = (annual_depreciation / ppy) if depreciable else 0.0

        period_interest = interest_series[t - 1] if t - 1 < len(interest_series) else 0.0

        tax, nol_carryforward = _cash_tax(
            treatment=project.tax_treatment,
            ebitda=period_ebitda,
            depreciation=period_depreciation,
            interest=period_interest,
            tax_rate=project.tax_rate,
            nol_carryforward=nol_carryforward,
        )

        period_index.append(t)
        year_fraction.append(t / ppy)
        production.append(period_production)
        contracted_rev.append(c_rev)
        merchant_rev.append(m_rev)
        revenue.append(total_rev)
        opex.append(period_opex)
        ebitda.append(period_ebitda)
        depreciation.append(period_depreciation)
        cash_tax.append(tax)
        cfads.append(period_ebitda - tax)

    return CashflowResult(
        periods_per_year=ppy,
        period_index=tuple(period_index),
        year_fraction=tuple(year_fraction),
        production_mwh=tuple(production),
        contracted_revenue=tuple(contracted_rev),
        merchant_revenue=tuple(merchant_rev),
        revenue=tuple(revenue),
        opex=tuple(opex),
        ebitda=tuple(ebitda),
        depreciation=tuple(depreciation),
        cash_tax=tuple(cash_tax),
        cfads=tuple(cfads),
        tax_treatment=project.tax_treatment,
    )


def _cash_tax(
    *,
    treatment: TaxTreatment,
    ebitda: float,
    depreciation: float,
    interest: float,
    tax_rate: float,
    nol_carryforward: float,
) -> tuple[float, float]:
    """Cash tax for one period, plus the NOL carried into the next period.

    A negative taxable income does not generate a refund; it accumulates as a
    net operating loss and shelters future taxable income. This is the standard
    project-level treatment for a stand-alone SPV that cannot consolidate.
    """
    if treatment is TaxTreatment.NONE or tax_rate <= 0.0:
        return 0.0, nol_carryforward

    taxable = ebitda - depreciation
    if treatment is TaxTreatment.FULL:
        taxable -= interest

    taxable -= nol_carryforward
    if taxable < 0.0:
        return 0.0, -taxable
    return taxable * tax_rate, 0.0


def flat_cashflow(
    cfads_per_period: float,
    n_periods: int,
    periods_per_year: int = 1,
) -> CashflowResult:
    """A synthetic flat-CFADS series.

    Used by the golden tests: with constant CFADS and a constant DSCR target,
    the sculpted debt size collapses to a closed-form annuity, so the engine's
    answer can be checked against a formula rather than against itself.
    """
    if n_periods <= 0:
        raise ValueError("n_periods must be positive")
    zeros = tuple(0.0 for _ in range(n_periods))
    flat = tuple(float(cfads_per_period) for _ in range(n_periods))
    return CashflowResult(
        periods_per_year=periods_per_year,
        period_index=tuple(range(1, n_periods + 1)),
        year_fraction=tuple(t / periods_per_year for t in range(1, n_periods + 1)),
        production_mwh=zeros,
        contracted_revenue=flat,
        merchant_revenue=zeros,
        revenue=flat,
        opex=zeros,
        ebitda=flat,
        depreciation=zeros,
        cash_tax=zeros,
        cfads=flat,
        tax_treatment=TaxTreatment.NONE,
    )


def assert_cfads_identity(result: CashflowResult) -> None:
    """Assert revenue - opex - tax == CFADS for every period.

    Cheap invariant, but it is the one line that catches a mis-wired operating
    model before it propagates into the debt sizing.
    """
    for i in range(result.n_periods):
        expected = result.revenue[i] - result.opex[i] - result.cash_tax[i]
        if abs(expected - result.cfads[i]) > CASH_TOLERANCE:
            raise AssertionError(
                f"CFADS identity violated in period {i + 1}: "
                f"{expected} != {result.cfads[i]}"
            )
