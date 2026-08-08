"""Cost recovery: MACRS, straight line, bonus, and the 50% ITC basis reduction.

**The one rule everybody outside the asset class gets wrong.** Under
**§50(c)(3)**, claiming an investment credit reduces the depreciable basis of
the property by **50% of the credit**::

    depreciable basis = eligible cost - 0.5 x ITC

So a $100m project taking a 30% ITC ($30m) depreciates $85m, not $100m. That
single line moves a sponsor IRR by more than most of the debt assumptions
practitioners argue about, and it is the reason a tax-equity model cannot reuse
a generic infrastructure depreciation module. It is asserted directly in
``tests/test_tax_depreciation.py``.

**Methods implemented**

* **MACRS 5-year** - 200% declining balance switching to straight line,
  half-year convention (IRS Pub. 946 Table A-1). The default for most qualified
  energy property.
* **MACRS 15-year** - 150% declining balance switching to straight line,
  half-year convention.
* **Straight line 5 / 15 / 20 / 39** years.
* **Bonus depreciation** under §168(k) at a caller-supplied rate. Bonus is taken
  on the **reduced** basis in year one; the remaining basis then runs the
  ordinary recovery table.

**Declared simplifications** (also in ``UNVERIFIED.md``):

* the **half-year** convention is applied to every straight-line life, including
  39-year nonresidential real property, which properly uses the **mid-month**
  convention;
* the **mid-quarter** convention is not implemented;
* state depreciation (which frequently decouples from federal bonus) is out of
  scope for Phase 2.
"""

from __future__ import annotations

from engine.tax.constants import (
    ITC_BASIS_REDUCTION_FRACTION,
    MACRS_5_YEAR,
    MACRS_15_YEAR,
    STRAIGHT_LINE_LIVES,
)
from engine.tax.models import (
    DepreciationMethod,
    DepreciationPeriod,
    DepreciationSchedule,
)

__all__ = [
    "reduced_basis",
    "recovery_percentages",
    "build_schedule",
]

_CITATIONS = (
    "itc-basis-reduction",
    "macrs-recovery-periods",
    "bonus-depreciation",
    "straight-line-conventions",
)


def reduced_basis(original_basis: float, itc_amount: float) -> float:
    """Depreciable basis after the §50(c)(3) adjustment.

    ``original_basis - 0.5 * itc_amount``. Where no investment credit is claimed
    (a §45Y PTC deal, or a disqualified project) ``itc_amount`` is zero and the
    basis is unreduced - which is exactly why PTC deals depreciate more.
    """
    if original_basis < 0:
        raise ValueError("original_basis must be >= 0")
    if itc_amount < 0:
        raise ValueError("itc_amount must be >= 0")
    return original_basis - ITC_BASIS_REDUCTION_FRACTION * itc_amount


def _straight_line_percentages(life: int) -> tuple[float, ...]:
    """Straight-line recovery percentages under the half-year convention.

    Half a year's deduction in year 1, full deductions in years 2..life, and the
    remaining half year in year ``life + 1``. Sums to exactly 1.
    """
    half = 1.0 / (2 * life)
    full = 1.0 / life
    return (half,) + (full,) * (life - 1) + (half,)


def recovery_percentages(method: DepreciationMethod) -> tuple[float, ...]:
    """The recovery table for a method, as fractions of depreciable basis."""
    if method is DepreciationMethod.MACRS_5:
        return MACRS_5_YEAR
    if method is DepreciationMethod.MACRS_15:
        return MACRS_15_YEAR
    life = STRAIGHT_LINE_LIVES.get(method.value)
    if life is None:  # pragma: no cover - exhaustive over the enum
        raise ValueError(f"Unsupported depreciation method: {method}")
    return _straight_line_percentages(life)


def build_schedule(
    original_basis: float,
    itc_amount: float,
    method: DepreciationMethod = DepreciationMethod.MACRS_5,
    bonus_rate: float = 0.0,
    start_year: int = 1,
) -> DepreciationSchedule:
    """Full period-by-period cost recovery schedule.

    Parameters
    ----------
    original_basis
        Eligible cost before the §50(c)(3) reduction - normally project capex.
    itc_amount
        The investment credit actually claimed. Zero for a PTC deal.
    method
        Recovery table to apply to the post-bonus remaining basis.
    bonus_rate
        §168(k) bonus fraction, applied to the **reduced** basis in the first
        period. 1.0 is full expensing.
    start_year
        Label for the first period. Pass the placed-in-service calendar year to
        get calendar-labelled periods; the default of 1 gives relative years.

    Returns
    -------
    DepreciationSchedule
        With the basis reduction shown explicitly, so a reviewer can tie
        ``original_basis - basis_reduction == depreciable_basis`` by eye.
    """
    if not 0.0 <= bonus_rate <= 1.0:
        raise ValueError("bonus_rate must lie in [0, 1]")

    basis_reduction = ITC_BASIS_REDUCTION_FRACTION * itc_amount
    depreciable = reduced_basis(original_basis, itc_amount)
    bonus = depreciable * bonus_rate
    remaining = depreciable - bonus

    table = recovery_percentages(method)
    periods: list[DepreciationPeriod] = []
    opening = depreciable

    for i, pct in enumerate(table):
        this_bonus = bonus if i == 0 else 0.0
        recovery = remaining * pct
        total = this_bonus + recovery
        closing = opening - total
        periods.append(
            DepreciationPeriod(
                year=start_year + i,
                opening_basis=opening,
                bonus_deduction=this_bonus,
                recovery_deduction=recovery,
                total_deduction=total,
                closing_basis=closing,
            )
        )
        opening = closing

    return DepreciationSchedule(
        method=method,
        original_basis=original_basis,
        itc_amount=itc_amount,
        basis_reduction=basis_reduction,
        depreciable_basis=depreciable,
        bonus_rate=bonus_rate,
        bonus_deduction=bonus,
        periods=tuple(periods),
        citation_ids=_CITATIONS,
    )
