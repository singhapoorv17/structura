"""The bundle of engine objects every sheet builder receives.

One frozen container rather than seven positional arguments, so a new sheet
can be added without changing any existing builder signature.
The derived properties here are the handful of quantities that more than one
sheet needs (period counts, style codes, period-end dates) - deliberately
computed once, in one place, so two sheets cannot disagree about them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Final

from engine.circularity import FundingSolution
from engine.models import (
    AmortizationStyle,
    DebtTerms,
    ProjectInputs,
    ReturnsResult,
    TaxTreatment,
    WaterfallResult,
)

__all__ = [
    "AMORTIZATION_CODE",
    "TAX_TREATMENT_CODE",
    "ModelBundle",
    "DISCLAIMER",
]

#: Excel has no enums, so the amortisation style is carried as an integer that
#: ``CHOOSE()`` indexes directly. Changing this cell in Excel genuinely
#: re-sizes the facility - the three sizing formulas are all live.
AMORTIZATION_CODE: Final[dict[AmortizationStyle, int]] = {
    AmortizationStyle.SCULPTED: 1,
    AmortizationStyle.LEVEL: 2,
    AmortizationStyle.FIXED_PRINCIPAL: 3,
}

#: 1 = no project-level tax (CFADS is pre-tax), 2 = tax before the interest
#: deduction, 3 = full (interest deductible - which is what makes the tax line
#: circular, and is precisely why the workbook needs iterative calculation).
TAX_TREATMENT_CODE: Final[dict[TaxTreatment, int]] = {
    TaxTreatment.NONE: 1,
    TaxTreatment.PRE_DEBT: 2,
    TaxTreatment.FULL: 3,
}

DISCLAIMER: Final[str] = (
    "Illustrative modelling tool. Not tax, legal, accounting or investment "
    "advice. Outputs depend entirely on user-supplied assumptions and must be "
    "independently verified before any financing, investment or tax decision."
)


@dataclass(frozen=True, slots=True)
class ModelBundle:
    """Everything the workbook needs, resolved once."""

    project: ProjectInputs
    terms: DebtTerms
    solution: FundingSolution
    waterfall: WaterfallResult
    returns: ReturnsResult
    discount_rate: float = 0.10
    lockup_dscr: float | None = None
    generated_on: date = field(default_factory=date.today)

    # -- shapes -------------------------------------------------------------

    @property
    def periods_per_year(self) -> int:
        return self.project.periods_per_year

    @property
    def n_periods(self) -> int:
        """Operating periods from COD to the end of project life."""
        return self.solution.cashflow.n_periods

    @property
    def n_debt_periods(self) -> int:
        """Periods the senior facility actually amortises over."""
        return self.solution.sizing.debt.n_periods

    @property
    def construction_months(self) -> int:
        """Months of construction. At least one column, so the grid is never empty."""
        return max(self.project.construction_months, 1)

    @property
    def period_months(self) -> float:
        return 12.0 / self.periods_per_year

    @property
    def dsra_periods(self) -> float:
        """DSRA cover expressed in model periods (6 months annual = 0.5)."""
        return self.terms.dsra_months / self.period_months

    @property
    def dsra_lookahead(self) -> int:
        """How many future periods the DSRA formula must reach forward.

        The forward-looking reserve consumes future debt service pro rata, so
        the number of terms in the Excel formula is the ceiling of the cover
        expressed in periods. Computed from the engine's inputs so the emitted
        formula is exactly as long as it needs to be.
        """
        import math

        return max(1, math.ceil(self.dsra_periods - 1e-12))

    # -- codes --------------------------------------------------------------

    @property
    def amortization_code(self) -> int:
        return AMORTIZATION_CODE[self.terms.amortization]

    @property
    def tax_code(self) -> int:
        return TAX_TREATMENT_CODE[self.project.tax_treatment]

    # -- calendar -----------------------------------------------------------

    @property
    def cod(self) -> datetime:
        c = self.project.cod_date
        return datetime(c.year, c.month, c.day)

    def period_end_dates(self, start: int = 1) -> tuple[datetime, ...]:
        """Period-end dates, matching ``engine.metrics.period_dates``.

        A 365-day year divided by the period count - the same convention the
        engine uses for XIRR, so the workbook's XIRR and the engine's agree.
        Exact day-count conventions (30/360, act/360) are not modelled; see the
        Notes sheet.
        """
        days = int(round(365.0 / self.periods_per_year))
        return tuple(
            self.cod + timedelta(days=days * t)
            for t in range(start, self.n_periods + 1)
        )

    # -- convenience --------------------------------------------------------

    @property
    def target_dscr_profile(self) -> tuple[float, ...]:
        """Target DSCR per debt period, expanded from scalar or sequence."""
        return self.terms.dscr_profile(self.terms.periods(self.periods_per_year))[
            : self.n_debt_periods
        ]

    @property
    def scalar_target_dscr(self) -> float | None:
        """The single target, or ``None`` when the target is time-varying."""
        if isinstance(self.terms.target_dscr, (int, float)):
            return float(self.terms.target_dscr)
        return None
