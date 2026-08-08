"""Waterfall - the order in which the project's cash is allowed to move.

Priority of payments, senior to junior, exactly as a non-recourse credit
agreement writes it. Cash cannot skip a step.

1. **CFADS** - revenue less operating cost less cash tax, from Operations.
2. **Senior interest, then senior scheduled principal.** Interest is always paid
   first; a project paying principal ahead of interest has already defaulted.
3. **DSRA.** Drawn *up* the waterfall to cure a debt service shortfall, and
   topped back up here - below debt service, above everything junior. Any
   balance over target is released and becomes distributable.
4. **MRA.** Exogenous: the deposit and release schedule comes from a
   maintenance plan, so both rows are blue inputs.
5. **Cash sweep.** A contractual share of the surplus prepays senior debt, in
   **inverse order of maturity** - it retires the back of the schedule first,
   shortening the loan without disturbing the near-term profile the deal was
   sculpted to.
6. **Distribution lock-up.** Below the lock-up DSCR, 100% of the surplus is
   trapped (modelled as a full sweep - see Notes for the simplification).
7. **Distributions to equity** - the residual, and the only line the sponsor
   owns.

The inverse-order sweep is the one mechanic that is genuinely awkward in a
formula grid, and it is handled without a helper matrix: the principal still
scheduled in period *t* is the original schedule from *t* to maturity, less
every sweep already applied, capped at this period's own instalment. That is
algebraically identical to retiring instalments from the back.

Cash conservation is asserted on the sheet, not merely assumed: the check row
must read zero in every period.
"""

from __future__ import annotations

from export import styles
from export.model import ModelBundle
from export.workbook import WorkbookBuilder

__all__ = ["SHEET_NAME", "build"]

SHEET_NAME = "Waterfall"

#: Rows between "sweeps applied to date" and the "cash sweep prepayment" row it
#: reads. The waterfall has no data-dependent rows, so this offset is a
#: constant - and it is asserted at the end of :func:`build`, so a future edit
#: that shifts a row fails loudly instead of silently mis-wiring the sweep.
_SWEEP_ROW_OFFSET = 32

#: Rows between the senior "opening balance" row and the "closing balance" row
#: it carries forward from. Asserted below, for the same reason.
_BALANCE_ROW_OFFSET = 37


def build(wb: WorkbookBuilder, model: ModelBundle) -> None:
    """Write the Waterfall sheet."""
    n = model.n_periods
    sw = wb.create_sheet(SHEET_NAME, n_periods=n)
    sw.hide_gridlines()
    sw.set_widths()
    sw.title_block(
        "Cash waterfall",
        "CFADS -> senior interest -> senior principal -> DSRA -> MRA -> "
        "cash sweep -> subordinated -> distributions. Every line is a formula.",
    )
    sw.period_header()
    L = sw.local

    period = sw.values_row(
        "wf.period",
        "Period",
        list(sw.periods()),
        unit="#",
        style=styles.NOTE,
        number_format=styles.NUMBER_0,
    )
    cfads = sw.formula_row(
        "wf.cfads",
        "CFADS",
        lambda t: wb.ref("ops.cfads", t),
        unit="$",
        style=styles.LINK,
        number_format=styles.MONEY,
        total=True,
    )
    sw.skip()

    # ------------------------------------------------------------------
    # Senior debt service
    # ------------------------------------------------------------------
    sw.section("1-2. Senior debt service")
    opening = sw.formula_row(
        "wf.opening_balance",
        "Senior debt - opening balance",
        lambda t: (
            "Senior_Debt"
            if t == sw.start_period
            else f"{L(sw.row + _BALANCE_ROW_OFFSET, t - 1)}"
        ),
        unit="$",
        number_format=styles.MONEY,
    )
    interest_due = sw.formula_row(
        "wf.interest_due",
        "Senior interest due",
        lambda t: f"{L(opening.row, t)}*Rate_Per_Period",
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    contractual = sw.formula_row(
        "wf.principal_contractual",
        "Contractual principal instalment",
        lambda t: wb.ref("debt.principal", t),
        unit="$",
        style=styles.LINK,
        number_format=styles.MONEY,
    )
    remaining = sw.formula_row(
        "wf.principal_remaining",
        "Contractual principal still to run",
        lambda t: f"SUM({wb.span('debt.principal', t, sw.last_period)})",
        unit="$",
        number_format=styles.MONEY,
    )
    sweeps_to_date = sw.formula_row(
        "wf.sweeps_to_date",
        "Sweeps applied to date",
        lambda t: (
            "0"
            if t == sw.start_period
            else "SUM("
            + f"{L(sw.row + _SWEEP_ROW_OFFSET, sw.start_period, absolute=True)}:"
            + f"{L(sw.row + _SWEEP_ROW_OFFSET, t - 1, absolute=True)})"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=False,
    )
    principal_due = sw.formula_row(
        "wf.principal_due",
        "Senior principal due",
        # Inside the tenor: this period's instalment, less anything a sweep has
        # already retired from the back of the schedule, capped at the balance.
        # Past final maturity the whole residual balance falls due - which is
        # what a credit agreement says, and what keeps the balance (and so the
        # interest and DSCR rows) at exactly zero afterwards.
        lambda t: (
            f"IF({L(period.row, t)}>Debt_Periods,{L(opening.row, t)},"
            f"MAX(0,MIN({L(contractual.row, t)},"
            f"{L(remaining.row, t)}-{L(sweeps_to_date.row, t)},"
            f"{L(opening.row, t)})))"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    service_due = sw.formula_row(
        "wf.debt_service_due",
        "Senior debt service due",
        lambda t: f"{L(interest_due.row, t)}+{L(principal_due.row, t)}",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        total=True,
    )
    paid_from_cfads = sw.formula_row(
        "wf.paid_from_cfads",
        "Paid from CFADS",
        lambda t: f"MIN({L(cfads.row, t)},{L(service_due.row, t)})",
        unit="$",
        number_format=styles.MONEY,
    )
    shortfall_pre = sw.formula_row(
        "wf.shortfall_before_dsra",
        "Shortfall before DSRA",
        lambda t: f"{L(service_due.row, t)}-{L(paid_from_cfads.row, t)}",
        unit="$",
        number_format=styles.MONEY,
    )
    sw.skip()

    # ------------------------------------------------------------------
    # DSRA
    # ------------------------------------------------------------------
    sw.section("3. Debt service reserve account")
    dsra_opening = sw.formula_row(
        "wf.dsra_opening",
        "DSRA - opening balance",
        lambda t: (
            "DSRA_Initial" if t == sw.start_period else f"{L(sw.row + 5, t - 1)}"
        ),
        unit="$",
        number_format=styles.MONEY,
    )
    dsra_draw = sw.formula_row(
        "wf.dsra_draw",
        "DSRA drawn to cure a shortfall",
        lambda t: f"MIN({L(dsra_opening.row, t)},{L(shortfall_pre.row, t)})",
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    dsra_target = sw.formula_row(
        "wf.dsra_target",
        "DSRA target balance",
        lambda t: wb.ref("debt.dsra_target", t),
        unit="$",
        style=styles.LINK,
        number_format=styles.MONEY,
    )
    dsra_release = sw.formula_row(
        "wf.dsra_release_excess",
        "DSRA released above target",
        lambda t: (
            f"MAX({L(dsra_opening.row, t)}-{L(dsra_draw.row, t)}"
            f"-{L(dsra_target.row, t)},0)"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    dsra_deposit = sw.formula_row(
        "wf.dsra_deposit",
        "DSRA topped up",
        lambda t: (
            f"MIN(MAX({L(dsra_target.row, t)}-({L(dsra_opening.row, t)}"
            f"-{L(dsra_draw.row, t)}-{L(dsra_release.row, t)}),0),"
            f"MAX({L(cfads.row, t)}-{L(paid_from_cfads.row, t)}"
            f"+{L(dsra_release.row, t)},0))"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    dsra_closing = sw.formula_row(
        "wf.dsra_closing",
        "DSRA - closing balance",
        lambda t: (
            f"{L(dsra_opening.row, t)}-{L(dsra_draw.row, t)}"
            f"-{L(dsra_release.row, t)}+{L(dsra_deposit.row, t)}"
        ),
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        series_name="DSRA_Closing_Series",
    )
    assert dsra_closing.row == dsra_opening.row + 5, "DSRA back-link mis-wired"
    interest_paid = sw.formula_row(
        "wf.interest_paid",
        "Senior interest paid",
        lambda t: (
            f"MIN({L(interest_due.row, t)},{L(paid_from_cfads.row, t)}"
            f"+{L(dsra_draw.row, t)})"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    principal_paid = sw.formula_row(
        "wf.principal_paid",
        "Senior principal paid",
        lambda t: (
            f"{L(paid_from_cfads.row, t)}+{L(dsra_draw.row, t)}"
            f"-{L(interest_paid.row, t)}"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    cash_after_dsra = sw.formula_row(
        "wf.cash_after_dsra",
        "Cash after debt service and DSRA",
        lambda t: (
            f"{L(cfads.row, t)}-{L(paid_from_cfads.row, t)}"
            f"+{L(dsra_release.row, t)}-{L(dsra_deposit.row, t)}"
        ),
        unit="$",
        number_format=styles.MONEY,
    )
    sw.skip()

    # ------------------------------------------------------------------
    # MRA
    # ------------------------------------------------------------------
    sw.section("4. Maintenance reserve account (exogenous - blue inputs)")
    mra_dep_in = sw.values_row(
        "wf.mra_deposit_input",
        "MRA deposit scheduled",
        [0.0] * n,
        unit="$",
        style=styles.INPUT,
        number_format=styles.MONEY,
        total=True,
    )
    mra_rel_in = sw.values_row(
        "wf.mra_release_input",
        "MRA release scheduled",
        [0.0] * n,
        unit="$",
        style=styles.INPUT,
        number_format=styles.MONEY,
        total=True,
    )
    mra_opening = sw.formula_row(
        "wf.mra_opening",
        "MRA - opening balance",
        lambda t: "0" if t == sw.start_period else f"{L(sw.row + 3, t - 1)}",
        unit="$",
        number_format=styles.MONEY,
    )
    mra_release = sw.formula_row(
        "wf.mra_release",
        "MRA released",
        lambda t: f"MIN({L(mra_rel_in.row, t)},{L(mra_opening.row, t)})",
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    mra_deposit = sw.formula_row(
        "wf.mra_deposit",
        "MRA deposited",
        lambda t: (
            f"MIN({L(mra_dep_in.row, t)},MAX({L(cash_after_dsra.row, t)}"
            f"+{L(mra_release.row, t)},0))"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    mra_closing = sw.formula_row(
        "wf.mra_closing",
        "MRA - closing balance",
        lambda t: (
            f"{L(mra_opening.row, t)}+{L(mra_deposit.row, t)}"
            f"-{L(mra_release.row, t)}"
        ),
        unit="$",
        number_format=styles.MONEY,
    )
    assert mra_closing.row == mra_opening.row + 3, "MRA back-link mis-wired"
    cash_after_mra = sw.formula_row(
        "wf.cash_after_mra",
        "Cash after reserves",
        lambda t: (
            f"{L(cash_after_dsra.row, t)}+{L(mra_release.row, t)}"
            f"-{L(mra_deposit.row, t)}"
        ),
        unit="$",
        number_format=styles.MONEY,
    )
    sw.skip()

    # ------------------------------------------------------------------
    # Coverage, sweep and lock-up
    # ------------------------------------------------------------------
    sw.section("5-6. Coverage, cash sweep and distribution lock-up")
    dscr = sw.formula_row(
        "wf.dscr",
        "DSCR achieved",
        # $1 materiality floor: once the facility has matured the balance is
        # zero and there is no ratio to report. Without the floor a residual
        # cent of debt service would print a meaningless ratio.
        lambda t: (
            f'IF({L(service_due.row, t)}>1,'
            f'{L(cfads.row, t)}/{L(service_due.row, t)},"")'
        ),
        unit="x",
        style=styles.TOTAL,
        number_format=styles.RATIO,
        series_name="Waterfall_DSCR_Series",
    )
    sw.formula_row(
        "wf.covenant_breach",
        "DSCR covenant breach",
        lambda t: (
            f"IF({L(service_due.row, t)}>1,"
            f"IF(AND(Covenant_DSCR>0,"
            f"{L(cfads.row, t)}/{L(service_due.row, t)}<Covenant_DSCR),1,0),0)"
        ),
        unit="1 = yes",
        number_format=styles.NUMBER_0,
    )
    lockup = sw.formula_row(
        "wf.lockup",
        "Distribution lock-up",
        lambda t: (
            f"IF({L(service_due.row, t)}>1,"
            f"IF(AND(Lockup_DSCR>0,"
            f"{L(cfads.row, t)}/{L(service_due.row, t)}<Lockup_DSCR),1,0),0)"
        ),
        unit="1 = yes",
        number_format=styles.NUMBER_0,
    )
    cafd = sw.formula_row(
        "wf.cafd",
        "Cash available for distribution (pre-sweep)",
        lambda t: f"MAX({L(cash_after_mra.row, t)},0)",
        unit="$",
        number_format=styles.MONEY,
    )
    sweep_rate = sw.formula_row(
        "wf.sweep_rate",
        "Sweep percentage applied",
        lambda t: f"IF({L(lockup.row, t)}=1,1,Cash_Sweep_Pct)",
        unit="%",
        number_format=styles.PERCENT_1,
    )
    sweep = sw.formula_row(
        "wf.sweep",
        "Cash sweep prepayment",
        lambda t: (
            f"MIN({L(cafd.row, t)}*{L(sweep_rate.row, t)},"
            f"{L(opening.row, t)}-{L(principal_paid.row, t)})"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    assert sweep.row == sweeps_to_date.row + _SWEEP_ROW_OFFSET, (
        "the inverse-order sweep link is mis-wired: set _SWEEP_ROW_OFFSET to "
        f"{sweep.row - sweeps_to_date.row}"
    )
    closing = sw.formula_row(
        "wf.closing_balance",
        "Senior debt - closing balance",
        lambda t: (
            f"{L(opening.row, t)}-{L(principal_paid.row, t)}-{L(sweep.row, t)}"
        ),
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        series_name="Waterfall_Closing_Balance_Series",
    )
    assert closing.row == opening.row + _BALANCE_ROW_OFFSET, (
        "the senior balance back-link is mis-wired: set _BALANCE_ROW_OFFSET to "
        f"{closing.row - opening.row}"
    )
    cash_after_sweep = sw.formula_row(
        "wf.cash_after_sweep",
        "Cash after sweep",
        lambda t: f"{L(cash_after_mra.row, t)}-{L(sweep.row, t)}",
        unit="$",
        number_format=styles.MONEY,
    )
    sw.skip()

    # ------------------------------------------------------------------
    # Junior and equity
    # ------------------------------------------------------------------
    sw.section("7. Subordinated debt and distributions")
    sub_in = sw.values_row(
        "wf.sub_service_input",
        "Subordinated debt service scheduled",
        [0.0] * n,
        unit="$",
        style=styles.INPUT,
        number_format=styles.MONEY,
        total=True,
    )
    sub_paid = sw.formula_row(
        "wf.sub_service",
        "Subordinated debt service paid",
        lambda t: (
            f"MIN({L(sub_in.row, t)},MAX({L(cash_after_sweep.row, t)},0))"
        ),
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    distributions = sw.formula_row(
        "wf.distributions",
        "Distributions to equity",
        lambda t: f"MAX({L(cash_after_sweep.row, t)}-{L(sub_paid.row, t)},0)",
        unit="$",
        style=styles.TOTAL,
        number_format=styles.MONEY,
        total=True,
        series_name="Distributions_Series",
    )
    shortfall_post = sw.formula_row(
        "wf.debt_service_shortfall",
        "Senior debt service shortfall",
        lambda t: f"{L(shortfall_pre.row, t)}-{L(dsra_draw.row, t)}",
        unit="$",
        number_format=styles.MONEY,
        total=True,
    )
    sw.skip()

    sw.section("Check")
    sw.formula_row(
        "wf.cash_check",
        "Sources less uses (must be zero)",
        lambda t: (
            f"({L(cfads.row, t)}+{L(dsra_draw.row, t)}+{L(dsra_release.row, t)}"
            f"+{L(mra_release.row, t)})"
            f"-({L(interest_paid.row, t)}+{L(principal_paid.row, t)}"
            f"+{L(sweep.row, t)}+{L(dsra_deposit.row, t)}"
            f"+{L(mra_deposit.row, t)}+{L(sub_paid.row, t)}"
            f"+{L(distributions.row, t)})"
        ),
        unit="$",
        style=styles.CHECK,
        number_format=styles.NUMBER_2,
        series_name="Cash_Check_Series",
    )
    sw.skip()
    sw.scalar(
        "Total senior debt service shortfall",
        f"=SUM({_range(sw, shortfall_post)})",
        unit="$",
        style=styles.CHECK,
        number_format=styles.MONEY,
        name="Total_DS_Shortfall",
        source="Non-zero means the deal did not meet its debt service in some "
        "period even after drawing the DSRA.",
    )
    sw.scalar(
        "Minimum DSCR (post-waterfall)",
        f"=MIN({_range(sw, dscr)})",
        unit="x",
        number_format=styles.RATIO,
        name="Min_DSCR_Waterfall",
    )
    assert period.row > 0 and mra_dep_in.row > 0
    sw.freeze("D6")


def _range(sw, ref) -> str:
    first = sw.local(ref.row, sw.start_period, absolute=True)
    last = sw.local(ref.row, sw.last_period, absolute=True)
    return f"{first}:{last}"
