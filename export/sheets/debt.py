"""Debt - the sizing tests, the sculpt, and the amortisation schedule.

LIVE FORMULAS
-------------
The exported model carries live formulas, not pasted values. This is the sheet
that most depends on it: the debt quantum, the sculpted service profile, the
interest / principal split, the DSCR row and the LLCR/PLCR rows are all
formulas. Change the target DSCR on Inputs and the facility re-sizes.

THE SCULPTING IDENTITY, WRITTEN IN EXCEL
----------------------------------------
Let ``C_t`` be CFADS, ``d_t`` the target DSCR, ``r`` the rate per period and
``g`` the grace period in whole periods.

1. Available service, period by period:      ``DS_t = C_t / d_t``
2. Debt quantum is the PV of that service:   ``D = SUM_{t>g} DS_t (1+r)^-(t-g)``
3. Split it off the actual balance:          ``I_t = r B_{t-1}``,
   ``P_t = DS_t - I_t``, ``B_t = B_{t-1} - P_t``

Step 2 is what forces step 3 to amortise to exactly zero at maturity, so no
iteration is needed anywhere in the sculpt. (The circularity in a project
finance model is in the *funding* - IDC, fees, DSRA - and lives on the
Construction sheet.)

All three amortisation styles are sized live and side by side, which is
information a credit committee actually wants: it shows how much debt capacity
the structure is leaving on the table. ``Amort_Style_Code`` selects which one
drives the schedule.

WHAT IS NOT A FORMULA
---------------------
One cell: the applied grace period, on Inputs, in amber. Structura lengthens
the interest-only holiday until no period requires negative amortisation, which
is a search rather than an expression. Everything downstream of it is live.
"""

from __future__ import annotations

from export import styles
from export.model import ModelBundle
from export.workbook import INFINITY_SENTINEL, WorkbookBuilder

__all__ = ["SHEET_NAME", "build"]

SHEET_NAME = "Debt"

#: Dollar tolerance used by the live binding-constraint test. Two sizing tests
#: that agree to within a dollar on a nine-figure facility are the same test.
_BINDING_TOLERANCE = "1"


def build(wb: WorkbookBuilder, model: ModelBundle) -> None:
    """Write the Debt sheet."""
    n = model.n_periods
    sw = wb.create_sheet(SHEET_NAME, n_periods=n)
    sw.hide_gridlines()
    sw.set_widths()
    sw.title_block(
        "Senior debt - sizing and amortisation",
        "Sculpted to the target DSCR. Quantum, service, interest, principal, "
        "DSCR, LLCR and PLCR are all live formulas.",
    )
    sw.period_header()
    L = sw.local

    # ------------------------------------------------------------------
    # Tenor, tail and grace
    # ------------------------------------------------------------------
    sw.section("Facility shape")
    sw.scalar(
        "Tenor requested",
        "=ROUND(Tenor_Years*Periods_Per_Year,0)",
        unit="periods",
        number_format=styles.NUMBER_0,
        name="Tenor_Periods",
    )
    sw.scalar(
        "Maximum tenor permitted by the tail test",
        "=Periods_Total-ROUND(Tail_Years*Periods_Per_Year,0)",
        unit="periods",
        number_format=styles.NUMBER_0,
        name="Tail_Max_Periods",
        source="Project life less the tail the lender requires.",
    )
    sw.scalar(
        "Debt periods applied",
        "=MIN(Tenor_Periods,Tail_Max_Periods)",
        unit="periods",
        style=styles.TOTAL,
        number_format=styles.NUMBER_0,
        name="Debt_Periods",
    )
    sw.scalar(
        "Grace period requested",
        "=INT(Grace_Period_Months*Periods_Per_Year/12)",
        unit="periods",
        number_format=styles.NUMBER_0,
        name="Grace_Periods_Requested",
    )
    sw.scalar(
        "Grace period applied (solver-derived, see Inputs)",
        "=Grace_Periods",
        unit="periods",
        style=styles.LINK,
        number_format=styles.NUMBER_0,
    )
    sw.scalar(
        "Amortising periods",
        "=Debt_Periods-Grace_Periods",
        unit="periods",
        number_format=styles.NUMBER_0,
        name="Amortising_Periods",
    )
    sw.scalar(
        "Annuity factor over the amortising periods",
        "=IF(Rate_Per_Period=0,Amortising_Periods,"
        "(1-(1+Rate_Per_Period)^-Amortising_Periods)/Rate_Per_Period)",
        unit="x",
        number_format=styles.NUMBER_2,
        name="Annuity_Factor",
        source="PV of 1 per period in arrears. Used by the level-payment test.",
    )
    sw.scalar(
        "Tail achieved",
        "=(Periods_Total-Debt_Periods)/Periods_Per_Year",
        unit="years",
        number_format=styles.YEARS,
        name="Tail_Achieved_Years",
    )
    sw.skip()

    # ------------------------------------------------------------------
    # Sculpting build-up
    # ------------------------------------------------------------------
    sw.section("Sculpting build-up")
    period = sw.values_row(
        "debt.period",
        "Period",
        list(sw.periods()),
        unit="#",
        style=styles.NOTE,
        number_format=styles.NUMBER_0,
    )
    cfads = sw.formula_row(
        "debt.cfads",
        "CFADS",
        lambda t: wb.ref("ops.cfads", t),
        unit="$",
        style=styles.LINK,
        number_format=styles.MONEY,
        total=True,
    )
    scalar_target = model.scalar_target_dscr
    if scalar_target is not None:
        target = sw.formula_row(
            "debt.target_dscr",
            "Target DSCR",
            lambda t: "Target_DSCR",
            unit="x",
            style=styles.LINK,
            number_format=styles.RATIO,
        )
    else:
        profile = model.target_dscr_profile
        target = sw.values_row(
            "debt.target_dscr",
            "Target DSCR (time-varying profile)",
            [
                profile[t - 1] if t - 1 < len(profile) else profile[-1]
                for t in sw.periods()
            ],
            unit="x",
            style=styles.INPUT,
            number_format=styles.RATIO,
        )
    available = sw.formula_row(
        "debt.available_service",
        "Debt service available at the target DSCR",
        lambda t: (
            f"IF({L(period.row, t)}<=Debt_Periods,"
            f"{L(cfads.row, t)}/{L(target.row, t)},0)"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
        series_name="Available_Service_Series",
    )
    discount = sw.formula_row(
        "debt.discount_factor",
        "Discount factor to the end of the grace period",
        lambda t: (
            f"IF(AND({L(period.row, t)}>Grace_Periods,"
            f"{L(period.row, t)}<=Debt_Periods),"
            f"(1+Rate_Per_Period)^-({L(period.row, t)}-Grace_Periods),0)"
        ),
        unit="x",
        number_format="0.0000",
    )
    pv_available = sw.formula_row(
        "debt.pv_available",
        "PV of available service",
        lambda t: f"{L(available.row, t)}*{L(discount.row, t)}",
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    fp_factor = sw.formula_row(
        "debt.fixed_principal_factor",
        "Fixed-principal service factor",
        lambda t: (
            f"IF({L(period.row, t)}>Debt_Periods,0,"
            f"IF({L(period.row, t)}<=Grace_Periods,Rate_Per_Period,"
            f"1/Amortising_Periods+Rate_Per_Period*"
            f"(1-({L(period.row, t)}-Grace_Periods-1)/Amortising_Periods)))"
        ),
        unit="x",
        number_format="0.0000",
    )
    fp_implied = sw.formula_row(
        "debt.fixed_principal_implied_debt",
        "Debt implied by the fixed-principal test",
        lambda t: (
            f"IF(AND({L(period.row, t)}<=Debt_Periods,{L(fp_factor.row, t)}>0),"
            f"{L(available.row, t)}/{L(fp_factor.row, t)},{INFINITY_SENTINEL})"
        ),
        unit="$",
        number_format=styles.MONEY_OR_NO_LIMIT,
    )
    amortising_only = sw.formula_row(
        "debt.available_amortising_only",
        "Available service, amortising periods only",
        lambda t: (
            f"IF(AND({L(period.row, t)}>Grace_Periods,"
            f"{L(period.row, t)}<=Debt_Periods),"
            f"{L(available.row, t)},{INFINITY_SENTINEL})"
        ),
        unit="$",
        number_format=styles.MONEY_OR_NO_LIMIT,
    )
    grace_only = sw.formula_row(
        "debt.available_grace_only",
        "Available service, grace periods only",
        lambda t: (
            f"IF({L(period.row, t)}<=Grace_Periods,"
            f"{L(available.row, t)},{INFINITY_SENTINEL})"
        ),
        unit="$",
        number_format=styles.MONEY_OR_NO_LIMIT,
    )
    cfads_loan = sw.formula_row(
        "debt.cfads_loan_life",
        "CFADS within the loan life",
        lambda t: (
            f"IF({L(period.row, t)}<=Debt_Periods,{L(cfads.row, t)},0)"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    sw.skip()

    # ------------------------------------------------------------------
    # Debt quantum by test
    # ------------------------------------------------------------------
    sw.section("Debt quantum permitted by each credit test")
    sw.scalar(
        "PV of available service (sculpted)",
        f"=SUM({_range(sw, pv_available)})",
        unit="$",
        number_format=styles.MONEY,
        name="PV_Available_Service",
    )
    sw.scalar(
        "Interest-only coverage cap during grace",
        f"=IF(AND(Grace_Periods>0,Rate_Per_Period>0),"
        f"MIN({_range(sw, grace_only)})/Rate_Per_Period,{INFINITY_SENTINEL})",
        unit="$",
        number_format=styles.MONEY_OR_NO_LIMIT,
        name="Interest_Only_Cap",
        source="A grace period cannot support more debt than its own interest "
        "coverage allows.",
    )
    sw.scalar(
        "Debt - sculpted to the DSCR target",
        "=MIN(PV_Available_Service,Interest_Only_Cap)",
        unit="$",
        number_format=styles.MONEY,
        name="Debt_Sculpted",
    )
    sw.scalar(
        "Level payment supported",
        f"=MIN({_range(sw, amortising_only)})",
        unit="$",
        number_format=styles.MONEY,
        name="Level_Payment",
        source="A constant payment is set by the tightest period, so every "
        "other period's coverage goes unused.",
    )
    sw.scalar(
        "Debt - level payment",
        "=MIN(Level_Payment*Annuity_Factor,Interest_Only_Cap)",
        unit="$",
        number_format=styles.MONEY,
        name="Debt_Level",
    )
    sw.scalar(
        "Debt - fixed principal",
        f"=MIN({_range(sw, fp_implied)})",
        unit="$",
        number_format=styles.MONEY,
        name="Debt_Fixed_Principal",
    )
    sw.scalar(
        "Debt supported by the DSCR test (selected style)",
        "=CHOOSE(Amort_Style_Code,Debt_Sculpted,Debt_Level,Debt_Fixed_Principal)",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        name="Debt_DSCR_Test",
    )
    sw.scalar(
        "Debt permitted by the gearing cap",
        "=Max_Gearing*Total_Project_Cost",
        unit="$",
        number_format=styles.MONEY,
        name="Debt_Gearing_Test",
        source="Circular by construction: project cost includes IDC and fees, "
        "which depend on the debt. Excel resolves it iteratively.",
    )
    sw.scalar(
        "PV of CFADS to loan maturity",
        f"=NPV(Rate_Per_Period,{_range(sw, cfads_loan)})",
        unit="$",
        number_format=styles.MONEY,
        name="PV_CFADS_Loan_Life",
        source="Discounted at the debt rate - the denominator of LLCR is a "
        "balance that compounds at that rate.",
    )
    sw.scalar(
        "PV of CFADS to end of project life",
        f"=NPV(Rate_Per_Period,{_range(sw, cfads)})",
        unit="$",
        number_format=styles.MONEY,
        name="PV_CFADS_Project_Life",
    )
    sw.scalar(
        "Debt permitted by the LLCR floor",
        f"=IF(Min_LLCR>0,PV_CFADS_Loan_Life/Min_LLCR,{INFINITY_SENTINEL})",
        unit="$",
        number_format=styles.MONEY_OR_NO_LIMIT,
        name="Debt_LLCR_Test",
    )
    sw.scalar(
        "Debt permitted by the PLCR floor",
        f"=IF(Min_PLCR>0,PV_CFADS_Project_Life/Min_PLCR,{INFINITY_SENTINEL})",
        unit="$",
        number_format=styles.MONEY_OR_NO_LIMIT,
        name="Debt_PLCR_Test",
    )
    sw.scalar(
        "SENIOR DEBT SIZED",
        "=MIN(Debt_DSCR_Test,Debt_Gearing_Test,Debt_LLCR_Test,Debt_PLCR_Test)",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        name="Senior_Debt",
        label_style=styles.LABEL,
        source="The binding test is whichever of the four is smallest.",
    )
    sw.scalar(
        "Binding constraint",
        f"=IF(Senior_Debt>=Debt_DSCR_Test-{_BINDING_TOLERANCE},"
        f'IF(Debt_Periods<Tenor_Periods,"TAIL","DSCR"),'
        f"IF(Senior_Debt>=Debt_Gearing_Test-{_BINDING_TOLERANCE},"
        f'"GEARING",IF(Senior_Debt>=Debt_LLCR_Test-{_BINDING_TOLERANCE},'
        f'"LLCR","PLCR")))',
        style=styles.TOTAL,
        name="Binding_Constraint",
        source="Practitioners care which test binds, not only the number.",
    )
    sw.skip()

    # ------------------------------------------------------------------
    # Amortisation schedule
    # ------------------------------------------------------------------
    sw.section("Contractual amortisation schedule")
    opening = sw.formula_row(
        "debt.opening_balance",
        "Opening balance",
        lambda t: (
            "Senior_Debt"
            if t == sw.start_period
            else f"{L(sw.row + 4, t - 1)}"  # previous period's closing balance
        ),
        unit="$",
        number_format=styles.MONEY,
        series_name="Debt_Opening_Balance_Series",
    )
    interest = sw.formula_row(
        "debt.interest",
        "Interest",
        lambda t: (
            f"IF({L(period.row, t)}<=Debt_Periods,"
            f"{L(opening.row, t)}*Rate_Per_Period,0)"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
        series_name="Senior_Interest_Series",
    )
    service = sw.formula_row(
        "debt.debt_service",
        "Debt service",
        lambda t: _service_formula(sw, L, period.row, available.row, fp_factor.row, t),
        unit="$",
        number_format=styles.MONEY,
        total=True,
        series_name="Senior_Debt_Service_Series",
    )
    principal = sw.formula_row(
        "debt.principal",
        "Scheduled principal",
        lambda t: (
            f"MIN(MAX({L(service.row, t)}-{L(interest.row, t)},0),"
            f"{L(opening.row, t)})"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
        series_name="Senior_Principal_Series",
    )
    closing = sw.formula_row(
        "debt.closing_balance",
        "Closing balance",
        lambda t: f"{L(opening.row, t)}-{L(principal.row, t)}",
        unit="$",
        number_format=styles.MONEY,
        series_name="Debt_Closing_Balance_Series",
    )
    assert closing.row == opening.row + 4, "opening-balance back-link mis-wired"

    dscr = sw.formula_row(
        "debt.dscr",
        "DSCR achieved",
        lambda t: (
            f'IF({L(service.row, t)}>0,{L(cfads.row, t)}/{L(service.row, t)},"")'
        ),
        unit="x",
        style=styles.TOTAL,
        number_format=styles.RATIO,
        series_name="DSCR_Series",
    )
    dsra_target = sw.formula_row(
        "debt.dsra_target",
        "DSRA target balance (end of period)",
        lambda t: _dsra_formula(sw, L, service.row, t, model.dsra_lookahead),
        unit="$",
        number_format=styles.MONEY,
        series_name="DSRA_Target_Series",
    )
    sw.formula_row(
        "debt.llcr_series",
        "LLCR (forward, at each period end)",
        lambda t: _coverage_series(sw, L, closing.row, cfads_loan.row, t),
        unit="x",
        number_format=styles.RATIO,
    )
    sw.formula_row(
        "debt.plcr_series",
        "PLCR (forward, at each period end)",
        lambda t: _coverage_series(sw, L, closing.row, cfads.row, t),
        unit="x",
        number_format=styles.RATIO,
    )
    sw.skip()

    # ------------------------------------------------------------------
    # Coverage summary
    # ------------------------------------------------------------------
    sw.section("Coverage and reserve summary")
    sw.scalar(
        "Minimum DSCR",
        f"=MIN({_range(sw, dscr)})",
        unit="x",
        style=styles.TOTAL,
        number_format=styles.RATIO,
        name="Min_DSCR_Achieved",
    )
    sw.scalar(
        "LLCR at COD",
        "=PV_CFADS_Loan_Life/Senior_Debt",
        unit="x",
        number_format=styles.RATIO,
        name="LLCR_At_COD",
    )
    sw.scalar(
        "PLCR at COD",
        "=PV_CFADS_Project_Life/Senior_Debt",
        unit="x",
        number_format=styles.RATIO,
        name="PLCR_At_COD",
    )
    sw.scalar(
        "Weighted average life",
        f"=SUMPRODUCT({_range(sw, period)},{_range(sw, principal)})"
        f"/SUM({_range(sw, principal)})/Periods_Per_Year",
        unit="years",
        number_format=styles.YEARS,
        name="Debt_WAL_Years",
        source="Lenders price and risk-weight off WAL, not final maturity.",
    )
    sw.scalar(
        "DSRA required at COD",
        _dsra_at_cod(sw, service.row, model.dsra_lookahead),
        unit="$",
        number_format=styles.MONEY,
        name="DSRA_Initial",
        source="Forward-looking cover for the service about to fall due. One "
        "of the uses that makes construction funding circular.",
    )
    sw.scalar(
        "Check: closing balance at final maturity",
        f"={L(closing.row, sw.last_period)}",
        unit="$",
        style=styles.CHECK,
        number_format=styles.NUMBER_2,
        name="Final_Balance_Check",
        source="The PV identity forces the facility to amortise to zero. This "
        "cell is the proof.",
    )
    assert dsra_target.row > 0
    sw.freeze("D6")


# ---------------------------------------------------------------------------
# Formula helpers
# ---------------------------------------------------------------------------


def _range(sw, ref) -> str:
    """Same-sheet absolute range across every period column of ``ref``."""
    first = sw.local(ref.row, sw.start_period, absolute=True)
    last = sw.local(ref.row, sw.last_period, absolute=True)
    return f"{first}:{last}"


def _service_formula(sw, L, period_row: int, available_row: int, fp_row: int, t: int) -> str:
    """Debt service for one period, for whichever amortisation style is selected.

    Every branch is homogeneous of degree one in the debt quantum, which is why
    a single ``Senior_Debt`` multiplier rescales the whole profile exactly when
    a gearing, LLCR or PLCR cap cuts the facility below its DSCR maximum. The
    resulting DSCR then lands *above* target - the deal is over-covered, which
    is what a gearing-constrained deal looks like in practice.
    """
    p = L(period_row, t)
    return (
        f"IF({p}>Debt_Periods,0,"
        f"IF({p}<=Grace_Periods,Rate_Per_Period*Senior_Debt,"
        f"CHOOSE(Amort_Style_Code,"
        f"{L(available_row, t)}*Senior_Debt/PV_Available_Service,"
        f"Senior_Debt/Annuity_Factor,"
        f"Senior_Debt*{L(fp_row, t)})))"
    )


def _dsra_formula(sw, L, service_row: int, t: int, lookahead: int) -> str:
    """Forward-looking DSRA target at the end of period ``t``.

    The reserve holds ``DSRA_Months`` of the service *about to fall due*, so it
    sums forward from period ``t+1``, taking each future period pro rata until
    the cover is exhausted. ``lookahead`` is sized from the engine's inputs so
    the emitted formula has exactly as many terms as the cover needs.
    """
    terms = []
    for j in range(1, lookahead + 1):
        if not sw.periods().stop > t + j:
            break
        weight = f"MIN(1,MAX(0,DSRA_Periods-{j - 1}))"
        terms.append(f"{weight}*{L(service_row, t + j)}")
    return "+".join(terms) if terms else "0"


def _dsra_at_cod(sw, service_row: int, lookahead: int) -> str:
    """The DSRA that must be funded at financial close (period 0)."""
    terms = []
    for j in range(1, lookahead + 1):
        period = sw.start_period + j - 1
        if period > sw.last_period:
            break
        weight = f"MIN(1,MAX(0,DSRA_Periods-{j - 1}))"
        terms.append(f"{weight}*{sw.local(service_row, period, absolute=True)}")
    return "=" + ("+".join(terms) if terms else "0")


def _coverage_series(sw, L, closing_row: int, cfads_row: int, t: int) -> str:
    """LLCR / PLCR measured at the end of period ``t``.

    PV of the CFADS still ahead of the loan, discounted at the debt rate,
    over the balance outstanding. ``NPV`` discounts its first argument by one
    period, which is exactly the convention the engine uses.
    """
    if t >= sw.last_period:
        return '""'
    forward = (
        f"{sw.local(cfads_row, t + 1, absolute=True)}:"
        f"{sw.local(cfads_row, sw.last_period, absolute=True)}"
    )
    # A $1 materiality floor: a coverage ratio measured against a balance of a
    # few cents of floating-point residue is noise, not information.
    return (
        f"IF({L(closing_row, t)}>1,"
        f"NPV(Rate_Per_Period,{forward})/{L(closing_row, t)},\"\")"
    )
