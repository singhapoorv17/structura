"""Return metrics: IRR, XIRR, NPV, payback, and effective cost of capital.

Sign convention throughout: **outflows negative, inflows positive, from the
perspective of the party whose return is being measured.** Equity IRR is
measured from the sponsor's chair, so the equity contribution at COD is
negative. The effective cost of debt is measured from the *lender's* chair -
the facility advanced is a negative number to them - which is why the same
routine produces the borrower's all-in cost.

``pyxirr`` is used for the root-finding. It is a compiled
Brent/Newton implementation and is materially more robust than a hand-rolled
bisection on the long, sign-alternating cashflow series a levered project throws
off.
"""

from __future__ import annotations

from datetime import date, timedelta

import pyxirr

from engine.defaults import CASH_TOLERANCE, MONTHS_PER_YEAR
from engine.models import (
    ConstructionResult,
    DebtResult,
    ReturnsResult,
    WaterfallResult,
)

__all__ = [
    "irr",
    "xirr",
    "npv",
    "payback_period",
    "effective_cost_of_debt",
    "equity_cashflows",
    "period_dates",
    "compute_returns",
]


def irr(cashflows: tuple[float, ...] | list[float]) -> float | None:
    """Periodic IRR: the rate that sets the PV of the series to zero.

    Returns ``None`` when no rate exists - a series that never changes sign has
    no IRR, and returning ``None`` is more honest than returning a number.
    """
    flows = list(cashflows)
    if not flows or all(f >= 0 for f in flows) or all(f <= 0 for f in flows):
        return None
    try:
        result = pyxirr.irr(flows)
    except Exception:  # pragma: no cover - pyxirr raises on pathological series
        return None
    return None if result is None else float(result)


def annualise(periodic_rate: float, periods_per_year: int) -> float:
    """Compound a per-period rate to an effective annual rate."""
    return (1.0 + periodic_rate) ** periods_per_year - 1.0


def xirr(dates: tuple[date, ...], amounts: tuple[float, ...]) -> float | None:
    """Date-aware IRR. The right metric when periods are not evenly spaced."""
    if len(dates) != len(amounts):
        raise ValueError("dates and amounts must be the same length")
    if all(a >= 0 for a in amounts) or all(a <= 0 for a in amounts):
        return None
    try:
        result = pyxirr.xirr(list(dates), list(amounts))
    except Exception:  # pragma: no cover
        return None
    return None if result is None else float(result)


def npv(cashflows: tuple[float, ...] | list[float], rate: float) -> float:
    """NPV of a series received in arrears, with ``cashflows[0]`` at t=0.

    Note the convention: index 0 is *undiscounted*. Equity series built by
    ``equity_cashflows`` put the COD contribution at index 0, so this matches.
    """
    return sum(cf / (1.0 + rate) ** i for i, cf in enumerate(cashflows))


def payback_period(
    cashflows: tuple[float, ...] | list[float],
    periods_per_year: int = 1,
) -> float | None:
    """Years until cumulative cash turns positive, interpolated within a period.

    Undiscounted. ``cashflows[0]`` is the investment at t=0.
    """
    cumulative = 0.0
    previous = 0.0
    for i, cf in enumerate(cashflows):
        previous = cumulative
        cumulative += cf
        if cumulative >= 0 and i > 0:
            if cf == 0:
                return i / periods_per_year
            fraction = -previous / cf
            return (i - 1 + fraction) / periods_per_year
    return None


def effective_cost_of_debt(
    debt: DebtResult,
    upfront_fee: float = 0.0,
    commitment_fee: float = 0.0,
) -> float | None:
    """All-in effective annual cost of the senior facility, including fees.

    The borrower receives the facility less the fees it pays out of it, and
    repays the full debt service. The IRR of that series is the true cost of
    the money - always above the coupon, and the number a credit committee
    compares against the swap curve.
    """
    net_proceeds = debt.debt_size - upfront_fee - commitment_fee
    flows = [net_proceeds] + [-ds for ds in debt.debt_service]
    periodic = irr(tuple(flows))
    if periodic is None:
        return None
    return annualise(periodic, debt.periods_per_year)


def equity_cashflows(
    construction: ConstructionResult,
    waterfall: WaterfallResult,
) -> tuple[float, ...]:
    """Sponsor cashflow series: equity in at t=0, distributions thereafter.

    The whole equity contribution is treated as a single outflow at COD.
    Equity is in reality drawn across construction (often *ahead* of debt, on
    an equity-first funding order), which makes the true equity IRR slightly
    lower. Simplified here; see LIMITS.md. The monthly equity draw series is
    available on ``ConstructionResult.monthly_equity_draw``.
    """
    return (-construction.equity_at_cod, *waterfall.distributions)


def period_dates(
    cod_date: date, n_periods: int, periods_per_year: int
) -> tuple[date, ...]:
    """Payment dates: COD, then the end of each model period.

    Uses a 365-day year scaled by period length. Exact day-count conventions
    (30/360, act/360) are an Excel-parity concern, not a sizing concern.
    """
    days = int(round(365.0 / periods_per_year))
    return tuple(cod_date + timedelta(days=days * i) for i in range(n_periods + 1))


def compute_returns(
    construction: ConstructionResult,
    waterfall_post_tax: WaterfallResult,
    debt: DebtResult,
    *,
    waterfall_pre_tax: WaterfallResult | None = None,
    discount_rate: float = 0.10,
    periods_per_year: int = 1,
    cod_date: date | None = None,
    tax_rate: float = 0.0,
) -> ReturnsResult:
    """Assemble the sponsor and facility return metrics.

    Parameters
    ----------
    waterfall_post_tax:
        The waterfall run with project-level cash tax in CFADS.
    waterfall_pre_tax:
        Optional companion run with tax switched off. Supplying both is what
        makes the pre-tax / post-tax equity IRR pair meaningful: they must be
        the *same* deal with only the tax line changed. If omitted, the
        pre-tax IRR is reported as ``None`` rather than guessed at.
    discount_rate:
        Annual rate for the equity NPV. Converted to a per-period rate.
    tax_rate:
        Marginal rate used for the after-tax cost of debt, ``r x (1 - t)``.
    """
    post_flows = equity_cashflows(construction, waterfall_post_tax)
    periodic_post = irr(post_flows)
    equity_irr_post = (
        annualise(periodic_post, periods_per_year) if periodic_post is not None else None
    )

    equity_irr_pre: float | None = None
    if waterfall_pre_tax is not None:
        pre_flows = equity_cashflows(construction, waterfall_pre_tax)
        periodic_pre = irr(pre_flows)
        equity_irr_pre = (
            annualise(periodic_pre, periods_per_year)
            if periodic_pre is not None
            else None
        )

    period_discount = (1.0 + discount_rate) ** (1.0 / periods_per_year) - 1.0
    equity_npv = npv(post_flows, period_discount)
    invested = construction.equity_at_cod
    moic = (
        sum(waterfall_post_tax.distributions) / invested
        if invested > CASH_TOLERANCE
        else 0.0
    )

    cost_of_debt = effective_cost_of_debt(
        debt, construction.upfront_fee, construction.commitment_fee
    )
    after_tax_cost_of_debt = (
        cost_of_debt * (1.0 - tax_rate) if cost_of_debt is not None else None
    )

    wacc: float | None = None
    total_capital = construction.debt_at_cod + construction.equity_at_cod
    if (
        total_capital > CASH_TOLERANCE
        and after_tax_cost_of_debt is not None
        and equity_irr_post is not None
    ):
        wacc = (
            construction.debt_at_cod / total_capital * after_tax_cost_of_debt
            + construction.equity_at_cod / total_capital * equity_irr_post
        )

    dates: tuple[date, ...] = ()
    if cod_date is not None:
        dates = period_dates(
            cod_date, len(waterfall_post_tax.distributions), periods_per_year
        )

    return ReturnsResult(
        equity_investment=invested,
        equity_cashflows=post_flows,
        equity_irr_pre_tax=equity_irr_pre,
        equity_irr_post_tax=equity_irr_post,
        equity_npv=equity_npv,
        equity_moic=moic,
        payback_years=payback_period(post_flows, periods_per_year),
        effective_cost_of_debt=cost_of_debt,
        after_tax_cost_of_debt=after_tax_cost_of_debt,
        weighted_average_cost_of_capital=wacc,
        dates=dates,
    )


def months_to_periods(months: float, periods_per_year: int) -> float:
    """Convert a month count to model periods."""
    return months * periods_per_year / MONTHS_PER_YEAR
