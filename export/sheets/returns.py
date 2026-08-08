"""Returns - equity cashflows, IRR / NPV / payback, and the cost of the debt.

Every return metric on this sheet is computed by **Excel's own financial
functions** operating on the workbook's own cashflow rows - ``IRR``, ``XIRR``,
``NPV``. Nothing is pasted from Python. That is the point: a reader can select
the equity cashflow row, look at the status bar, and see the same numbers.

Sign convention: outflows negative, inflows positive, from the chair of the
party whose return is being measured. The sponsor's equity contribution at COD
is negative. The lender's row is written from the *lender's* chair - the
facility advanced is negative to them - which is why the same ``IRR`` produces
the borrower's all-in cost of funds.

This sheet is the only one with a **period 0** column: the equity investment
lands at COD, before the first operating period.
"""

from __future__ import annotations

from export import styles
from export.model import ModelBundle
from export.workbook import WorkbookBuilder

__all__ = ["SHEET_NAME", "build"]

SHEET_NAME = "Returns"


def build(wb: WorkbookBuilder, model: ModelBundle) -> None:
    """Write the Returns sheet."""
    n = model.n_periods
    sw = wb.create_sheet(SHEET_NAME, n_periods=n + 1, start_period=0)
    sw.hide_gridlines()
    sw.set_widths()
    sw.title_block(
        "Returns",
        "Equity cashflows and the sponsor's IRR, NPV, MOIC and payback, plus "
        "the all-in cost of the senior facility. Period 0 is COD.",
    )
    sw.period_header()
    L = sw.local

    period = sw.values_row(
        "ret.period",
        "Period",
        list(sw.periods()),
        unit="#",
        style=styles.NOTE,
        number_format=styles.NUMBER_0,
    )
    dates = sw.formula_row(
        "ret.date",
        "Cashflow date",
        lambda t: (
            "COD_Date"
            if t == 0
            else f"EDATE(COD_Date,Period_Months*{L(period.row, t)})"
        ),
        unit="date",
        style=styles.FORMULA,
        number_format=styles.DATE_FMT,
    )
    sw.skip()

    # ------------------------------------------------------------------
    # Sponsor
    # ------------------------------------------------------------------
    sw.section("Sponsor cashflows")
    contribution = sw.formula_row(
        "ret.equity_contribution",
        "Equity contribution",
        lambda t: "-Equity_At_COD" if t == 0 else "0",
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    distributions = sw.formula_row(
        "ret.distributions",
        "Distributions received",
        lambda t: "0" if t == 0 else wb.ref("wf.distributions", t),
        unit="$",
        style=styles.LINK,
        number_format=styles.MONEY,
        total=True,
    )
    equity_cf = sw.formula_row(
        "ret.equity_cashflow",
        "Equity cashflow",
        lambda t: f"{L(contribution.row, t)}+{L(distributions.row, t)}",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        total=True,
        series_name="Equity_Cashflow_Series",
    )
    cumulative = sw.formula_row(
        "ret.cumulative",
        "Cumulative equity cashflow",
        lambda t: (
            f"{L(equity_cf.row, t)}"
            if t == 0
            else f"{L(sw.row, t - 1)}+{L(equity_cf.row, t)}"
        ),
        unit="$",
        number_format=styles.MONEY,
    )
    sw.skip()

    # ------------------------------------------------------------------
    # Lender
    # ------------------------------------------------------------------
    sw.section("Senior facility cashflows (lender's chair)")
    lender_cf = sw.formula_row(
        "ret.lender_cashflow",
        "Facility advanced / debt service received",
        lambda t: (
            "Senior_Debt-Upfront_Fee_Amount-Commitment_Fee_Total"
            if t == 0
            else f"-{wb.ref('debt.debt_service', t)}"
        ),
        unit="$",
        style=styles.LINK,
        number_format=styles.MONEY,
        total=True,
    )
    sw.skip()

    cf_range = _range(sw, equity_cf)
    cum_range = _range(sw, cumulative)
    date_range = _range(sw, dates)
    lender_range = _range(sw, lender_cf)
    first_operating = sw.local(equity_cf.row, 1, absolute=True)
    last_operating = sw.local(equity_cf.row, sw.last_period, absolute=True)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    sw.section("Sponsor return metrics")
    sw.scalar(
        "Equity IRR - per period",
        f"=IRR({cf_range})",
        unit="% per period",
        number_format=styles.RATE_3,
        name="Equity_IRR_Periodic",
    )
    sw.scalar(
        "Equity IRR - annual effective",
        "=(1+Equity_IRR_Periodic)^Periods_Per_Year-1",
        unit="% p.a.",
        style=styles.TOTAL,
        number_format=styles.PERCENT_2,
        name="Equity_IRR",
        source="Periodic IRR compounded to an effective annual rate.",
    )
    sw.scalar(
        "Equity XIRR - date aware",
        f"=XIRR({cf_range},{date_range})",
        unit="% p.a.",
        number_format=styles.PERCENT_2,
        name="Equity_XIRR",
        source="Uses actual dates, so it is the right metric if the period "
        "spacing is ever made uneven.",
    )
    sw.scalar(
        "Equity NPV",
        f"=NPV(Discount_Rate_Per_Period,{first_operating}:{last_operating})"
        f"+{sw.local(equity_cf.row, 0, absolute=True)}",
        unit="$",
        number_format=styles.MONEY,
        name="Equity_NPV",
        source="Discounted at the equity discount rate on Inputs. The period-0 "
        "contribution is undiscounted.",
    )
    sw.scalar(
        "Equity MOIC",
        f"=SUM({_range(sw, distributions)})/Equity_At_COD",
        unit="x",
        number_format=styles.RATIO,
        name="Equity_MOIC",
    )
    sw.scalar(
        "Payback",
        f'=IF(COUNTIF({cum_range},"<0")=0,"n/a",'
        f'IF(COUNTIF({cum_range},"<0")>=Periods_Total+1,"not within project life",'
        f'(COUNTIF({cum_range},"<0")-1'
        f'+(-INDEX({cum_range},COUNTIF({cum_range},"<0")))'
        f'/INDEX({cf_range},COUNTIF({cum_range},"<0")+1))/Periods_Per_Year))',
        unit="years",
        number_format=styles.YEARS,
        name="Equity_Payback_Years",
        source="Undiscounted, interpolated within the crossing period. Assumes "
        "cumulative cash crosses zero once.",
    )
    sw.skip()

    # ------------------------------------------------------------------
    # Cost of capital
    # ------------------------------------------------------------------
    sw.section("Cost of capital")
    sw.scalar(
        "Effective cost of senior debt (all-in, incl. fees)",
        f"=(1+IRR({lender_range}))^Periods_Per_Year-1",
        unit="% p.a.",
        number_format=styles.PERCENT_2,
        name="Effective_Cost_Of_Debt",
        source="Always above the coupon, because the borrower receives the "
        "facility net of the fees it funds out of it.",
    )
    sw.scalar(
        "After-tax cost of senior debt",
        "=Effective_Cost_Of_Debt*(1-Tax_Rate)",
        unit="% p.a.",
        number_format=styles.PERCENT_2,
        name="After_Tax_Cost_Of_Debt",
    )
    sw.scalar(
        "Weighted average cost of capital",
        "=Debt_At_COD/(Debt_At_COD+Equity_At_COD)*After_Tax_Cost_Of_Debt"
        "+Equity_At_COD/(Debt_At_COD+Equity_At_COD)*Equity_IRR",
        unit="% p.a.",
        style=styles.TOTAL,
        number_format=styles.PERCENT_2,
        name="WACC",
        source="Weighted at COD on the funded capital structure, with equity "
        "costed at the achieved equity IRR.",
    )
    sw.skip()
    sw.note(
        "The equity IRR here is measured with the whole equity contribution "
        "landing at COD. Equity is in practice drawn across construction, "
        "which lowers the true IRR slightly - see the Notes sheet."
    )
    sw.freeze("D6")


def _range(sw, ref) -> str:
    first = sw.local(ref.row, sw.start_period, absolute=True)
    last = sw.local(ref.row, sw.last_period, absolute=True)
    return f"{first}:{last}"
