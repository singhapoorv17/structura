"""Inputs - every driver of the model, as a named, blue, editable cell.

WHY EVERYTHING HERE IS AN INPUT AND NOTHING HERE IS A FORMULA
--------------------------------------------------------------
This sheet is the model's only source of exogenous truth. If a number can be
derived from another number it does not belong here - it belongs on the sheet
that derives it. Keeping that boundary clean is what lets a credit officer
answer "what did you assume?" by reading one page.

Two exceptions are marked as such:

* A short **derived** block at the foot restates a handful of unit conversions
  (rate per period, periods in the tenor). They are formulas, black, and exist
  so that the rest of the workbook never divides by 12 in-line.
* One **solver-derived input** - the applied grace period - sits in an amber
  cell. See the Notes sheet: it is the only quantity in the workbook that
  Structura's Python solver produces and Excel cannot re-derive.

Every cell here carries a workbook-scoped defined name, so formulas elsewhere
read ``=Production_Year1_MWh*(1-Degradation)^Escalation_Steps`` rather than
``=$C$21*(1-$C$24)^D8``.
"""

from __future__ import annotations

from export import styles
from export.model import ModelBundle
from export.workbook import WorkbookBuilder

__all__ = ["SHEET_NAME", "build"]

SHEET_NAME = "Inputs"

_LAST_COL = 8  # section banding runs A..H


def build(wb: WorkbookBuilder, model: ModelBundle) -> None:
    """Write the Inputs sheet."""
    sw = wb.create_sheet(SHEET_NAME, n_periods=0)
    sw.hide_gridlines()
    sw.ws.column_dimensions["A"].width = 46
    sw.ws.column_dimensions["B"].width = 22
    sw.ws.column_dimensions["C"].width = 18
    sw.ws.column_dimensions["D"].width = 74

    p = model.project
    t = model.terms

    sw.title_block(
        "Inputs and assumptions",
        "Blue cells are inputs - change them and the whole model recalculates. "
        "Amber cells are solver-derived (see Notes). Black cells are formulas.",
    )

    def inp(label, value, unit, name, fmt, source=""):
        return sw.scalar(
            label,
            value,
            unit=unit,
            style=styles.INPUT,
            number_format=fmt,
            name=name,
            source=source,
        )

    def der(label, formula, unit, name, fmt, source=""):
        return sw.scalar(
            label,
            f"={formula}",
            unit=unit,
            style=styles.FORMULA,
            number_format=fmt,
            name=name,
            source=source,
        )

    # -- project ------------------------------------------------------------
    sw.section("1. Project", _LAST_COL)
    sw.scalar(
        "Project name",
        p.name,
        style=styles.INPUT,
        name="Project_Name",
    )
    sw.scalar(
        "Technology",
        p.technology.value,
        style=styles.INPUT,
        name="Technology_Name",
    )
    inp("Installed capacity", p.capacity_mw, "MW", "Capacity_MW", styles.NUMBER_0)
    inp(
        "Commercial operation date (COD)",
        model.cod,
        "date",
        "COD_Date",
        styles.DATE_FMT,
    )
    inp(
        "Project life",
        p.project_life_years,
        "years",
        "Project_Life_Years",
        styles.NUMBER_0,
    )
    inp(
        "Model frequency",
        p.periods_per_year,
        "periods p.a.",
        "Periods_Per_Year",
        styles.NUMBER_0,
        "1 = annual, 2 = semi-annual, 4 = quarterly, 12 = monthly.",
    )
    sw.skip()

    # -- capital cost -------------------------------------------------------
    sw.section("2. Capital cost and construction", _LAST_COL)
    inp("Construction capital cost (capex)", p.capex, "$", "Capex", styles.MONEY,
        "Hard cost only. Financing costs are built up on the Construction sheet.")
    inp(
        "Construction period",
        p.construction_months,
        "months",
        "Construction_Months",
        styles.NUMBER_0,
        "The monthly drawdown grid on Construction is built to this length.",
    )
    sw.skip()

    # -- production ---------------------------------------------------------
    sw.section("3. Production", _LAST_COL)
    inp(
        "Year 1 net production",
        p.production,
        "MWh",
        "Production_Year1_MWh",
        styles.NUMBER_0,
        f"Exceedance case: {p.production_case.value.upper()}.",
    )
    inp(
        "Annual degradation",
        p.degradation,
        "% p.a.",
        "Degradation",
        styles.PERCENT_2,
        "Compounds on an operating-year basis: year n = year 1 x (1-d)^(n-1).",
    )
    sw.skip()

    # -- revenue ------------------------------------------------------------
    sw.section("4. Revenue", _LAST_COL)
    inp(
        "Contracted price, year 1",
        p.contracted_price,
        "$/MWh",
        "Contracted_Price",
        styles.PRICE,
    )
    inp(
        "Contracted share of production",
        p.contracted_share,
        "% of MWh",
        "Contracted_Share",
        styles.PERCENT_1,
    )
    inp(
        "Contracted price escalation",
        p.contracted_escalation,
        "% p.a.",
        "Contracted_Escalation",
        styles.PERCENT_2,
    )
    inp(
        "Offtake term",
        p.contract_years,
        "years",
        "Contract_Years",
        styles.NUMBER_0,
        "After expiry, 100% of volume prices at the merchant curve.",
    )
    inp(
        "Merchant price, year 1",
        p.merchant_price,
        "$/MWh",
        "Merchant_Price",
        styles.PRICE,
        "No free source exists for forward PPA/merchant curves - user input.",
    )
    inp(
        "Merchant price escalation",
        p.merchant_escalation,
        "% p.a.",
        "Merchant_Escalation",
        styles.PERCENT_2,
    )
    sw.skip()

    # -- operating cost -----------------------------------------------------
    sw.section("5. Operating cost", _LAST_COL)
    inp("Operating cost, year 1", p.opex_year1, "$ p.a.", "Opex_Year1", styles.MONEY)
    inp(
        "Operating cost escalation",
        p.opex_escalation,
        "% p.a.",
        "Opex_Escalation",
        styles.PERCENT_2,
    )
    sw.skip()

    # -- tax ----------------------------------------------------------------
    sw.section("6. Project-level tax", _LAST_COL)
    inp(
        "Tax treatment",
        model.tax_code,
        "code",
        "Tax_Treatment_Code",
        styles.NUMBER_0,
        "1 = none (CFADS pre-tax, the market convention for sizing) | "
        "2 = tax before the interest deduction | 3 = full, interest deductible.",
    )
    inp("Corporate tax rate", p.tax_rate, "%", "Tax_Rate", styles.PERCENT_1,
        "Federal only. IRC s.11(b), 21%.")
    inp(
        "Book depreciation life",
        p.depreciation_years,
        "years",
        "Depreciation_Years",
        styles.NUMBER_0,
        "Straight line. MACRS, bonus and the ITC basis reduction live in "
        "engine/tax and are not on this sheet.",
    )
    sw.skip()

    # -- senior debt --------------------------------------------------------
    sw.section("7. Senior debt terms", _LAST_COL)
    scalar_target = model.scalar_target_dscr
    if scalar_target is not None:
        inp(
            "Target DSCR (sizing)",
            scalar_target,
            "x",
            "Target_DSCR",
            styles.RATIO,
            "The sculpting target. This is the single most sensitive input in "
            "the model - change it and the debt quantum moves immediately.",
        )
    else:
        # A time-varying target is written period by period on the Debt sheet;
        # the named cell still exists so downstream formulas are uniform, and
        # holds the minimum of the profile for reference.
        inp(
            "Target DSCR (minimum of profile)",
            min(model.target_dscr_profile),
            "x",
            "Target_DSCR",
            styles.RATIO,
            "Time-varying target: the period-by-period profile is a blue input "
            "row on the Debt sheet.",
        )
    inp("Tenor", t.tenor_years, "years", "Tenor_Years", styles.NUMBER_0)
    inp(
        "All-in interest rate",
        t.interest_rate,
        "% p.a.",
        "Interest_Rate",
        styles.RATE_3,
        "Base rate plus margin. Structura ships no rates feed; supply a live fix.",
    )
    inp(
        "Upfront / arrangement fee",
        t.upfront_fee,
        "% of facility",
        "Upfront_Fee_Pct",
        styles.PERCENT_2,
        "Drawn in full at first utilisation and financed by the facility.",
    )
    inp(
        "Commitment fee",
        t.commitment_fee,
        "% p.a. undrawn",
        "Commitment_Fee_Pct",
        styles.PERCENT_2,
    )
    inp(
        "Amortisation style",
        model.amortization_code,
        "code",
        "Amort_Style_Code",
        styles.NUMBER_0,
        "1 = sculpted to the DSCR target | 2 = level payment | "
        "3 = fixed principal. All three are sized live on the Debt sheet.",
    )
    inp(
        "Grace period (requested)",
        t.grace_period_months,
        "months",
        "Grace_Period_Months",
        styles.NUMBER_0,
        "Interest-only holiday at the front of the loan. Interest is paid "
        "current, not capitalised.",
    )
    inp(
        "Maximum gearing",
        t.max_gearing,
        "% of funded cost",
        "Max_Gearing",
        styles.PERCENT_1,
        "Debt / total funded project cost, including IDC, fees and the DSRA.",
    )
    inp(
        "Required tail",
        t.tail_years,
        "years",
        "Tail_Years",
        styles.NUMBER_0,
        "Project life less debt tenor. The asset must outlive the loan.",
    )
    inp(
        "DSRA cover",
        t.dsra_months,
        "months of DS",
        "DSRA_Months",
        styles.NUMBER_0,
        "Forward-looking: the reserve holds cover for the service about to "
        "fall due." if t.dsra_forward_looking else "Backward-looking.",
    )
    inp(
        "DSRA funded by debt",
        1 if t.dsra_debt_funded else 0,
        "1 = yes",
        "DSRA_Debt_Funded",
        styles.NUMBER_0,
    )
    inp(
        "Cash sweep",
        t.cash_sweep_pct,
        "% of surplus",
        "Cash_Sweep_Pct",
        styles.PERCENT_1,
        "Applied to prepay senior debt, in inverse order of maturity.",
    )
    inp(
        "DSCR covenant",
        t.covenant_dscr or 0.0,
        "x",
        "Covenant_DSCR",
        styles.RATIO,
        "Reporting only - the model flags a breach, it does not accelerate.",
    )
    inp(
        "Distribution lock-up DSCR",
        model.lockup_dscr or 0.0,
        "x",
        "Lockup_DSCR",
        styles.RATIO,
        "0 = no lock-up test. Below this DSCR, 100% of surplus is trapped.",
    )
    inp(
        "Minimum LLCR (sizing floor)",
        t.min_llcr or 0.0,
        "x",
        "Min_LLCR",
        styles.RATIO,
        "0 = not tested.",
    )
    inp(
        "Minimum PLCR (sizing floor)",
        t.min_plcr or 0.0,
        "x",
        "Min_PLCR",
        styles.RATIO,
        "0 = not tested.",
    )
    sw.skip()

    # -- returns ------------------------------------------------------------
    sw.section("8. Returns", _LAST_COL)
    inp(
        "Equity discount rate",
        model.discount_rate,
        "% p.a.",
        "Discount_Rate",
        styles.PERCENT_1,
        "Used for the equity NPV only. Not a cost of capital assertion.",
    )
    sw.skip()

    # -- derived ------------------------------------------------------------
    sw.section("9. Derived - unit conversions (formulas, not inputs)", _LAST_COL)
    der(
        "Model periods over project life",
        "ROUND(Project_Life_Years*Periods_Per_Year,0)",
        "periods",
        "Periods_Total",
        styles.NUMBER_0,
    )
    der(
        "Months per model period",
        "12/Periods_Per_Year",
        "months",
        "Period_Months",
        styles.NUMBER_0,
    )
    der(
        "Interest rate per period",
        "Interest_Rate/Periods_Per_Year",
        "% per period",
        "Rate_Per_Period",
        styles.RATE_3,
        "Nominal annual divided by frequency (money-market convention), which "
        "is how a credit agreement quotes a margin over a periodic index.",
    )
    der(
        "DSRA cover in model periods",
        "DSRA_Months/Period_Months",
        "periods",
        "DSRA_Periods",
        styles.NUMBER_2,
    )
    der(
        "Equity discount rate per period",
        "(1+Discount_Rate)^(1/Periods_Per_Year)-1",
        "% per period",
        "Discount_Rate_Per_Period",
        styles.RATE_3,
    )
    sw.skip()

    # -- solver-derived -----------------------------------------------------
    sw.section("10. Solver-derived input (amber - see Notes)", _LAST_COL)
    sw.scalar(
        "Grace period applied by the solver",
        model.solution.sizing.debt.grace_periods,
        unit="periods",
        style=styles.SOLVER_INPUT,
        number_format=styles.NUMBER_0,
        name="Grace_Periods",
        source=(
            "Structura lengthens the interest-only holiday until no period "
            "requires negative amortisation. That is a search, not an "
            "expression, so Excel cannot re-derive it. Everything downstream "
            "of this cell is a live formula."
        ),
    )
    sw.note(
        "Requested grace period, for comparison: "
        f"{model.terms.grace_periods(model.periods_per_year)} period(s)."
    )
    sw.skip()

    sw.note(
        "Sources for the market defaults behind these values: Norton Rose "
        "Fulbright, 'Cost of Capital: 2026 Outlook' (2026-01-29); standard "
        "non-recourse credit-agreement practice. See the Notes sheet."
    )
    sw.freeze("A5")
