"""The cash waterfall - the order in which a project's cash is allowed to move.

Priority of payments, senior to junior. This is the order written into a
non-recourse credit agreement, and the whole point of the structure: cash
cannot skip a step.

1. **Revenue less operating expense less cash tax** - i.e. CFADS, produced by
   ``engine.cashflow``. Everything below is a financing item.
2. **Senior interest**, then **senior scheduled principal**. Interest is always
   paid before principal; a project that pays principal ahead of interest has
   already defaulted.
3. **Debt Service Reserve Account.** Drawn *up* the waterfall to cure a debt
   service shortfall, and topped back up here, below debt service and above
   everything junior. Excess over target is released and becomes distributable.
4. **Maintenance Reserve Account.** Exogenous in Phase 1 (see PHASE1.md): the
   caller supplies the deposit and release schedule from a maintenance plan.
5. **Cash sweep.** A contractual percentage of the remaining surplus prepays
   senior debt. Prepayments are applied in **inverse order of maturity** -
   they retire the back end of the schedule first - which is the market
   standard because it shortens the loan without changing near-term service.
6. **Distribution lock-up test.** If DSCR falls below the lock-up level, the
   remaining cash may not leave the project. Modelled here as a 100% sweep in
   that period (declared as a simplification in PHASE1.md; a real agreement
   traps the cash in a blocked account first and releases it after a cure
   period).
7. **Distributions to equity** - the residual, and the only line the sponsor
   actually owns.

Subordinated / back-leverage debt sits between (6) and (7). Phase 1 exposes the
hook (``subordinated_service``) but does not size a sub-debt tranche; that is
Phase 3, where back-leverage matters for the structure comparison.

**Cash conservation is an asserted invariant.** For every period::

    CFADS + DSRA release + MRA release
        == interest + scheduled principal + sweep prepayment
           + DSRA deposit + MRA deposit + subordinated service + distributions

``assert_cash_conservation`` checks it to ``CASH_TOLERANCE``. It is cheap and
it catches almost every wiring mistake a waterfall can have.
"""

from __future__ import annotations

from engine.defaults import CASH_TOLERANCE
from engine.models import DebtResult, WaterfallResult

__all__ = ["run_waterfall", "assert_cash_conservation"]


def run_waterfall(
    cfads: tuple[float, ...],
    debt: DebtResult,
    *,
    dsra_target: tuple[float, ...] | None = None,
    dsra_initial: float | None = None,
    cash_sweep_pct: float = 0.0,
    lockup_dscr: float | None = None,
    covenant_dscr: float | None = None,
    mra_deposits: tuple[float, ...] | None = None,
    mra_releases: tuple[float, ...] | None = None,
    subordinated_service: tuple[float, ...] | None = None,
) -> WaterfallResult:
    """Run the waterfall over the full project life.

    Parameters
    ----------
    cfads:
        CFADS for the whole project life. May be longer than the debt tenor;
        periods after maturity carry no debt service and everything is
        distributable.
    debt:
        The sized schedule. Its ``principal`` series is the *scheduled*
        amortisation; actual principal may exceed it if a sweep prepays, and
        the schedule is shortened from the back when it does.
    dsra_target:
        Required DSRA balance at COD (index 0) and at the end of each debt
        period. Produced by ``engine.debt.dsra_targets``.
    dsra_initial:
        DSRA balance standing at COD. Defaults to ``dsra_target[0]``, which is
        the amount funded at financial close.
    cash_sweep_pct:
        Fraction of post-reserve surplus applied to prepay senior debt.
    lockup_dscr:
        DSCR below which distributions are blocked.
    covenant_dscr:
        DSCR covenant level, reported as a breach flag. Reporting only - the
        engine does not model acceleration.

    Returns
    -------
    WaterfallResult
        Every line, period by period.
    """
    n = len(cfads)
    n_debt = debt.n_periods
    rate = debt.rate_per_period

    if dsra_target is None:
        dsra_target = tuple(0.0 for _ in range(n_debt + 1))
    dsra_balance = dsra_target[0] if dsra_initial is None else dsra_initial

    mra_in = mra_deposits or tuple(0.0 for _ in range(n))
    mra_out = mra_releases or tuple(0.0 for _ in range(n))
    sub_service = subordinated_service or tuple(0.0 for _ in range(n))

    #: Remaining scheduled principal, consumed front to back and written down
    #: from the back when a prepayment lands.
    remaining_principal = list(debt.principal)

    balance = debt.debt_size
    mra_balance = 0.0

    out: dict[str, list] = {
        key: []
        for key in (
            "interest", "principal", "sweep", "debt_service", "opening", "closing",
            "dsra_open", "dsra_dep", "dsra_rel", "dsra_close", "dsra_tgt",
            "mra_dep", "mra_rel", "mra_close", "cafd", "sub", "dist", "dscr",
            "shortfall", "breach", "lockup",
        )
    }

    for t in range(n):
        cash = cfads[t]
        opening_balance = balance
        dsra_opening = dsra_balance

        # --- 2. senior debt service ----------------------------------------
        # Interest keeps accruing on any balance still outstanding after the
        # scheduled maturity (only reachable after a payment shortfall), and
        # the whole residual balance is due.
        interest_due = opening_balance * rate if opening_balance > 0 else 0.0
        principal_due = (
            remaining_principal[t] if t < n_debt else opening_balance
        )
        principal_due = max(min(principal_due, opening_balance), 0.0)
        service_due = interest_due + principal_due

        paid_from_cash = min(cash, service_due)
        cash -= paid_from_cash
        shortfall = service_due - paid_from_cash

        # DSRA is drawn up the waterfall to cure a shortfall.
        dsra_draw = min(dsra_balance, shortfall)
        dsra_balance -= dsra_draw
        shortfall -= dsra_draw

        interest_paid = min(interest_due, paid_from_cash + dsra_draw)
        principal_paid = paid_from_cash + dsra_draw - interest_paid
        balance -= principal_paid
        if t < n_debt:
            remaining_principal[t] -= principal_paid

        # --- 3. DSRA top-up / release --------------------------------------
        target = dsra_target[t + 1] if t + 1 < len(dsra_target) else 0.0
        if t >= n_debt:
            target = 0.0
        dsra_release_excess = max(dsra_balance - target, 0.0)
        dsra_balance -= dsra_release_excess
        cash += dsra_release_excess

        dsra_deposit = min(max(target - dsra_balance, 0.0), max(cash, 0.0))
        dsra_balance += dsra_deposit
        cash -= dsra_deposit

        # --- 4. maintenance reserve ----------------------------------------
        mra_release = min(mra_out[t], mra_balance)
        mra_balance -= mra_release
        cash += mra_release
        mra_deposit = min(mra_in[t], max(cash, 0.0))
        mra_balance += mra_deposit
        cash -= mra_deposit

        # --- coverage -------------------------------------------------------
        dscr = (cfads[t] / service_due) if service_due > 0 else float("inf")
        locked = lockup_dscr is not None and dscr < lockup_dscr
        breach = covenant_dscr is not None and service_due > 0 and dscr < covenant_dscr

        # --- 5/6. cash sweep and lock-up ------------------------------------
        cafd = max(cash, 0.0)
        sweep_rate = 1.0 if locked else cash_sweep_pct
        sweep = min(cafd * sweep_rate, balance)
        balance -= sweep
        cash -= sweep
        if sweep > 0:
            _apply_prepayment_inverse_order(remaining_principal, sweep, t)

        # --- subordinated debt, then equity ---------------------------------
        sub = min(sub_service[t], max(cash, 0.0))
        cash -= sub
        distributions = max(cash, 0.0)

        out["opening"].append(opening_balance)
        out["interest"].append(interest_paid)
        out["principal"].append(principal_paid)
        out["sweep"].append(sweep)
        out["debt_service"].append(interest_paid + principal_paid + sweep)
        out["closing"].append(balance)
        out["dsra_open"].append(dsra_opening)
        out["dsra_tgt"].append(target)
        out["dsra_dep"].append(dsra_deposit)
        out["dsra_rel"].append(dsra_draw + dsra_release_excess)
        out["dsra_close"].append(dsra_balance)
        out["mra_dep"].append(mra_deposit)
        out["mra_rel"].append(mra_release)
        out["mra_close"].append(mra_balance)
        out["cafd"].append(cafd)
        out["sub"].append(sub)
        out["dist"].append(distributions)
        out["dscr"].append(dscr)
        out["shortfall"].append(shortfall)
        out["breach"].append(bool(breach))
        out["lockup"].append(bool(locked))

    result = WaterfallResult(
        period_index=tuple(range(1, n + 1)),
        cfads=tuple(cfads),
        interest=tuple(out["interest"]),
        principal_scheduled=tuple(out["principal"]),
        sweep_prepayment=tuple(out["sweep"]),
        debt_service=tuple(out["debt_service"]),
        opening_balance=tuple(out["opening"]),
        closing_balance=tuple(out["closing"]),
        dsra_opening=tuple(out["dsra_open"]),
        dsra_target=tuple(out["dsra_tgt"]),
        dsra_deposit=tuple(out["dsra_dep"]),
        dsra_release=tuple(out["dsra_rel"]),
        dsra_closing=tuple(out["dsra_close"]),
        mra_deposit=tuple(out["mra_dep"]),
        mra_release=tuple(out["mra_rel"]),
        mra_closing=tuple(out["mra_close"]),
        cash_available_for_distribution=tuple(out["cafd"]),
        subordinated_service=tuple(out["sub"]),
        distributions=tuple(out["dist"]),
        dscr=tuple(out["dscr"]),
        debt_service_shortfall=tuple(out["shortfall"]),
        covenant_breach=tuple(out["breach"]),
        lockup=tuple(out["lockup"]),
    )
    assert_cash_conservation(result)
    return result


def _apply_prepayment_inverse_order(
    remaining: list[float], amount: float, current_index: int
) -> None:
    """Retire scheduled principal from the back of the schedule forward.

    Inverse-order-of-maturity application is the market standard for cash
    sweeps: it shortens the loan without cutting near-term amortisation, so the
    near-term DSCR profile the deal was sculpted to is preserved.
    """
    left = amount
    for i in range(len(remaining) - 1, current_index, -1):
        if left <= 0:
            break
        take = min(remaining[i], left)
        remaining[i] -= take
        left -= take


def assert_cash_conservation(
    result: WaterfallResult, tolerance: float = CASH_TOLERANCE
) -> None:
    """Assert sources equal uses in every period.

    A waterfall that does not conserve cash is not a waterfall; it is a
    spreadsheet with a plug. This is the single most valuable assertion in the
    engine.
    """
    for i in range(result.n_periods):
        sources = result.sources(i)
        uses = result.uses(i)
        if abs(sources - uses) > max(tolerance, abs(sources) * 1e-9):
            raise AssertionError(
                f"cash not conserved in period {i + 1}: sources {sources:,.6f} "
                f"!= uses {uses:,.6f} (difference {sources - uses:,.6e})"
            )
