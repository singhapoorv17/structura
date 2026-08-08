"""Summary - the one page that goes in front of a credit committee.

Nothing is computed here. Every figure is a link, so the front sheet cannot
disagree with the model behind it - the single most common failure mode in a
hand-built deal model. If a number on this page looks wrong, the fault is
upstream, and the link tells you exactly where upstream.

Three blocks, in the order a credit officer reads them: what the facility is,
which test binds it, and whether the deal passes.
"""

from __future__ import annotations

from export import styles
from export.model import DISCLAIMER, ModelBundle
from export.workbook import WorkbookBuilder

__all__ = ["SHEET_NAME", "build"]

SHEET_NAME = "Summary"

_COL_LABEL = 1
_COL_UNIT = 2
_COL_VALUE = 3
_COL_LIMIT = 4
_COL_ACTUAL = 5
_COL_NOTE = 7


def build(wb: WorkbookBuilder, model: ModelBundle) -> None:
    """Write the Summary sheet."""
    sw = wb.create_sheet(SHEET_NAME, n_periods=0)
    sw.hide_gridlines()
    for col, width in (
        ("A", 48),
        ("B", 13),
        ("C", 18),
        ("D", 14),
        ("E", 14),
        ("F", 11),
        ("G", 62),
    ):
        sw.ws.column_dimensions[col].width = width

    sw.title_block(
        f"Structura - {model.project.name}",
        f"Senior debt sizing and cash waterfall. Generated "
        f"{model.generated_on.isoformat()}. All figures are links to the "
        f"sheets behind them; open the workbook and change any blue cell.",
    )

    # ------------------------------------------------------------------
    sw.section("The deal", _COL_NOTE)
    sw.scalar("Project", "=Project_Name")
    sw.scalar("Technology", "=Technology_Name")
    sw.scalar("Installed capacity", "=Capacity_MW", unit="MW",
              number_format=styles.NUMBER_0)
    sw.scalar("Commercial operation date", "=COD_Date", unit="date",
              number_format=styles.DATE_FMT)
    sw.scalar("Project life", "=Project_Life_Years", unit="years",
              number_format=styles.NUMBER_0)
    sw.skip()

    # ------------------------------------------------------------------
    sw.section("Headline result", _COL_NOTE)
    sw.scalar(
        "Senior debt sized",
        "=Senior_Debt",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
    )
    sw.scalar(
        "Binding constraint",
        "=Binding_Constraint",
        style=styles.TOTAL,
        source="Which credit test actually sets the quantum. Practitioners "
        "care about this as much as about the number.",
    )
    sw.scalar("Gearing", "=Gearing_Achieved", unit="% of TPC",
              number_format=styles.PERCENT_1)
    sw.scalar("Tenor", "=Debt_Periods/Periods_Per_Year", unit="years",
              number_format=styles.YEARS)
    sw.scalar("Weighted average life", "=Debt_WAL_Years", unit="years",
              number_format=styles.YEARS)
    sw.scalar("Minimum DSCR", "=Min_DSCR_Achieved", unit="x",
              number_format=styles.RATIO)
    sw.scalar("LLCR at COD", "=LLCR_At_COD", unit="x",
              number_format=styles.RATIO)
    sw.scalar("PLCR at COD", "=PLCR_At_COD", unit="x",
              number_format=styles.RATIO)
    sw.scalar("All-in cost of senior debt", "=Effective_Cost_Of_Debt",
              unit="% p.a.", number_format=styles.PERCENT_2)
    sw.skip()

    # ------------------------------------------------------------------
    sw.section("Sponsor economics", _COL_NOTE)
    sw.scalar("Sponsor equity at COD", "=Equity_At_COD", unit="$",
              number_format=styles.MONEY)
    sw.scalar("Equity IRR", "=Equity_IRR", unit="% p.a.",
              style=styles.TOTAL, number_format=styles.PERCENT_2)
    sw.scalar("Equity NPV", "=Equity_NPV", unit="$",
              number_format=styles.MONEY,
              source="At the equity discount rate on Inputs.")
    sw.scalar("Equity MOIC", "=Equity_MOIC", unit="x",
              number_format=styles.RATIO)
    sw.scalar("Payback", "=Equity_Payback_Years", unit="years",
              number_format=styles.YEARS)
    sw.scalar("Weighted average cost of capital", "=WACC", unit="% p.a.",
              number_format=styles.PERCENT_2)
    sw.skip()

    # ------------------------------------------------------------------
    sw.section("Sources and uses", _COL_NOTE)
    sw.scalar("USES", "", label_style=styles.SUBHEAD)
    sw.scalar("Construction capital cost", "=Capex", unit="$",
              number_format=styles.MONEY)
    sw.scalar("Upfront / arrangement fee", "=Upfront_Fee_Amount", unit="$",
              number_format=styles.MONEY)
    sw.scalar("Commitment fee", "=Commitment_Fee_Total", unit="$",
              number_format=styles.MONEY)
    sw.scalar("Interest during construction (IDC)", "=IDC", unit="$",
              number_format=styles.MONEY)
    sw.scalar("Initial debt service reserve (DSRA)", "=DSRA_Initial", unit="$",
              number_format=styles.MONEY)
    sw.scalar("Total uses", "=Total_Uses", unit="$", style=styles.TOTAL,
              number_format=styles.MONEY, label_style=styles.SUBHEAD)
    sw.skip()
    sw.scalar("SOURCES", "", label_style=styles.SUBHEAD)
    sw.scalar("Senior debt", "=Debt_At_COD", unit="$",
              number_format=styles.MONEY)
    sw.scalar("Sponsor equity", "=Equity_At_COD", unit="$",
              number_format=styles.MONEY)
    sw.scalar("Total sources", "=Total_Sources", unit="$", style=styles.TOTAL,
              number_format=styles.MONEY, label_style=styles.SUBHEAD)
    sw.scalar(
        "Check: sources less uses",
        "=Total_Sources-Total_Uses",
        unit="$",
        style=styles.CHECK,
        number_format=styles.NUMBER_2,
    )
    sw.skip()

    # ------------------------------------------------------------------
    sw.section("Credit tests", _COL_NOTE)
    _test_header(sw)
    _test(sw, "Minimum DSCR", "=Target_DSCR", "=Min_DSCR_Achieved",
          '=IF(Min_DSCR_Achieved>=Target_DSCR-0.0005,"PASS","FAIL")',
          styles.RATIO, "Sculpted to the target, so it lands on it unless "
          "another test cuts the quantum.")
    _test(sw, "Maximum gearing", "=Max_Gearing", "=Gearing_Achieved",
          '=IF(Gearing_Achieved<=Max_Gearing+0.0005,"PASS","FAIL")',
          styles.PERCENT_1, "Debt / total funded project cost.")
    _test(sw, "Tenor", "=Tenor_Years", "=Debt_Periods/Periods_Per_Year",
          '=IF(Debt_Periods<=Tenor_Periods,"PASS","FAIL")',
          styles.YEARS, "Shortened automatically if the tail test bites.")
    _test(sw, "Tail", "=Tail_Years", "=Tail_Achieved_Years",
          '=IF(Tail_Achieved_Years>=Tail_Years-0.0005,"PASS","FAIL")',
          styles.YEARS, "The asset must outlive the loan.")
    _test(sw, "Minimum LLCR", "=Min_LLCR", "=LLCR_At_COD",
          '=IF(Min_LLCR=0,"not tested",'
          'IF(LLCR_At_COD>=Min_LLCR-0.0005,"PASS","FAIL"))',
          styles.RATIO, "PV of CFADS to maturity at the debt rate / debt.")
    _test(sw, "Minimum PLCR", "=Min_PLCR", "=PLCR_At_COD",
          '=IF(Min_PLCR=0,"not tested",'
          'IF(PLCR_At_COD>=Min_PLCR-0.0005,"PASS","FAIL"))',
          styles.RATIO, "Same, with the horizon run to end of project life.")
    _test(sw, "DSCR covenant", "=Covenant_DSCR", "=Min_DSCR_Waterfall",
          '=IF(Covenant_DSCR=0,"not tested",'
          'IF(Min_DSCR_Waterfall>=Covenant_DSCR-0.0005,"PASS","FAIL"))',
          styles.RATIO, "Measured after the waterfall, including any sweep.")
    _test(sw, "Debt service met in full", "=0", "=Total_DS_Shortfall",
          '=IF(Total_DS_Shortfall<=0.01,"PASS","FAIL")',
          styles.MONEY, "Shortfall remaining after the DSRA has been drawn.")
    sw.skip()

    # ------------------------------------------------------------------
    sw.section("Model integrity checks", _COL_NOTE)
    sw.scalar(
        "Construction circularity converged",
        "=Circularity_Check",
        unit="$",
        style=styles.CHECK,
        number_format=styles.NUMBER_2,
        source="Zero when Excel's iterative calculation has settled. If it is "
        "not zero, switch on File > Options > Formulas > Enable iterative "
        "calculation (the workbook asks for this automatically).",
    )
    sw.scalar(
        "Senior facility amortised in full at maturity",
        "=Final_Balance_Check",
        unit="$",
        style=styles.CHECK,
        number_format=styles.NUMBER_2,
        source="The PV identity behind the sculpt forces this to zero.",
    )
    sw.scalar(
        "Sponsor cash conserved (waterfall)",
        f"=SUM({wb.span('wf.cash_check')})",
        unit="$",
        style=styles.CHECK,
        number_format=styles.NUMBER_2,
        source="Sources less uses, summed over every period of the waterfall.",
    )
    sw.skip()

    sw.write(_COL_LABEL, sw.row, "Disclaimer", styles.SUBHEAD)
    sw.row += 1
    sw.write(_COL_LABEL, sw.row, DISCLAIMER, styles.NOTE)
    sw.row += 1
    sw.write(
        _COL_LABEL,
        sw.row,
        "Structura is MIT-licensed open source. Market defaults are drawn from "
        "public sources only - see the Notes sheet for the full attribution.",
        styles.NOTE,
    )
    sw.freeze("A5")


# ---------------------------------------------------------------------------


def _test_header(sw) -> None:
    for col, text in (
        (_COL_LABEL, "Test"),
        (_COL_VALUE, "Limit"),
        (_COL_LIMIT, "Achieved"),
        (_COL_ACTUAL, "Result"),
        (_COL_NOTE, "Note"),
    ):
        sw.write(col, sw.row, text, styles.HEADER)
    sw.row += 1


def _test(sw, label, limit, actual, verdict, fmt, note) -> None:
    sw.write(_COL_LABEL, sw.row, label, styles.LABEL)
    sw.write(_COL_VALUE, sw.row, limit, styles.FORMULA, fmt)
    sw.write(_COL_LIMIT, sw.row, actual, styles.FORMULA, fmt)
    sw.write(_COL_ACTUAL, sw.row, verdict, styles.TOTAL)
    sw.write(_COL_NOTE, sw.row, note, styles.NOTE)
    sw.row += 1
