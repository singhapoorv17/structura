"""Debt sizing, sculpting and the credit tests - the core of the engine.

THE SCULPTING MATH
------------------
Let ``C_t`` be CFADS in period *t*, ``d_t`` the target DSCR in period *t*, and
``r`` the per-period interest rate. Sculpting means: choose the debt service
``DS_t`` so the deal covers exactly the target in every period, then let the
debt quantum fall out of it.

1. Available debt service, period by period::

       DS_t = C_t / d_t                              (t = g+1 .. N)

2. Debt quantum is the present value of that service at the debt rate::

       D = SUM_{t=g+1..N}  DS_t / (1 + r)^(t - g)

3. Split each period's service into interest and principal off the actual
   balance::

       I_t = r * B_{t-1},   P_t = DS_t - I_t,   B_t = B_{t-1} - P_t,  B_0 = D

Step 2 guarantees step 3 amortises to exactly zero at maturity. Proof: the
balance recursion is ``B_t = B_{t-1}(1+r) - DS_t``, so

    B_N = D(1+r)^N - SUM_t DS_t (1+r)^(N-t) = 0

precisely when ``D`` is the PV in step 2. That identity - **debt size is the PV
of the sculpted service at the debt rate** - is the whole trick, and it is why
sculpting needs no iteration at all once CFADS is known. (The circularity in a
project-finance model is not in the sculpt; it is in the *funding*: IDC, fees
and the DSRA. That is solved separately in ``engine.circularity``.)

``g`` is the grace period in whole periods. During grace, principal is deferred
and only interest is paid, so ``DS_t = r * D`` for ``t <= g`` and the PV in
step 2 is taken back only as far as the end of grace, because the balance is
still ``D`` at that point.

WHY THE COVERAGE RATIOS USE THE DISCOUNT RATES THEY USE
-------------------------------------------------------
**DSCR** is a flow test: this period's cash over this period's service. It says
nothing about tomorrow.

**LLCR** = PV of CFADS over the remaining *loan life*, discounted at the **debt
rate**, divided by the debt outstanding. The debt rate is the right discount
rate because the ratio is a like-for-like comparison against the loan's own
economics: the denominator is a balance that compounds at ``r``, so valuing the
numerator at anything other than ``r`` would compare two different currencies.
An LLCR of 1.40x means the cash the loan can reach, valued the way the loan is
valued, is 1.4x the loan. It is the standard restructuring/refinancing test.

**PLCR** is the same calculation with the CFADS horizon extended to the **full
project life** rather than the loan maturity. It therefore captures the tail -
the cash the asset produces after the loan matures - and is always >= LLCR.
Lenders look at the LLCR/PLCR gap to see how much residual value they could
restructure into if the deal underperforms.

All three are computed here; ``SizingResult.summary()`` reports which one
actually binds the debt.
"""

from __future__ import annotations

from engine.defaults import (
    CASH_TOLERANCE,
    MONTHS_PER_YEAR,
    NO_LIMIT,
    RATIO_TOLERANCE,
)
from engine.models import (
    AmortizationStyle,
    ConstraintTest,
    DebtResult,
    DebtTerms,
    SizingConstraint,
    SizingResult,
)

__all__ = [
    "annuity_factor",
    "present_value",
    "sculpt_available_service",
    "sculpted_debt_size",
    "effective_grace_periods",
    "service_for_debt_size",
    "build_schedule",
    "llcr",
    "plcr",
    "llcr_series",
    "dsra_targets",
    "size_facility",
]


# ---------------------------------------------------------------------------
# Discounting primitives
# ---------------------------------------------------------------------------


def annuity_factor(rate: float, n_periods: int) -> float:
    """PV of 1 per period for ``n_periods``, in arrears: (1-(1+r)^-n)/r."""
    if n_periods <= 0:
        return 0.0
    if rate == 0.0:
        return float(n_periods)
    return (1.0 - (1.0 + rate) ** (-n_periods)) / rate


def present_value(
    amounts: tuple[float, ...] | list[float],
    rate: float,
    offset: int = 0,
) -> float:
    """PV of a series received in arrears, discounted ``offset`` periods back.

    ``amounts[0]`` is treated as received one period after the valuation date
    unless ``offset`` shifts it: with ``offset = k``, ``amounts[0]`` is
    discounted ``1 - k`` periods. Used to value CFADS as at an interim date.
    """
    return sum(a / (1.0 + rate) ** (i + 1 - offset) for i, a in enumerate(amounts))


# ---------------------------------------------------------------------------
# Sculpting
# ---------------------------------------------------------------------------


def sculpt_available_service(
    cfads: tuple[float, ...],
    targets: tuple[float, ...],
) -> tuple[float, ...]:
    """Maximum debt service each period can carry at the target DSCR: C_t / d_t."""
    if len(cfads) != len(targets):
        raise ValueError("cfads and targets must be the same length")
    return tuple(c / d for c, d in zip(cfads, targets))


def _sculpt_with_grace(
    cfads: tuple[float, ...],
    targets: tuple[float, ...],
    rate: float,
    grace_periods: int,
) -> tuple[float, tuple[float, ...]]:
    """The raw sculpt for a *given* grace period. See ``sculpted_debt_size``."""
    n = len(cfads)
    available = sculpt_available_service(cfads, targets)
    amortising = available[grace_periods:]

    # PV back to the end of the grace period: the balance is still D there.
    pv = present_value(amortising, rate)

    debt_size = pv
    if grace_periods > 0 and rate > 0.0:
        interest_only_cap = min(available[:grace_periods]) / rate
        debt_size = min(pv, interest_only_cap)

    scale = (debt_size / pv) if pv > 0.0 else 0.0
    service = tuple(
        (rate * debt_size) if t < grace_periods else available[t] * scale
        for t in range(n)
    )
    return debt_size, service


def _amortises_non_negatively(
    debt_size: float, service: tuple[float, ...], rate: float
) -> bool:
    """True if the profile never requires principal to go backwards."""
    tolerance = max(CASH_TOLERANCE, abs(debt_size) * 1e-9)
    balance = debt_size
    for ds in service:
        principal = ds - balance * rate
        if principal < -tolerance:
            return False
        balance -= max(principal, 0.0)
    return True


def effective_grace_periods(
    cfads: tuple[float, ...],
    targets: tuple[float, ...],
    rate: float,
    grace_periods: int = 0,
) -> int:
    """Grace period actually required to avoid negative amortisation.

    A pure PV sculpt can imply a debt service *below* the interest accruing in
    the early periods when CFADS ramps steeply and the rate is high. The
    arithmetic is happy with that - it is negative amortisation - but no term
    facility permits it: principal cannot go backwards.

    The market answer is an interest-only holiday at the front of the loan, so
    the engine lengthens the grace period one period at a time until every
    period amortises non-negatively, and caps the quantum at the interest-only
    coverage limit while it does. This is deterministic and terminates in at
    most ``n - 1`` steps.
    """
    n = len(cfads)
    if grace_periods >= n:
        raise ValueError("grace period must be shorter than the debt tenor")
    for g in range(grace_periods, n):
        debt_size, service = _sculpt_with_grace(cfads, targets, rate, g)
        if _amortises_non_negatively(debt_size, service, rate):
            return g
    raise ValueError(
        "no sculpted profile amortises non-negatively against this CFADS "
        "shape at this rate - shorten the tenor or use level payments"
    )


def sculpted_debt_size(
    cfads: tuple[float, ...],
    targets: tuple[float, ...],
    rate: float,
    grace_periods: int = 0,
) -> tuple[float, tuple[float, ...]]:
    """Solve the sculpted debt quantum and service profile.

    Returns
    -------
    (debt_size, debt_service)
        ``debt_service`` has one entry per debt period. Entries inside the
        grace period are interest-only (``r * D``).

    Notes
    -----
    If the grace-period interest ``r * D`` cannot be covered at the target DSCR
    in some grace period, the quantum is capped at ``min(C_t / d_t) / r`` over
    the grace periods and the post-grace service is scaled down pro rata. The
    resulting DSCR is then *above* target in the amortising periods - the deal
    is over-covered rather than under-covered, which is the only acceptable
    direction to err in.

    The grace period is also lengthened automatically if the requested one
    would produce negative amortisation; see ``effective_grace_periods``.
    """
    grace = effective_grace_periods(cfads, targets, rate, grace_periods)
    return _sculpt_with_grace(cfads, targets, rate, grace)


def _level_payment_size(
    cfads: tuple[float, ...],
    targets: tuple[float, ...],
    rate: float,
    grace_periods: int,
) -> tuple[float, tuple[float, ...]]:
    """Size a level-payment (annuity) facility.

    A constant payment ``A`` must clear the target DSCR in *every* amortising
    period, so it is set by the tightest one: ``A = min_t (C_t / d_t)``. The
    quantum is then ``A`` times the annuity factor over the amortising periods.
    Any period with more coverage than the minimum simply goes unused - which
    is exactly why sculpting raises more debt off the same CFADS.
    """
    n = len(cfads)
    available = sculpt_available_service(cfads, targets)
    amortising = available[grace_periods:]
    payment = min(amortising)
    af = annuity_factor(rate, n - grace_periods)
    debt_size = payment * af

    if grace_periods > 0 and rate > 0.0:
        cap = min(available[:grace_periods]) / rate
        if cap < debt_size:
            debt_size = cap
            payment = debt_size / af if af > 0 else 0.0

    service = tuple(
        (rate * debt_size) if t < grace_periods else payment for t in range(n)
    )
    return debt_size, service


def _fixed_principal_size(
    cfads: tuple[float, ...],
    targets: tuple[float, ...],
    rate: float,
    grace_periods: int,
) -> tuple[float, tuple[float, ...]]:
    """Size a fixed-principal (straight-line amortisation) facility.

    With ``m = N - g`` amortising periods the principal is ``D/m`` every period
    and the service in amortising period *k* (k = 1..m) is::

        DS_k = D * [ 1/m + r * (1 - (k-1)/m) ]  =  D * f_k

    Each period imposes ``D <= (C/d) / f_k``, and during grace ``D <= (C/d)/r``.
    The quantum is the minimum over all of them.

    Fixed principal raises less debt than level payment against a flat or
    rising CFADS profile, because its service is front-loaded while the cash is
    not. Against a *declining* profile the ordering reverses - a declining
    service schedule tracks declining CFADS better than a flat one does - so
    the engine does not assume a universal ranking between the two. Sculpting
    dominates both in every case, which is why it is the market standard.
    """
    n = len(cfads)
    m = n - grace_periods
    available = sculpt_available_service(cfads, targets)

    factors: list[float] = []
    for t in range(n):
        if t < grace_periods:
            factors.append(rate)
        else:
            k = t - grace_periods + 1
            factors.append(1.0 / m + rate * (1.0 - (k - 1) / m))

    caps = [
        available[t] / factors[t] if factors[t] > 0 else NO_LIMIT for t in range(n)
    ]
    debt_size = min(caps)
    service = tuple(debt_size * f for f in factors)
    return debt_size, service


def size_debt_service(
    cfads: tuple[float, ...],
    targets: tuple[float, ...],
    rate: float,
    style: AmortizationStyle,
    grace_periods: int = 0,
) -> tuple[float, tuple[float, ...]]:
    """Dispatch to the sizing routine for the requested amortisation style."""
    if style is AmortizationStyle.SCULPTED:
        return sculpted_debt_size(cfads, targets, rate, grace_periods)
    if style is AmortizationStyle.LEVEL:
        return _level_payment_size(cfads, targets, rate, grace_periods)
    if style is AmortizationStyle.FIXED_PRINCIPAL:
        return _fixed_principal_size(cfads, targets, rate, grace_periods)
    raise ValueError(f"unknown amortisation style {style!r}")


def service_for_debt_size(
    debt_size: float,
    cfads: tuple[float, ...],
    targets: tuple[float, ...],
    rate: float,
    style: AmortizationStyle,
    grace_periods: int = 0,
) -> tuple[float, ...]:
    """Re-derive the debt service profile for a quantum below the DSCR maximum.

    When a gearing cap, an LLCR floor or a tail requirement cuts the debt below
    what DSCR alone would support, the *shape* of the repayment profile is
    preserved and the whole profile is scaled down. Because debt size is linear
    in the service profile (it is a PV), the scaling factor is simply
    ``D_target / D_max``. Every DSCR then lands above target - the deal is
    over-covered, which is what a gearing-constrained deal looks like in
    practice.
    """
    max_size, max_service = size_debt_service(
        cfads, targets, rate, style, grace_periods
    )
    if debt_size > max_size + CASH_TOLERANCE:
        raise ValueError(
            f"requested debt {debt_size:,.2f} exceeds the DSCR-supportable "
            f"maximum {max_size:,.2f}"
        )
    if max_size <= 0.0:
        return tuple(0.0 for _ in cfads)
    # Every style's service profile is homogeneous of degree one in the debt
    # size - including the interest-only grace payments, since r x (k D) =
    # k x (r D) - so a single scalar rescales the whole profile exactly.
    scale = debt_size / max_size
    return tuple(s * scale for s in max_service)


# ---------------------------------------------------------------------------
# Schedule construction
# ---------------------------------------------------------------------------


def build_schedule(
    debt_size: float,
    debt_service: tuple[float, ...],
    cfads: tuple[float, ...],
    targets: tuple[float, ...],
    rate: float,
    periods_per_year: int,
    style: AmortizationStyle,
    grace_periods: int = 0,
) -> DebtResult:
    """Turn a debt service profile into a full amortisation schedule."""
    n = len(debt_service)
    opening: list[float] = []
    interest: list[float] = []
    principal: list[float] = []
    closing: list[float] = []

    balance = debt_size
    snap = max(CASH_TOLERANCE, abs(debt_size) * 1e-9)
    service = list(debt_service)

    for t in range(n):
        opening.append(balance)
        i = balance * rate
        p = service[t] - i
        if p < 0.0:
            if p < -snap:
                raise ValueError(
                    f"period {t + 1}: debt service {service[t]:,.2f} does not "
                    f"cover interest {i:,.2f} - facility cannot be built"
                )
            p = 0.0
        if p > balance:
            p = balance
        balance -= p
        if t == n - 1 and abs(balance) <= snap:
            # Absorb floating-point residue into the final principal so the
            # facility repays to exactly zero.
            p += balance
            balance = 0.0
        service[t] = i + p
        interest.append(i)
        principal.append(p)
        closing.append(balance)

    dscr = tuple(
        (c / s) if s > 0 else float("inf") for c, s in zip(cfads, service)
    )
    return DebtResult(
        debt_size=debt_size,
        amortization=style,
        rate_per_period=rate,
        periods_per_year=periods_per_year,
        grace_periods=grace_periods,
        opening_balance=tuple(opening),
        interest=tuple(interest),
        principal=tuple(principal),
        debt_service=tuple(service),
        closing_balance=tuple(closing),
        cfads=tuple(cfads),
        dscr=dscr,
        target_dscr=tuple(targets),
    )


# ---------------------------------------------------------------------------
# Coverage ratios
# ---------------------------------------------------------------------------


def llcr(
    cfads_loan_life: tuple[float, ...],
    debt_outstanding: float,
    rate: float,
    reserves: float = 0.0,
) -> float:
    """Loan Life Coverage Ratio.

    ``(PV of CFADS to loan maturity at the debt rate + available reserves) /
    debt outstanding``. See the module docstring for why the debt rate is the
    correct discount rate. ``reserves`` lets the caller include the DSRA
    balance, which some credit agreements permit; the engine excludes it by
    default because the conservative form is the one lenders test against.
    """
    if debt_outstanding <= 0.0:
        return NO_LIMIT
    return (present_value(cfads_loan_life, rate) + reserves) / debt_outstanding


def plcr(
    cfads_project_life: tuple[float, ...],
    debt_outstanding: float,
    rate: float,
    reserves: float = 0.0,
) -> float:
    """Project Life Coverage Ratio - LLCR with the horizon run to project end.

    PLCR >= LLCR always, and the gap is the value of the tail: cash the asset
    produces after the loan has matured, which is the lender's restructuring
    headroom.
    """
    return llcr(cfads_project_life, debt_outstanding, rate, reserves)


def llcr_series(
    cfads: tuple[float, ...],
    balances: tuple[float, ...],
    rate: float,
    horizon: int | None = None,
) -> tuple[float, ...]:
    """LLCR at the end of every debt period.

    ``balances[t]`` is the closing balance of period ``t+1``; the ratio at that
    date discounts CFADS from period ``t+2`` onwards. ``horizon`` caps the
    CFADS horizon (loan maturity for LLCR, project life for PLCR).
    """
    end = len(cfads) if horizon is None else min(horizon, len(cfads))
    out: list[float] = []
    for t, balance in enumerate(balances):
        forward = cfads[t + 1 : end]
        out.append(llcr(tuple(forward), balance, rate))
    return tuple(out)


# ---------------------------------------------------------------------------
# Reserves
# ---------------------------------------------------------------------------


def dsra_targets(
    debt_service: tuple[float, ...],
    dsra_months: float,
    periods_per_year: int,
    forward_looking: bool = True,
) -> tuple[float, ...]:
    """DSRA target balance at COD and at the end of every debt period.

    The returned tuple has ``len(debt_service) + 1`` entries: index 0 is the
    balance required at COD (this is the amount that must be funded at
    financial close, and it is one of the uses that makes construction funding
    circular), index *t* is the balance required at the end of period *t*.

    Forward-looking (market standard): the reserve holds ``dsra_months`` of the
    debt service *about to fall due*, so at the end of period *t* it is sized
    off periods ``t+1, t+2, ...``. If the reserve horizon is longer than one
    period, later periods are consumed pro rata.

    Backward-looking: sized off the service just paid in period *t*. Simpler,
    and it is what some older credit agreements say, but it under-reserves into
    a rising service profile.
    """
    if dsra_months <= 0:
        return tuple(0.0 for _ in range(len(debt_service) + 1))

    period_months = MONTHS_PER_YEAR / periods_per_year

    def months_of_service(start_index: int) -> float:
        """Sum ``dsra_months`` of service starting at 0-based ``start_index``."""
        remaining = dsra_months
        total = 0.0
        idx = start_index
        while remaining > 1e-12 and 0 <= idx < len(debt_service):
            take = min(remaining, period_months)
            total += debt_service[idx] * (take / period_months)
            remaining -= take
            idx += 1
        return total

    targets: list[float] = []
    for t in range(len(debt_service) + 1):
        if forward_looking:
            targets.append(months_of_service(t))
        else:
            targets.append(months_of_service(max(t - 1, 0)) if t > 0 else
                           months_of_service(0))
    targets[-1] = 0.0  # released at maturity
    return tuple(targets)


# ---------------------------------------------------------------------------
# Sizing with the full set of credit tests
# ---------------------------------------------------------------------------

#: Order used to break ties when two tests permit the same quantum. DSCR first
#: because a deal that is simultaneously DSCR- and gearing-limited is described
#: by practitioners as DSCR-bound.
_TIE_BREAK_ORDER: tuple[SizingConstraint, ...] = (
    SizingConstraint.DSCR,
    SizingConstraint.GEARING,
    SizingConstraint.TAIL,
    SizingConstraint.LLCR,
    SizingConstraint.PLCR,
    SizingConstraint.TENOR,
)


def size_facility(
    cfads: tuple[float, ...],
    terms: DebtTerms,
    periods_per_year: int,
    project_life_periods: int | None = None,
    total_project_cost: float | None = None,
) -> SizingResult:
    """Size the senior facility against every credit test and report the binder.

    Parameters
    ----------
    cfads:
        CFADS for the full project life, from the first operating period.
    terms:
        Facility terms and credit tests.
    periods_per_year:
        Model frequency (1 = annual, 2 = semi-annual).
    project_life_periods:
        Length of the project life in periods. Defaults to ``len(cfads)``.
        Used for the tail test and for PLCR.
    total_project_cost:
        Funded project cost including IDC, fees and the initial DSRA. Required
        for the gearing test; omit it to skip that test (the gearing figure
        reported will then be based on nothing and is returned as 0.0).
        ``engine.circularity.solve_funding`` supplies it consistently.

    Returns
    -------
    SizingResult
        The schedule, every test, and ``binding_constraint``.
    """
    life_periods = project_life_periods or len(cfads)
    if life_periods > len(cfads):
        raise ValueError("project life exceeds the CFADS series supplied")

    rate = terms.rate_per_period(periods_per_year)
    requested_periods = min(terms.periods(periods_per_year), life_periods)
    if requested_periods <= 0:
        raise ValueError("debt tenor rounds to zero periods")

    grace = terms.grace_periods(periods_per_year)

    # --- tenor / tail -------------------------------------------------------
    required_tail_periods = int(round(terms.tail_years * periods_per_year))
    tail_max_periods = life_periods - required_tail_periods
    if tail_max_periods <= 0:
        raise ValueError(
            "the required tail is longer than the project life - no debt is "
            "possible on these terms"
        )
    n_periods = min(requested_periods, tail_max_periods)
    if grace >= n_periods:
        raise ValueError("grace period must be shorter than the debt tenor")

    targets_full = terms.dscr_profile(terms.periods(periods_per_year))
    targets = targets_full[:n_periods]

    # --- quantum implied by each test --------------------------------------
    dscr_debt, _ = size_debt_service(
        cfads[:requested_periods],
        targets_full[:requested_periods],
        rate,
        terms.amortization,
        grace,
    )
    if dscr_debt <= 0.0:
        raise ValueError(
            "CFADS supports no debt at the target DSCR - check the operating "
            "model before looking at the facility"
        )

    tail_debt = NO_LIMIT
    if n_periods < requested_periods:
        tail_debt, _ = size_debt_service(
            cfads[:n_periods], targets, rate, terms.amortization, grace
        )

    gearing_debt = (
        terms.max_gearing * total_project_cost
        if total_project_cost is not None
        else NO_LIMIT
    )

    pv_loan_life = present_value(cfads[:n_periods], rate)
    pv_project_life = present_value(cfads[:life_periods], rate)
    llcr_debt = (
        pv_loan_life / terms.min_llcr if terms.min_llcr else NO_LIMIT
    )
    plcr_debt = (
        pv_project_life / terms.min_plcr if terms.min_plcr else NO_LIMIT
    )

    candidates: dict[SizingConstraint, float] = {
        SizingConstraint.DSCR: dscr_debt,
        SizingConstraint.TAIL: tail_debt,
        SizingConstraint.GEARING: gearing_debt,
        SizingConstraint.LLCR: llcr_debt,
        SizingConstraint.PLCR: plcr_debt,
    }
    debt_size = min(candidates.values())
    tolerance = max(CASH_TOLERANCE, abs(debt_size) * 1e-12)
    binding = next(
        c
        for c in _TIE_BREAK_ORDER
        if c in candidates and candidates[c] <= debt_size + tolerance
    )

    # --- build the schedule at the constrained quantum ----------------------
    service = service_for_debt_size(
        debt_size, cfads[:n_periods], targets, rate, terms.amortization, grace
    )
    applied_grace = grace
    if terms.amortization is AmortizationStyle.SCULPTED:
        applied_grace = effective_grace_periods(
            cfads[:n_periods], targets, rate, grace
        )
    schedule = build_schedule(
        debt_size,
        service,
        cfads[:n_periods],
        targets,
        rate,
        periods_per_year,
        terms.amortization,
        applied_grace,
    )

    dsra = dsra_targets(
        schedule.debt_service,
        terms.dsra_months,
        periods_per_year,
        terms.dsra_forward_looking,
    )

    achieved_llcr = llcr(cfads[:n_periods], debt_size, rate)
    achieved_plcr = plcr(cfads[:life_periods], debt_size, rate)
    series = llcr_series(cfads, schedule.closing_balance, rate, horizon=n_periods)
    gearing = (
        debt_size / total_project_cost
        if total_project_cost not in (None, 0.0)
        else 0.0
    )
    tail_years = (life_periods - n_periods) / periods_per_year
    covenant = terms.covenant_dscr or 0.0

    tests = (
        ConstraintTest(
            constraint=SizingConstraint.DSCR,
            implied_debt=dscr_debt,
            limit=min(targets),
            actual=schedule.min_dscr,
            binds=binding is SizingConstraint.DSCR,
            passes=schedule.min_dscr >= covenant - RATIO_TOLERANCE,
            note=(
                "sculpted to the target profile"
                if terms.amortization is AmortizationStyle.SCULPTED
                else f"{terms.amortization.value} amortisation"
            ),
        ),
        ConstraintTest(
            constraint=SizingConstraint.GEARING,
            implied_debt=gearing_debt,
            limit=terms.max_gearing,
            actual=gearing,
            binds=binding is SizingConstraint.GEARING,
            passes=gearing <= terms.max_gearing + RATIO_TOLERANCE,
            note=(
                "debt / total funded project cost"
                if total_project_cost is not None
                else "not tested - no project cost supplied"
            ),
        ),
        ConstraintTest(
            constraint=SizingConstraint.TENOR,
            implied_debt=NO_LIMIT,
            limit=terms.tenor_years,
            actual=n_periods / periods_per_year,
            binds=False,
            passes=n_periods <= requested_periods,
            note=(
                "tenor shortened by the tail requirement"
                if n_periods < requested_periods
                else "as requested"
            ),
        ),
        ConstraintTest(
            constraint=SizingConstraint.TAIL,
            implied_debt=tail_debt,
            limit=terms.tail_years,
            actual=tail_years,
            binds=binding is SizingConstraint.TAIL,
            passes=tail_years >= terms.tail_years - RATIO_TOLERANCE,
            note="project life less debt tenor",
        ),
        ConstraintTest(
            constraint=SizingConstraint.LLCR,
            implied_debt=llcr_debt,
            limit=terms.min_llcr if terms.min_llcr else 0.0,
            actual=achieved_llcr,
            binds=binding is SizingConstraint.LLCR,
            passes=(
                achieved_llcr >= terms.min_llcr - RATIO_TOLERANCE
                if terms.min_llcr
                else True
            ),
            note="PV of CFADS to maturity at the debt rate / debt",
        ),
        ConstraintTest(
            constraint=SizingConstraint.PLCR,
            implied_debt=plcr_debt,
            limit=terms.min_plcr if terms.min_plcr else 0.0,
            actual=achieved_plcr,
            binds=binding is SizingConstraint.PLCR,
            passes=(
                achieved_plcr >= terms.min_plcr - RATIO_TOLERANCE
                if terms.min_plcr
                else True
            ),
            note="PV of CFADS to project end at the debt rate / debt",
        ),
    )

    return SizingResult(
        debt=schedule,
        binding_constraint=binding,
        tests=tests,
        min_dscr=schedule.min_dscr,
        llcr=achieved_llcr,
        plcr=achieved_plcr,
        llcr_series=series,
        gearing=gearing,
        tail_years=tail_years,
        total_project_cost=total_project_cost or 0.0,
        dsra_target=dsra,
    )
