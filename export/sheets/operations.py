"""Operations - the operating model, from MWh to CFADS.

Everything on this sheet is a live formula off the Inputs sheet. Nothing is
pasted. Change the merchant price, the degradation rate or the offtake term and
the CFADS row moves, which moves the sculpt, which moves the debt quantum.

Deliberately free of financing. A reviewer can sign off the operating model on
its own before looking at a single sculpting formula, which is the whole reason
the engine keeps ``engine/cashflow.py`` ignorant of debt.

The one financing reference on the sheet is the interest line inside the tax
build-up, and it is switched off unless the tax treatment is ``3`` (full).
Interest is tax-deductible, so cash tax depends on the debt schedule, which
depends on CFADS, which depends on cash tax - a genuine circular reference.
It resolves natively because the workbook is written with ``iterate="1"``.
"""

from __future__ import annotations

from export import styles
from export.model import ModelBundle
from export.workbook import WorkbookBuilder

__all__ = ["SHEET_NAME", "build"]

SHEET_NAME = "Operations"

#: Named range over the Debt sheet's interest row. Referenced by INDEX() here
#: rather than by cell address, so this sheet can be built before the Debt
#: sheet exists - Excel resolves defined names at calculation time, not at
#: write time.
SENIOR_INTEREST_SERIES = "Senior_Interest_Series"


def build(wb: WorkbookBuilder, model: ModelBundle) -> None:
    """Write the Operations sheet."""
    sw = wb.create_sheet(SHEET_NAME, n_periods=model.n_periods)
    sw.hide_gridlines()
    sw.set_widths()
    sw.title_block(
        "Operating model",
        "Revenue less operating cost less cash tax = CFADS. "
        "Every cell is a formula off Inputs; nothing on this sheet is pasted.",
    )
    sw.period_header()

    L = sw.local  # local same-sheet reference: L(row, period)

    period = sw.values_row(
        "ops.period",
        "Period",
        list(sw.periods()),
        unit="#",
        style=styles.NOTE,
        number_format=styles.NUMBER_0,
    )
    year = sw.formula_row(
        "ops.year",
        "Operating year",
        lambda t: f"INT(({L(period.row, t)}-1)/Periods_Per_Year)+1",
        unit="#",
        number_format=styles.NUMBER_0,
    )
    esc = sw.formula_row(
        "ops.escalation_steps",
        "Escalation / degradation steps applied",
        lambda t: f"{L(year.row, t)}-1",
        unit="#",
        number_format=styles.NUMBER_0,
    )
    sw.formula_row(
        "ops.date",
        "Period ending",
        lambda t: f"EDATE(COD_Date,Period_Months*{L(period.row, t)})",
        unit="date",
        number_format=styles.DATE_FMT,
    )
    sw.skip()

    # -- production ---------------------------------------------------------
    sw.section("Production")
    production = sw.formula_row(
        "ops.production",
        "Net production",
        lambda t: (
            f"Production_Year1_MWh*(1-Degradation)^{L(esc.row, t)}"
            f"/Periods_Per_Year"
        ),
        unit="MWh",
        number_format=styles.NUMBER_0,
        total=True,
    )
    sw.skip()

    # -- revenue ------------------------------------------------------------
    sw.section("Revenue")
    flag = sw.formula_row(
        "ops.contract_flag",
        "Under offtake contract",
        lambda t: (
            f"IF({L(period.row, t)}<=ROUND(Contract_Years*Periods_Per_Year,0),1,0)"
        ),
        unit="1 = yes",
        number_format=styles.NUMBER_0,
    )
    price_c = sw.formula_row(
        "ops.contracted_price",
        "Contracted price",
        lambda t: f"Contracted_Price*(1+Contracted_Escalation)^{L(esc.row, t)}",
        unit="$/MWh",
        number_format=styles.PRICE,
    )
    price_m = sw.formula_row(
        "ops.merchant_price",
        "Merchant price",
        lambda t: f"Merchant_Price*(1+Merchant_Escalation)^{L(esc.row, t)}",
        unit="$/MWh",
        number_format=styles.PRICE,
    )
    vol_c = sw.formula_row(
        "ops.contracted_volume",
        "Contracted volume",
        lambda t: (
            f"{L(production.row, t)}*Contracted_Share*{L(flag.row, t)}"
        ),
        unit="MWh",
        number_format=styles.NUMBER_0,
        total=True,
    )
    vol_m = sw.formula_row(
        "ops.merchant_volume",
        "Merchant volume",
        lambda t: f"{L(production.row, t)}-{L(vol_c.row, t)}",
        unit="MWh",
        number_format=styles.NUMBER_0,
        total=True,
    )
    rev_c = sw.formula_row(
        "ops.contracted_revenue",
        "Contracted revenue",
        lambda t: f"{L(vol_c.row, t)}*{L(price_c.row, t)}",
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    rev_m = sw.formula_row(
        "ops.merchant_revenue",
        "Merchant revenue",
        lambda t: f"{L(vol_m.row, t)}*{L(price_m.row, t)}",
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    revenue = sw.formula_row(
        "ops.revenue",
        "Total revenue",
        lambda t: f"{L(rev_c.row, t)}+{L(rev_m.row, t)}",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        total=True,
        series_name="Revenue_Series",
    )
    sw.skip()

    # -- operating cost -----------------------------------------------------
    sw.section("Operating cost and EBITDA")
    opex = sw.formula_row(
        "ops.opex",
        "Operating expenditure",
        lambda t: (
            f"Opex_Year1*(1+Opex_Escalation)^{L(esc.row, t)}/Periods_Per_Year"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
        series_name="Opex_Series",
    )
    ebitda = sw.formula_row(
        "ops.ebitda",
        "EBITDA",
        lambda t: f"{L(revenue.row, t)}-{L(opex.row, t)}",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        total=True,
        series_name="EBITDA_Series",
    )
    sw.skip()

    # -- tax ----------------------------------------------------------------
    sw.section("Project-level cash tax")
    sw.note(
        "Tax treatment 1 (the default, and the market convention for debt "
        "sizing) leaves CFADS pre-tax because tax attributes sit in a structure "
        "modelled above the project. Treatment 3 deducts senior interest, which "
        "makes this block circular - resolved by iterative calculation."
    )
    depreciation = sw.formula_row(
        "ops.depreciation",
        "Book depreciation (straight line)",
        lambda t: (
            f"IF(AND(Depreciation_Years>0,{L(year.row, t)}-1<Depreciation_Years),"
            f"Capex/Depreciation_Years/Periods_Per_Year,0)"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    interest = sw.formula_row(
        "ops.deductible_interest",
        "Senior interest (deductible)",
        lambda t: (
            f"IF(Tax_Treatment_Code=3,"
            f"INDEX({SENIOR_INTEREST_SERIES},{L(period.row, t)}),0)"
        ),
        unit="$",
        style=styles.LINK,
        number_format=styles.MONEY,
        total=True,
    )
    nol_bf = sw.formula_row(
        "ops.nol_brought_forward",
        "Tax loss brought forward",
        lambda t: "0" if t == sw.start_period else f"{L(sw.row + 3, t - 1)}",
        unit="$",
        number_format=styles.MONEY,
    )
    taxable = sw.formula_row(
        "ops.taxable_income",
        "Taxable income before losses",
        lambda t: (
            f"{L(ebitda.row, t)}-{L(depreciation.row, t)}-{L(interest.row, t)}"
        ),
        unit="$",
        number_format=styles.MONEY,
    )
    tax = sw.formula_row(
        "ops.cash_tax",
        "Cash tax",
        lambda t: (
            f"IF(OR(Tax_Treatment_Code=1,Tax_Rate<=0),0,"
            f"MAX(0,{L(taxable.row, t)}-{L(nol_bf.row, t)})*Tax_Rate)"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
        series_name="Cash_Tax_Series",
    )
    nol_cf = sw.formula_row(
        "ops.nol_carried_forward",
        "Tax loss carried forward",
        lambda t: (
            f"IF(OR(Tax_Treatment_Code=1,Tax_Rate<=0),0,"
            f"MAX(0,{L(nol_bf.row, t)}-{L(taxable.row, t)}))"
        ),
        unit="$",
        number_format=styles.MONEY,
    )
    # The brought-forward row was written before the carried-forward row
    # existed, so its forward reference was computed from the cursor. Assert the
    # arithmetic rather than trusting it.
    assert nol_cf.row == nol_bf.row + 3, (
        "the tax-loss carry-forward link is mis-wired: "
        f"brought forward on row {nol_bf.row}, carried forward on row {nol_cf.row}"
    )
    sw.skip()

    # -- CFADS --------------------------------------------------------------
    sw.section("Cash Flow Available for Debt Service")
    cfads = sw.formula_row(
        "ops.cfads",
        "CFADS",
        lambda t: f"{L(ebitda.row, t)}-{L(tax.row, t)}",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        total=True,
        series_name="CFADS_Series",
    )
    check = sw.formula_row(
        "ops.cfads_check",
        "Check: revenue less opex less tax less CFADS",
        lambda t: (
            f"{L(revenue.row, t)}-{L(opex.row, t)}-{L(tax.row, t)}"
            f"-{L(cfads.row, t)}"
        ),
        unit="$",
        style=styles.CHECK,
        number_format=styles.NUMBER_2,
    )
    wb.define_range(
        "CFADS_Check_Series",
        SHEET_NAME,
        check.row,
        check.first_col,
        check.first_col + check.n_periods - 1,
    )
    sw.skip()
    sw.note(
        "The check row must read zero in every period. It is the CFADS "
        "identity asserted inside the Python engine, restated in the workbook."
    )
    assert check.row > cfads.row
    sw.freeze("D6")
