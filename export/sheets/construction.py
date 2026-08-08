"""Construction - the drawdown schedule, IDC, fees and sources & uses.

THE CIRCULARITY LIVES HERE
--------------------------
Total project cost is not an input. It is::

    TPC = capex + upfront fee + commitment fee + IDC + initial DSRA

and every term after ``capex`` depends on the size of the debt, while the debt
in turn depends on total project cost through the gearing cap::

    D = MIN( D_DSCR , max_gearing x TPC )

That is a genuine fixed point, and it is why ``openpyxl`` is used: it is the
only writer that can set ``iterate="1"``, so
this is the only toolchain in which the exported workbook resolves the loop
natively instead of opening with a circular-reference warning.

The loop is closed by one cell. Debt-funded capex is defined as::

    X = D - upfront fee - IDC - commitment fee

which is exactly the statement "the facility, once it has paid its own fees and
capitalised its own interest, funds this much hard cost". IDC and the
commitment fee come out of the monthly grid, which is driven by ``X``. Excel
iterates the pair to convergence; Python solves the identical fixed point with
Brent's method in ``engine/circularity.py``. Both paths must agree, and the
test suite asserts that they do.

Conventions (identical to the engine, so the two answers are comparable):

* Draws land at the **start** of the month and interest accrues on the balance
  after the draw. This is the lender's convention; a mid-month convention would
  understate IDC by roughly half a month.
* IDC and the commitment fee are **capitalised** into the construction loan.
* The upfront fee is drawn in full at first utilisation and financed by the
  facility itself.
* The initial DSRA is funded at COD and therefore accrues no IDC.
"""

from __future__ import annotations

from export import styles
from export.model import ModelBundle
from export.workbook import WorkbookBuilder

__all__ = ["SHEET_NAME", "build"]

SHEET_NAME = "Construction"


def build(wb: WorkbookBuilder, model: ModelBundle) -> None:
    """Write the Construction sheet."""
    months = model.construction_months
    sw = wb.create_sheet(SHEET_NAME, n_periods=months)
    sw.hide_gridlines()
    sw.set_widths(period=11.0)
    sw.title_block(
        "Construction funding",
        "Monthly drawdown, interest during construction, fees and the "
        "sources & uses. The IDC / debt-size / fee circularity is live.",
    )
    sw.period_header(label="Construction month", total_label="Total")
    L = sw.local

    # ------------------------------------------------------------------
    # The circular block
    # ------------------------------------------------------------------
    sw.section("Financing costs (circular - resolved by iterative calculation)")
    sw.scalar(
        "Upfront / arrangement fee",
        "=Upfront_Fee_Pct*Senior_Debt",
        unit="$",
        number_format=styles.MONEY,
        name="Upfront_Fee_Amount",
    )
    sw.scalar(
        "Debt-funded capex",
        "=Senior_Debt-Upfront_Fee_Amount-IDC-Commitment_Fee_Total",
        unit="$",
        number_format=styles.MONEY,
        name="Debt_Funded_Capex",
        source="Closes the circularity: the facility, net of its own fees and "
        "capitalised interest, funds this much hard cost.",
    )
    sw.scalar(
        "Equity-funded capex",
        "=Capex-Debt_Funded_Capex",
        unit="$",
        number_format=styles.MONEY,
        name="Equity_Funded_Capex",
    )
    sw.skip()

    # ------------------------------------------------------------------
    # Monthly grid
    # ------------------------------------------------------------------
    sw.section("Monthly drawdown")
    month = sw.values_row(
        "con.month",
        "Month",
        list(sw.periods()),
        unit="#",
        style=styles.NOTE,
        number_format=styles.NUMBER_0,
    )
    raw_weight = sw.values_row(
        "con.capex_weight_raw",
        "Capex S-curve weight (input)",
        _capex_weights(model, months),
        unit="share",
        style=styles.INPUT,
        number_format="0.0000",
        total=True,
    )
    active = sw.formula_row(
        "con.capex_weight_active",
        "Weight within the construction period",
        lambda m: (
            f"IF({L(month.row, m)}<=Construction_Months,{L(raw_weight.row, m)},0)"
        ),
        unit="share",
        number_format="0.0000",
        total=True,
    )
    active_range = _range(sw, active)
    weight = sw.formula_row(
        "con.capex_weight",
        "Normalised weight",
        lambda m: (
            f"IF(SUM({active_range})>0,{L(active.row, m)}/SUM({active_range}),"
            f"IF({L(month.row, m)}=1,1,0))"
        ),
        unit="share",
        number_format="0.0000",
        total=True,
    )
    capex_draw = sw.formula_row(
        "con.capex_draw",
        "Capex spend",
        lambda m: f"Capex*{L(weight.row, m)}",
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    debt_capex_draw = sw.formula_row(
        "con.debt_capex_draw",
        "Debt funding of capex",
        lambda m: f"Debt_Funded_Capex*{L(weight.row, m)}",
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    fee_draw = sw.formula_row(
        "con.fee_draw",
        "Upfront fee drawn",
        lambda m: f"IF({L(month.row, m)}=1,Upfront_Fee_Amount,0)",
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    debt_draw = sw.formula_row(
        "con.debt_draw",
        "Total debt drawn",
        lambda m: f"{L(debt_capex_draw.row, m)}+{L(fee_draw.row, m)}",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        total=True,
        series_name="Debt_Draw_Series",
    )
    sw.formula_row(
        "con.equity_draw",
        "Equity funding of capex",
        lambda m: f"{L(capex_draw.row, m)}-{L(debt_capex_draw.row, m)}",
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    sw.skip()

    # ------------------------------------------------------------------
    # Construction loan balance
    # ------------------------------------------------------------------
    sw.section("Construction facility balance")
    opening = sw.formula_row(
        "con.opening_balance",
        "Opening balance",
        lambda m: (
            "0" if m == sw.start_period else f"{L(sw.row + 5, m - 1)}"
        ),
        unit="$",
        number_format=styles.MONEY,
    )
    after_draw = sw.formula_row(
        "con.balance_after_draw",
        "Balance after drawdown",
        lambda m: f"{L(opening.row, m)}+{L(debt_draw.row, m)}",
        unit="$",
        number_format=styles.MONEY,
    )
    interest = sw.formula_row(
        "con.interest",
        "Interest during construction (IDC)",
        lambda m: (
            f"IF(Construction_Months>0,"
            f"{L(after_draw.row, m)}*Interest_Rate/12,0)"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
        series_name="IDC_Monthly_Series",
    )
    undrawn = sw.formula_row(
        "con.undrawn",
        "Undrawn commitment",
        lambda m: f"MAX(Senior_Debt-{L(after_draw.row, m)},0)",
        unit="$",
        number_format=styles.MONEY,
    )
    commitment = sw.formula_row(
        "con.commitment_fee",
        "Commitment fee",
        lambda m: (
            f"IF(Construction_Months>0,"
            f"{L(undrawn.row, m)}*Commitment_Fee_Pct/12,0)"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    closing = sw.formula_row(
        "con.closing_balance",
        "Closing balance",
        lambda m: (
            f"{L(after_draw.row, m)}+{L(interest.row, m)}+{L(commitment.row, m)}"
        ),
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
    )
    assert closing.row == opening.row + 5, "opening-balance back-link mis-wired"
    sw.skip()

    # ------------------------------------------------------------------
    # Totals
    # ------------------------------------------------------------------
    sw.section("Funding requirement")
    sw.scalar(
        "Interest during construction (IDC)",
        f"=SUM({_range(sw, interest)})",
        unit="$",
        number_format=styles.MONEY,
        name="IDC",
    )
    sw.scalar(
        "Commitment fee",
        f"=SUM({_range(sw, commitment)})",
        unit="$",
        number_format=styles.MONEY,
        name="Commitment_Fee_Total",
    )
    sw.scalar(
        "Total project cost (funded basis)",
        "=Capex+Upfront_Fee_Amount+Commitment_Fee_Total+IDC+DSRA_Initial",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        name="Total_Project_Cost",
    )
    sw.scalar(
        "Senior debt at COD",
        f"={L(closing.row, sw.last_period)}"
        "+IF(DSRA_Debt_Funded=1,DSRA_Initial,0)",
        unit="$",
        number_format=styles.MONEY,
        name="Debt_At_COD",
        source="The construction facility rolls into the term facility at COD.",
    )
    sw.scalar(
        "Sponsor equity at COD",
        "=Total_Project_Cost-Debt_At_COD",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        name="Equity_At_COD",
    )
    sw.scalar(
        "Gearing",
        "=Debt_At_COD/Total_Project_Cost",
        unit="% of TPC",
        number_format=styles.PERCENT_1,
        name="Gearing_Achieved",
    )
    sw.scalar(
        "Check: construction balance less facility sized",
        f"={L(closing.row, sw.last_period)}-Senior_Debt",
        unit="$",
        style=styles.CHECK,
        number_format=styles.NUMBER_2,
        name="Circularity_Check",
        source="Zero when the circularity has converged.",
    )
    sw.skip()

    # ------------------------------------------------------------------
    # Sources and uses
    # ------------------------------------------------------------------
    sw.section("Sources and uses")
    sw.scalar("USES", "", label_style=styles.SUBHEAD)
    sw.scalar("Construction capital cost", "=Capex", unit="$",
              number_format=styles.MONEY)
    sw.scalar("Upfront / arrangement fee", "=Upfront_Fee_Amount", unit="$",
              number_format=styles.MONEY)
    sw.scalar("Commitment fee", "=Commitment_Fee_Total", unit="$",
              number_format=styles.MONEY)
    sw.scalar("Interest during construction", "=IDC", unit="$",
              number_format=styles.MONEY)
    sw.scalar("Initial debt service reserve (DSRA)", "=DSRA_Initial", unit="$",
              number_format=styles.MONEY)
    uses_row = sw.scalar(
        "Total uses",
        "=Total_Project_Cost",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        name="Total_Uses",
    )
    sw.skip()
    sw.scalar("SOURCES", "", label_style=styles.SUBHEAD)
    sw.scalar("Senior debt", "=Debt_At_COD", unit="$",
              number_format=styles.MONEY)
    sw.scalar("Sponsor equity", "=Equity_At_COD", unit="$",
              number_format=styles.MONEY)
    sw.scalar(
        "Total sources",
        "=Debt_At_COD+Equity_At_COD",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        name="Total_Sources",
    )
    sw.scalar(
        "Check: sources less uses",
        "=Total_Sources-Total_Uses",
        unit="$",
        style=styles.CHECK,
        number_format=styles.NUMBER_2,
    )
    assert uses_row > 0
    sw.freeze("D6")


def _capex_weights(model: ModelBundle, months: int) -> list[float]:
    """The normalised monthly capex S-curve, padded to the grid width."""
    curve = list(model.project.normalised_capex_curve())
    if not curve:
        curve = [1.0]
    return [curve[m] if m < len(curve) else 0.0 for m in range(months)]


def _range(sw, ref) -> str:
    first = sw.local(ref.row, sw.start_period, absolute=True)
    last = sw.local(ref.row, sw.last_period, absolute=True)
    return f"{first}:{last}"
