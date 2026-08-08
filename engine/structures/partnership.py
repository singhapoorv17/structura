"""§704(b) capital accounts, DROs, outside basis and suspended losses.

A grep of SAM's three finance modules (``cmod_levpartflip.cpp``,
``cmod_singleowner.cpp``, ``common.cpp``) returns zero hits for
``capital_account``, ``deficit_restoration``, ``outside_basis``, ``704(b)`` or
``suspended_loss``: its partnership flip is a stylised fixed percentage split
with an IRR-triggered flip date. This module implements the partnership-tax
layer underneath such a split.

The ledgers, and why there are three of them
--------------------------------------------
A partner in a project partnership has **three** running balances, and
practitioners conflate them at their peril:

**1. The §704(b) capital account** (:attr:`PartnerPeriod.capital_closing`).
A *book* balance maintained under Treas. Reg. §1.704-1(b)(2)(iv). It goes up by
contributions and allocated book income and down by distributions and allocated
book loss. It is the yardstick for whether an allocation has **economic
effect** — i.e. whether the IRS will respect it — because on liquidation the
partnership must distribute according to positive capital accounts.

**2. Outside basis** (:attr:`PartnerPeriod.outside_basis_closing`).
A *tax* balance under §705: contributions, plus the distributive share of
taxable income, plus the share of partnership liabilities under §752, less
distributions, less losses **allowed**. It can never go below zero. It is the
ceiling on loss deductibility under §704(d).

**3. Partnership minimum gain** (:attr:`PartnerPeriod.minimum_gain_share`).
Treas. Reg. §1.704-2(d): the gain the partnership would realise if it disposed
of property subject to a nonrecourse liability in satisfaction of that
liability. A partner's share of it functions as a **deemed** deficit
restoration obligation (§1.704-2(g)(1)), which is why a tax-equity investor
with no DRO at all can still be allocated losses that drive its capital account
negative — up to its share of minimum gain, and no further.

The five mechanics implemented
------------------------------
**Capital accounts, period by period.** §1.704-1(b)(2)(iv). Contributions,
allocations, distributions, and the §1.704-1(b)(2)(iv)(j) adjustment for the
§50(c)(3) investment-credit basis reduction, which is treated as an item of
loss for capital-account purposes.

**Deficit restoration obligations and the DRO cap.** An allocation has economic
effect under the alternate test of §1.704-1(b)(2)(ii)(d) only if it does not
create a capital-account deficit the partner is not obliged to restore. So each
partner has a **floor**::

    floor_i = -(dro_cap_i + minimum_gain_share_i)

An allocation that would breach the floor is capped, and the excess is
**reallocated** to the partners who still have capacity, pro rata to that
capacity. This is the single most consequential mechanic in a flip: it is why a
tax-equity investor stops absorbing losses part-way through the deal and the
sponsor starts absorbing them instead, and it is why the flip point moves.
Total allocations always still sum to 100% of the item; that is asserted.

**Outside basis and the §704(d) limitation.** A loss is deductible only to the
extent of outside basis (including the §752 share of nonrecourse liabilities).
The disallowed part is **suspended**, carried forward indefinitely, and freed
in a later year as basis is restored — first in, first out.

**Minimum gain chargeback.** §1.704-2(f). If partnership minimum gain *net
decreases* in a year, each partner must first be allocated items of income
equal to its share of the decrease. See "Declared simplifications" below for
exactly how much of §1.704-2 is modelled.

**The 50% ITC basis reduction.** §50(c)(3), computed by
:func:`engine.tax.depreciation.reduced_basis` and *not* reimplemented here.
This module consumes the resulting basis-reduction amount and applies it to the
capital accounts and to outside basis, allocated in the same ratio as the
credit (§50(c)(5)).

Declared simplifications
------------------------
Every one of these is also recorded in ``LIMITS_STRUCTURES.md``:

* **Minimum gain is derived, not tracked property by property.** Partnership
  minimum gain is computed as ``max(0, nonrecourse liability - book basis)`` on
  a single pooled asset. The regulations compute it property by property.
* **A partner's minimum-gain share** is tracked as its cumulative share of
  nonrecourse deductions less prior chargebacks. §1.704-2(g) builds the share
  from nonrecourse deductions *and* distributions of nonrecourse liability
  proceeds; the latter is not separately identified here.
* **Partner nonrecourse debt minimum gain** (§1.704-2(i)) is not modelled.
* **§704(c)** allocations (traditional, curative and remedial) are **not**
  implemented. Book and tax ledgers are maintained separately and a caller-
  supplied book/tax difference is honoured, but no reverse or forward §704(c)
  layer is computed.
* **Qualified income offset** (§1.704-1(b)(2)(ii)(d)) is not implemented as a
  separate mechanic; the DRO-cap floor prevents the deficits a QIO would cure.
* **§465 at-risk** and **§469 passive activity** limits are not modelled. Only
  the §704(d) basis limitation is.
* A **§731(a)(1) gain on a distribution in excess of basis** is recorded and
  reported but is not fed back into the capital accounts (it is a tax item, not
  a book item).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

from engine.structures.defaults import (
    ALLOCATION_TOLERANCE,
    CAPITAL_ACCOUNT_TOLERANCE,
    REALLOCATION_MAX_PASSES,
)

__all__ = [
    "PartnerRole",
    "PartnerTerms",
    "SharingRatios",
    "PeriodInputs",
    "ReallocationEvent",
    "CapitalAccountBreach",
    "PartnerPeriod",
    "PartnershipPeriod",
    "PartnershipResult",
    "run_partnership",
    "assert_capital_account_integrity",
]


class PartnerRole(str, Enum):
    """What a partner is in the deal, for reporting and risk attribution."""

    SPONSOR = "sponsor"
    TAX_EQUITY = "tax_equity"
    PREFERRED = "preferred"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PartnerTerms:
    """One partner's standing terms.

    Parameters
    ----------
    dro_cap
        The **deficit restoration obligation**: the maximum negative §704(b)
        capital account this partner has contractually agreed to restore on
        liquidation, in currency units, as a non-negative number. Zero means no
        DRO — the common position for a tax-equity investor, which relies
        instead on its share of minimum gain. A sponsor typically carries an
        unlimited or very large DRO.
    unlimited_dro
        True treats the DRO as unbounded. Modelled as an explicit flag rather
        than a large number so that "unlimited" never silently becomes a magic
        constant.
    bears_residual_allocations
        Where a loss cannot be absorbed by *any* partner within its floor, it
        is allocated to the partner(s) flagged here and a warning is raised.
        Exactly one partner should carry this; it is the general partner in
        substance.
    tax_rate
        Marginal rate applied to this partner's distributive share when its
        after-tax cashflow is assembled.
    """

    name: str
    role: PartnerRole
    tax_rate: float
    dro_cap: float = 0.0
    unlimited_dro: bool = False
    bears_residual_allocations: bool = False

    def __post_init__(self) -> None:
        if self.dro_cap < 0.0:
            raise ValueError(f"{self.name}: dro_cap must be >= 0")
        if not 0.0 <= self.tax_rate < 1.0:
            raise ValueError(f"{self.name}: tax_rate must lie in [0, 1)")


@dataclass(frozen=True, slots=True)
class SharingRatios:
    """The four sharing ratios that define a partnership period.

    Income, loss, credit and cash are separate ratios because in a real flip
    they genuinely differ: the investor commonly takes 99% of income, loss and
    credits but only a minority of the cash. Each mapping is keyed by partner
    name and must sum to 1.0.
    """

    income: Mapping[str, float]
    loss: Mapping[str, float]
    credit: Mapping[str, float]
    cash: Mapping[str, float]

    def __post_init__(self) -> None:
        for label in ("income", "loss", "credit", "cash"):
            ratio: Mapping[str, float] = getattr(self, label)
            total = sum(ratio.values())
            if abs(total - 1.0) > ALLOCATION_TOLERANCE:
                raise ValueError(
                    f"{label} sharing ratios sum to {total!r}, not 1.0 - "
                    f"an allocation that does not account for 100% of an item "
                    f"cannot have economic effect"
                )
            if any(v < 0.0 for v in ratio.values()):
                raise ValueError(f"{label} sharing ratios must be non-negative")


@dataclass(frozen=True, slots=True)
class PeriodInputs:
    """Everything the partnership earns, owes, holds and pays in one tax year.

    Parameters
    ----------
    book_income
        §704(b) book income or loss for the year, signed. Revenue less operating
        expense less interest less **book** depreciation.
    taxable_income
        Federal taxable income or loss for the year, signed. The same line using
        **tax** depreciation. Equal to ``book_income`` in the ordinary case
        where book basis equals tax basis; the two are maintained separately so
        that the distinction is structural rather than assumed away.
    credit
        Investment or production credit arising this year, before allocation.
    itc_basis_reduction
        The §50(c)(3) reduction (half the ITC) for the year in which the credit
        arises. Applied to capital accounts under §1.704-1(b)(2)(iv)(j) and to
        outside basis under §50(c)(5), allocated on the **credit** ratio.
    cash_available
        Cash available for distribution to partners this year.
    contributions
        Capital contributed this year, by partner name.
    nonrecourse_liability
        Closing balance of partnership nonrecourse liabilities. Drives both the
        §752 basis share and partnership minimum gain.
    book_basis
        Closing §704(b) book basis of the partnership's property. With
        ``nonrecourse_liability`` this is what produces minimum gain.
    nonrecourse_deductions
        The portion of the year's book loss funded by nonrecourse borrowing, as
        a positive number. Under §1.704-2(c) these are the deductions that
        increase minimum gain and that build a partner's minimum-gain share.
        Defaults to the increase in minimum gain, which is the regulation's own
        definition and needs no separate input in the ordinary case.
    """

    period: int
    year: int
    book_income: float = 0.0
    taxable_income: float = 0.0
    credit: float = 0.0
    itc_basis_reduction: float = 0.0
    cash_available: float = 0.0
    contributions: Mapping[str, float] = field(default_factory=dict)
    nonrecourse_liability: float = 0.0
    book_basis: float = 0.0
    nonrecourse_deductions: float | None = None


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReallocationEvent:
    """A loss allocation that hit a DRO cap and had to move.

    ``amount`` is the positive magnitude of loss taken away from ``from_partner``
    and given to ``to_partner`` because ``from_partner``'s §704(b) capital
    account would otherwise have fallen below its floor.
    """

    period: int
    from_partner: str
    to_partner: str
    amount: float
    reason: str


@dataclass(frozen=True, slots=True)
class CapitalAccountBreach:
    """A partner whose §704(b) capital account sat below its floor, itemised.

    Structured rather than prose because it is the single most consequential
    diagnostic this module produces and it must not be lost in a list of
    warnings. A capital account below ``-(DRO cap + minimum gain share)`` means
    the partnership has distributed cash the partner has no obligation to
    restore. It is **not** an economic-effect failure — an allocation never
    causes it, the DRO-cap mechanic sees to that — but it is the fact pattern a
    real LLC agreement cures with a **qualified income offset** under Treas.
    Reg. §1.704-1(b)(2)(ii)(d), or by restricting the distribution outright.
    Structura implements neither (``LIMITS_STRUCTURES.md`` §1.5), so it reports.
    """

    partner: str
    periods: tuple[int, ...]
    """Zero-indexed periods in which the account sat below its floor."""
    years: tuple[int, ...]
    worst_breach: float
    """Most negative (capital account − floor). Always ≤ 0."""
    worst_period: int
    worst_year: int
    cause: str
    """``"distributions"`` in every case the engine can produce: the DRO-cap
    mechanic makes an allocation-driven breach impossible, and
    :func:`assert_capital_account_integrity` raises if one ever occurs."""

    @property
    def n_periods(self) -> int:
        return len(self.periods)

    def describe(self) -> str:
        return (
            f"'{self.partner}': §704(b) capital account below its floor in "
            f"{self.n_periods} period(s) ({self.years[0]}-{self.years[-1]}), "
            f"worst breach ${self.worst_breach:,.0f} in {self.worst_year}, "
            f"driven by {self.cause}. A qualified income offset would cure it; "
            f"Structura does not model one."
        )


@dataclass(frozen=True, slots=True)
class PartnerPeriod:
    """One partner's three ledgers for one year, fully itemised.

    Every field is a line a reviewer can tie by hand. The capital-account
    identity is::

        capital_closing = capital_opening + contributions + book_allocation
                          - distributions - itc_basis_reduction_share
    """

    partner: str
    period: int
    year: int

    # --- §704(b) capital account -----------------------------------------
    capital_opening: float
    contributions: float
    book_allocation_base: float
    """Book income/loss the base sharing ratio would have given this partner."""
    book_reallocation: float
    """Signed adjustment applied by the DRO-cap mechanic. Positive means this
    partner absorbed loss reallocated from another; negative means loss was
    taken away from it."""
    book_allocation: float
    """Book income/loss actually allocated, after the DRO cap and the minimum
    gain chargeback."""
    chargeback_income: float
    """Portion of ``book_allocation`` that is a §1.704-2(f) minimum gain
    chargeback rather than an ordinary sharing-ratio allocation."""
    distributions: float
    itc_basis_reduction_share: float
    capital_after_allocation: float
    """Capital account after contributions, the §1.704-1(b)(2)(iv)(j) credit
    adjustment and the year's allocations, but **before** distributions. This
    is the balance economic effect is tested on: an *allocation* may not drive
    the account below its floor, whereas a *distribution* that does is a
    different problem with a different cure (a qualified income offset)."""
    capital_closing: float
    dro_cap: float
    capital_floor: float
    """``-(dro_cap + minimum_gain_share)``: how negative this account may go."""
    floor_binds: bool
    """True where the DRO cap actually moved this partner's allocation."""

    # --- outside basis and §704(d) ---------------------------------------
    outside_basis_opening: float
    liability_share_opening: float
    liability_share_closing: float
    taxable_allocation: float
    """Signed distributive share of taxable income/loss before §704(d)."""
    taxable_loss_allowed: float
    """Positive magnitude of loss actually deductible this year, including any
    suspended loss freed."""
    taxable_loss_suspended: float
    """Positive magnitude of this year's loss disallowed by §704(d)."""
    suspended_loss_opening: float
    suspended_loss_freed: float
    suspended_loss_closing: float
    outside_basis_closing: float
    excess_distribution_gain: float
    """§731(a)(1) gain from a distribution exceeding outside basis."""

    # --- credits and minimum gain ----------------------------------------
    credit_allocated: float
    minimum_gain_share: float

    @property
    def taxable_income_recognised(self) -> float:
        """Signed taxable amount actually reported by this partner this year.

        Income allocations flow through in full; loss allocations flow through
        only to the extent §704(d) allows. §731(a)(1) gain is added.
        """
        if self.taxable_allocation >= 0.0:
            return self.taxable_allocation + self.excess_distribution_gain
        return -self.taxable_loss_allowed + self.excess_distribution_gain


@dataclass(frozen=True, slots=True)
class PartnershipPeriod:
    """One tax year of the partnership, across all partners."""

    period: int
    year: int
    book_income: float
    taxable_income: float
    credit: float
    cash_distributed: float
    contributions: float
    minimum_gain: float
    minimum_gain_net_decrease: float
    chargeback_required: float
    chargeback_allocated: float
    chargeback_carryforward: float
    partners: tuple[PartnerPeriod, ...]
    reallocations: tuple[ReallocationEvent, ...]

    def partner(self, name: str) -> PartnerPeriod:
        for p in self.partners:
            if p.partner == name:
                return p
        raise KeyError(name)


@dataclass(frozen=True, slots=True)
class PartnershipResult:
    """The full partnership ledger, plus everything a caller needs downstream."""

    partners: tuple[PartnerTerms, ...]
    periods: tuple[PartnershipPeriod, ...]
    warnings: tuple[str, ...] = ()
    capital_account_breaches: tuple[CapitalAccountBreach, ...] = ()
    citation_ids: tuple[str, ...] = (
        "reg-1-704-1b2iv-capital-accounts",
        "reg-1-704-1b2iid-alternate-economic-effect",
        "reg-1-704-2-minimum-gain",
        "section-704d-basis-limitation",
        "section-705-outside-basis",
        "section-752-liability-share",
        "section-50c3-itc-basis-reduction",
    )

    def partner_series(self, name: str) -> tuple[PartnerPeriod, ...]:
        """This partner's ledger, one entry per period."""
        return tuple(p.partner(name) for p in self.periods)

    def capital_account(self, name: str) -> tuple[float, ...]:
        return tuple(p.partner(name).capital_closing for p in self.periods)

    def outside_basis(self, name: str) -> tuple[float, ...]:
        return tuple(p.partner(name).outside_basis_closing for p in self.periods)

    def suspended_losses(self, name: str) -> tuple[float, ...]:
        return tuple(p.partner(name).suspended_loss_closing for p in self.periods)

    def distributions(self, name: str) -> tuple[float, ...]:
        return tuple(p.partner(name).distributions for p in self.periods)

    def credits(self, name: str) -> tuple[float, ...]:
        return tuple(p.partner(name).credit_allocated for p in self.periods)

    def taxable_income(self, name: str) -> tuple[float, ...]:
        """Signed taxable amount recognised, after the §704(d) limitation."""
        return tuple(
            p.partner(name).taxable_income_recognised for p in self.periods
        )

    def after_tax_cashflow(
        self, name: str, tax_rate: float | None = None
    ) -> tuple[float, ...]:
        """Cash + tax effect, period by period, from this partner's chair.

        ``distribution - tax_rate x taxable income + credits``. A loss
        allocation therefore shows up as a positive number (a tax *benefit*),
        which is exactly why a tax-equity investor is willing to fund a project
        that distributes it very little cash.
        """
        rate = tax_rate
        if rate is None:
            rate = next(p.tax_rate for p in self.partners if p.name == name)
        out: list[float] = []
        for period in self.periods:
            row = period.partner(name)
            out.append(
                row.distributions
                - rate * row.taxable_income_recognised
                + row.credit_allocated
            )
        return tuple(out)


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------


def _capacity(capital: float, floor: float) -> float:
    """How much further loss a partner can absorb before breaching its floor."""
    return max(capital - floor, 0.0)


def _allocate_loss_with_dro_caps(
    *,
    period: int,
    loss: float,
    base_shares: Mapping[str, float],
    capitals: Mapping[str, float],
    floors: Mapping[str, float],
    unlimited: Mapping[str, bool],
    residual_partner: str,
    names: Sequence[str],
) -> tuple[dict[str, float], list[ReallocationEvent], list[str]]:
    """Split a book **loss** across partners, respecting every DRO cap.

    ``loss`` is a positive magnitude. Returns per-partner positive magnitudes.

    The mechanic, in the order Treas. Reg. §1.704-1(b)(2)(ii)(d) forces:

    1. Allocate on the stated loss ratio.
    2. Any partner whose account would fall below
       ``-(DRO cap + minimum gain share)`` is capped at exactly its floor.
    3. The excess is reallocated to the partners that still have capacity,
       **pro rata to that remaining capacity** — the convention every flip LLC
       agreement uses, because it is the allocation that keeps each partner's
       deficit proportional to its obligation to restore it.
    4. Repeat until the excess is exhausted or nobody has capacity left. Each
       pass removes at least one partner from the capacity pool, so this
       terminates.
    5. If capacity runs out entirely, the remainder lands on the partner flagged
       ``bears_residual_allocations`` and a warning is emitted. That is a
       modelling failure signal, not a tax result: in practice the LLC agreement
       would either carry an unlimited sponsor DRO or the deal would not close.
    """
    allocated: dict[str, float] = {n: 0.0 for n in names}
    events: list[ReallocationEvent] = []
    warnings: list[str] = []
    if loss <= 0.0:
        return allocated, events, warnings

    working = {n: capitals[n] for n in names}
    remaining = loss
    shares = {n: float(base_shares.get(n, 0.0)) for n in names}
    active = {n for n in names if shares[n] > 0.0}

    for _pass in range(REALLOCATION_MAX_PASSES):
        if remaining <= CAPITAL_ACCOUNT_TOLERANCE or not active:
            break
        share_total = sum(shares[n] for n in active)
        if share_total <= 0.0:
            break
        excess = 0.0
        blocked: list[str] = []
        for n in sorted(active):
            want = remaining * shares[n] / share_total
            cap = float("inf") if unlimited[n] else _capacity(working[n], floors[n])
            take = min(want, cap)
            allocated[n] += take
            working[n] -= take
            if want - take > CAPITAL_ACCOUNT_TOLERANCE:
                excess += want - take
                blocked.append(n)
        remaining = excess
        for n in blocked:
            active.discard(n)
        if remaining <= CAPITAL_ACCOUNT_TOLERANCE:
            remaining = 0.0
            break
        # Reopen the pool to everyone still holding capacity, weighted **pro
        # rata to that remaining capacity**.
        caps = {
            n: (float("inf") if unlimited[n] else _capacity(working[n], floors[n]))
            for n in names
        }
        live = {n: c for n, c in caps.items() if c > CAPITAL_ACCOUNT_TOLERANCE}
        if not live:
            active = set()
            break
        infinite = [n for n, c in live.items() if c == float("inf")]
        if infinite:
            shares = {n: (1.0 if n in infinite else 0.0) for n in names}
            active = set(infinite)
        else:
            total_cap = sum(live.values())
            shares = {n: live.get(n, 0.0) / total_cap for n in names}
            active = set(live)

    if remaining > CAPITAL_ACCOUNT_TOLERANCE:
        allocated[residual_partner] += remaining
        warnings.append(
            f"Period {period}: {remaining:,.0f} of book loss could not be "
            f"absorbed by any partner within its deficit restoration obligation "
            f"and was allocated to '{residual_partner}' as the residual bearer. "
            f"A real LLC agreement would resolve this with an unlimited sponsor "
            f"DRO or a qualified income offset; Structura does not invent one."
        )

    # Express the net movement as explicit donor -> recipient events, pro rata,
    # so a reviewer can see exactly whose loss went where and why.
    donors = {
        n: loss * float(base_shares.get(n, 0.0)) - allocated[n]
        for n in names
        if loss * float(base_shares.get(n, 0.0)) - allocated[n]
        > CAPITAL_ACCOUNT_TOLERANCE
    }
    takers = {
        n: allocated[n] - loss * float(base_shares.get(n, 0.0))
        for n in names
        if allocated[n] - loss * float(base_shares.get(n, 0.0))
        > CAPITAL_ACCOUNT_TOLERANCE
    }
    taker_total = sum(takers.values())
    if donors and taker_total > 0.0:
        for donor, shed in sorted(donors.items()):
            for taker, gained in sorted(takers.items()):
                events.append(
                    ReallocationEvent(
                        period=period,
                        from_partner=donor,
                        to_partner=taker,
                        amount=shed * gained / taker_total,
                        reason=(
                            f"{donor} reached its DRO cap: a further loss "
                            f"allocation would have driven its §704(b) capital "
                            f"account below {floors[donor]:,.2f} and would not "
                            f"have had economic effect under Treas. Reg. "
                            f"§1.704-1(b)(2)(ii)(d)."
                        ),
                    )
                )
    return allocated, events, warnings


def run_partnership(
    partners: Sequence[PartnerTerms],
    periods: Sequence[PeriodInputs],
    ratios: Sequence[SharingRatios],
    *,
    initial_capital: Mapping[str, float] | None = None,
    initial_outside_basis: Mapping[str, float] | None = None,
    initial_book_basis: float = 0.0,
    initial_nonrecourse_liability: float = 0.0,
) -> PartnershipResult:
    """Run the §704(b) ledger for every partner over every period.

    Parameters
    ----------
    partners
        Standing terms. Exactly one partner must carry
        ``bears_residual_allocations``.
    periods
        One :class:`PeriodInputs` per tax year, in order.
    ratios
        One :class:`SharingRatios` per period. Passing a different ratio for a
        period is how a flip flips: nothing else in this function knows what a
        flip is.
    initial_book_basis, initial_nonrecourse_liability
        Opening balances, used to compute the minimum gain at period 0 and
        therefore the first year's net increase or decrease.

    Order of operations within a period
    -----------------------------------
    Chosen to match the order a partnership tax return is actually prepared:

    1. **Contributions** — capital account and outside basis up.
    2. **Minimum gain** recomputed; a net decrease triggers a **chargeback** of
       gross income, allocated before anything else (§1.704-2(f)).
    3. **Residual book income or loss** allocated on the income/loss ratio,
       with the DRO-cap reallocation applied to loss.
    4. **§50(c)(3)/§1.704-1(b)(2)(iv)(j)** investment-credit basis reduction,
       allocated on the credit ratio, charged to capital accounts and basis.
    5. **Distributions** — capital account and outside basis down; anything in
       excess of basis is §731(a)(1) gain.
    6. **§752 liability share** re-struck; the change moves outside basis.
    7. **§704(d)** applied: losses allowed only to the extent of basis, the rest
       suspended; previously suspended losses freed first, FIFO.
    """
    names = [p.name for p in partners]
    if len(set(names)) != len(names):
        raise ValueError("partner names must be unique")
    if len(periods) != len(ratios):
        raise ValueError(
            f"{len(periods)} periods but {len(ratios)} sharing-ratio sets"
        )
    residual = [p.name for p in partners if p.bears_residual_allocations]
    if len(residual) != 1:
        raise ValueError(
            "exactly one partner must carry bears_residual_allocations "
            "(the general partner in substance)"
        )
    residual_partner = residual[0]
    for r in ratios:
        for label in ("income", "loss", "credit", "cash"):
            unknown = set(getattr(r, label)) - set(names)
            if unknown:
                raise ValueError(f"unknown partner(s) in {label} ratio: {unknown}")

    unlimited = {p.name: p.unlimited_dro for p in partners}
    dro_cap = {p.name: p.dro_cap for p in partners}

    capital = dict(initial_capital or {n: 0.0 for n in names})
    basis = dict(initial_outside_basis or {n: 0.0 for n in names})
    suspended = {n: 0.0 for n in names}
    mg_share = {n: 0.0 for n in names}
    liability_share = {n: 0.0 for n in names}
    for n in names:
        capital.setdefault(n, 0.0)
        basis.setdefault(n, 0.0)

    prior_minimum_gain = max(
        0.0, initial_nonrecourse_liability - initial_book_basis
    )
    chargeback_carry = 0.0

    out_periods: list[PartnershipPeriod] = []
    warnings: list[str] = []

    for row, ratio in zip(periods, ratios):
        events: list[ReallocationEvent] = []
        opening_capital = dict(capital)
        opening_basis = dict(basis)
        opening_suspended = dict(suspended)
        opening_liability = dict(liability_share)

        # -- 1. contributions ------------------------------------------------
        contributions = {n: float(row.contributions.get(n, 0.0)) for n in names}
        for n in names:
            capital[n] += contributions[n]
            basis[n] += contributions[n]

        # -- 2. minimum gain and the §1.704-2(f) chargeback -------------------
        minimum_gain = max(0.0, row.nonrecourse_liability - row.book_basis)
        mg_increase = max(0.0, minimum_gain - prior_minimum_gain)
        mg_decrease = max(0.0, prior_minimum_gain - minimum_gain)

        # Nonrecourse deductions build each partner's minimum-gain share, in the
        # ratio in which those deductions are allocated (§1.704-2(g)(1)). In the
        # ordinary case the deductions equal the increase in minimum gain, which
        # is the regulation's own definition (§1.704-2(c)).
        nr_deductions = (
            mg_increase
            if row.nonrecourse_deductions is None
            else float(row.nonrecourse_deductions)
        )
        if nr_deductions > 0.0:
            for n in names:
                mg_share[n] += nr_deductions * ratio.loss.get(n, 0.0)

        chargeback_required = mg_decrease + chargeback_carry
        chargeback_alloc = {n: 0.0 for n in names}
        chargeback_total = 0.0
        if chargeback_required > CAPITAL_ACCOUNT_TOLERANCE:
            share_pool = sum(mg_share[n] for n in names)
            available_income = max(row.book_income, 0.0)
            chargeback_total = min(chargeback_required, available_income)
            if share_pool > CAPITAL_ACCOUNT_TOLERANCE and chargeback_total > 0.0:
                for n in names:
                    chargeback_alloc[n] = (
                        chargeback_total * mg_share[n] / share_pool
                    )
                    mg_share[n] = max(0.0, mg_share[n] - chargeback_alloc[n])
            else:
                chargeback_total = 0.0
        chargeback_carry = max(0.0, chargeback_required - chargeback_total)

        # -- 3. credits and the §50(c)(3) / §1.704-1(b)(2)(iv)(j) adjustment ---
        # Applied before the year's residual allocation because the credit
        # arises when the property is placed in service, and because the
        # regulation treats the adjustment as an item of loss - so it must be
        # inside the capital account before the DRO floors are tested.
        credit_alloc = {n: row.credit * ratio.credit.get(n, 0.0) for n in names}
        itc_reduction = {
            n: row.itc_basis_reduction * ratio.credit.get(n, 0.0) for n in names
        }
        for n in names:
            capital[n] += chargeback_alloc[n] - itc_reduction[n]

        # -- 4. residual book allocation, with the DRO cap ---------------------
        residual_book = row.book_income - chargeback_total
        floors = {n: -(dro_cap[n] + mg_share[n]) for n in names}
        base_alloc = {n: 0.0 for n in names}
        realloc = {n: 0.0 for n in names}
        book_alloc = {n: 0.0 for n in names}

        if residual_book >= 0.0:
            for n in names:
                base_alloc[n] = residual_book * ratio.income.get(n, 0.0)
                book_alloc[n] = base_alloc[n]
        else:
            loss = -residual_book
            for n in names:
                base_alloc[n] = -loss * ratio.loss.get(n, 0.0)
            taken, events_, warn_ = _allocate_loss_with_dro_caps(
                period=row.period,
                loss=loss,
                base_shares=ratio.loss,
                capitals=dict(capital),
                floors=floors,
                unlimited=unlimited,
                residual_partner=residual_partner,
                names=names,
            )
            events.extend(events_)
            warnings.extend(warn_)
            for n in names:
                book_alloc[n] = -taken[n]
                realloc[n] = book_alloc[n] - base_alloc[n]

        total_book_allocated = sum(book_alloc.values()) + chargeback_total
        if abs(total_book_allocated - row.book_income) > CAPITAL_ACCOUNT_TOLERANCE:
            raise AssertionError(
                f"period {row.period}: book allocations sum to "
                f"{total_book_allocated!r} but book income is "
                f"{row.book_income!r} - allocations must account for 100% of "
                f"the item"
            )

        # Tax items follow the book allocation (§1.704-1(b)(1)(vii)): absent a
        # §704(c) layer, the tax allocation percentage IS the book percentage
        # actually used, including any DRO-cap reallocation. That is the whole
        # reason the reallocation matters to a tax-equity investor's yield.
        effective_book = {n: book_alloc[n] + chargeback_alloc[n] for n in names}
        book_total = sum(effective_book.values())
        tax_alloc: dict[str, float] = {}
        if abs(book_total) > CAPITAL_ACCOUNT_TOLERANCE:
            for n in names:
                tax_alloc[n] = row.taxable_income * effective_book[n] / book_total
        else:
            fallback = (
                ratio.income if row.taxable_income >= 0.0 else ratio.loss
            )
            for n in names:
                tax_alloc[n] = row.taxable_income * fallback.get(n, 0.0)

        # -- apply the residual allocation to the capital accounts -------------
        for n in names:
            capital[n] += book_alloc[n]
        capital_after_allocation = dict(capital)

        # -- 5. distributions --------------------------------------------------
        distributions = {
            n: row.cash_available * ratio.cash.get(n, 0.0) for n in names
        }
        for n in names:
            capital[n] -= distributions[n]

        # -- 6. §752 liability share ------------------------------------------
        # Tier 1 of Treas. Reg. §1.752-3(a): each partner's share of partnership
        # minimum gain. Tier 2 (§704(c) gain) is not modelled - declared. Tier 3:
        # the excess is shared in the partners' profit ratio for the year.
        residual_liability = max(0.0, row.nonrecourse_liability - minimum_gain)
        for n in names:
            liability_share[n] = mg_share[n] + residual_liability * ratio.income.get(
                n, 0.0
            )

        # -- 7. outside basis, §704(d), suspended losses -----------------------
        rows: list[PartnerPeriod] = []
        for n in names:
            b = basis[n]
            b += max(tax_alloc[n], 0.0)
            b += liability_share[n] - opening_liability[n]
            # §50(c)(3) reduces basis, but never below zero.
            b = max(b - itc_reduction[n], 0.0)

            excess_gain = 0.0
            if distributions[n] > b:
                excess_gain = distributions[n] - b
                b = 0.0
            else:
                b -= distributions[n]

            loss_this_year = max(-tax_alloc[n], 0.0)
            # Suspended losses are released first (FIFO) - the convention every
            # partnership tax preparer uses for a §704(d) carryforward.
            freed = min(suspended[n], b)
            b -= freed
            suspended[n] -= freed

            allowed_current = min(loss_this_year, b)
            b -= allowed_current
            newly_suspended = loss_this_year - allowed_current
            suspended[n] += newly_suspended

            basis[n] = b

            rows.append(
                PartnerPeriod(
                    partner=n,
                    period=row.period,
                    year=row.year,
                    capital_opening=opening_capital[n],
                    contributions=contributions[n],
                    book_allocation_base=base_alloc[n],
                    book_reallocation=realloc[n],
                    book_allocation=book_alloc[n] + chargeback_alloc[n],
                    chargeback_income=chargeback_alloc[n],
                    distributions=distributions[n],
                    itc_basis_reduction_share=itc_reduction[n],
                    capital_after_allocation=capital_after_allocation[n],
                    capital_closing=capital[n],
                    dro_cap=dro_cap[n],
                    capital_floor=floors[n],
                    floor_binds=abs(realloc[n]) > CAPITAL_ACCOUNT_TOLERANCE,
                    outside_basis_opening=opening_basis[n],
                    liability_share_opening=opening_liability[n],
                    liability_share_closing=liability_share[n],
                    taxable_allocation=tax_alloc[n],
                    taxable_loss_allowed=allowed_current + freed,
                    taxable_loss_suspended=newly_suspended,
                    suspended_loss_opening=opening_suspended[n],
                    suspended_loss_freed=freed,
                    suspended_loss_closing=suspended[n],
                    outside_basis_closing=basis[n],
                    excess_distribution_gain=excess_gain,
                    credit_allocated=credit_alloc[n],
                    minimum_gain_share=mg_share[n],
                )
            )

        out_periods.append(
            PartnershipPeriod(
                period=row.period,
                year=row.year,
                book_income=row.book_income,
                taxable_income=row.taxable_income,
                credit=row.credit,
                cash_distributed=sum(distributions.values()),
                contributions=sum(contributions.values()),
                minimum_gain=minimum_gain,
                minimum_gain_net_decrease=mg_decrease,
                chargeback_required=chargeback_required,
                chargeback_allocated=chargeback_total,
                chargeback_carryforward=chargeback_carry,
                partners=tuple(rows),
                reallocations=tuple(events),
            )
        )
        prior_minimum_gain = minimum_gain

    # A capital account driven below its floor by *distributions* rather than
    # by an allocation is not an economic-effect failure, but it is a real
    # commercial signal: the LLC agreement would carry a qualified income
    # offset (§1.704-1(b)(2)(ii)(d)), which Structura does not model. Report it.
    breaches: list[CapitalAccountBreach] = []
    for n in names:
        deficits = [
            p.partner(n)
            for p in out_periods
            if p.partner(n).capital_closing
            < p.partner(n).capital_floor - CAPITAL_ACCOUNT_TOLERANCE
        ]
        if deficits and not unlimited[n]:
            worst_row = min(deficits, key=lambda d: d.capital_closing - d.capital_floor)
            worst = worst_row.capital_closing - worst_row.capital_floor
            breaches.append(
                CapitalAccountBreach(
                    partner=n,
                    periods=tuple(d.period for d in deficits),
                    years=tuple(d.year for d in deficits),
                    worst_breach=worst,
                    worst_period=worst_row.period,
                    worst_year=worst_row.year,
                    cause="distributions",
                )
            )
            warnings.append(
                f"'{n}' ends {len(deficits)} period(s) with a §704(b) capital "
                f"account below its floor (worst breach {worst:,.0f}), driven by "
                f"distributions rather than by an allocation. A real LLC "
                f"agreement cures this with a qualified income offset or by "
                f"restricting the distribution; Structura models neither - see "
                f"LIMITS_STRUCTURES.md."
            )

    result = PartnershipResult(
        partners=tuple(partners),
        periods=tuple(out_periods),
        warnings=tuple(warnings),
        capital_account_breaches=tuple(breaches),
    )
    assert_capital_account_integrity(result)
    return result


def assert_capital_account_integrity(result: PartnershipResult) -> None:
    """The invariant a §704(b) ledger cannot be allowed to break.

    Checked **every period**, not just at the end, for every partner and in
    aggregate::

        Σ capital accounts + Σ distributions - Σ contributions
            + Σ ITC basis reductions
            == cumulative book income/loss allocated

    A capital account that does not reconcile to allocations is not a capital
    account; it is a plug. Runs automatically inside :func:`run_partnership`,
    which is why every result returned by this module is already checked.
    """
    names = [p.name for p in result.partners]
    cum_alloc = {n: 0.0 for n in names}
    cum_dist = {n: 0.0 for n in names}
    cum_contrib = {n: 0.0 for n in names}
    cum_itc = {n: 0.0 for n in names}

    for period in result.periods:
        for n in names:
            row = period.partner(n)
            cum_alloc[n] += row.book_allocation
            cum_dist[n] += row.distributions
            cum_contrib[n] += row.contributions
            cum_itc[n] += row.itc_basis_reduction_share

            expected = (
                row.capital_opening
                + row.contributions
                + row.book_allocation
                - row.distributions
                - row.itc_basis_reduction_share
            )
            if abs(row.capital_closing - expected) > CAPITAL_ACCOUNT_TOLERANCE:
                raise AssertionError(
                    f"period {period.period}, partner {n}: capital account "
                    f"{row.capital_closing!r} does not tie to the period "
                    f"identity ({expected!r})"
                )

            reconciled = (
                row.capital_closing + cum_dist[n] - cum_contrib[n] + cum_itc[n]
            )
            if abs(reconciled - cum_alloc[n]) > CAPITAL_ACCOUNT_TOLERANCE:
                raise AssertionError(
                    f"period {period.period}, partner {n}: capital + "
                    f"distributions - contributions + ITC basis reduction "
                    f"({reconciled!r}) does not reconcile to cumulative "
                    f"allocations ({cum_alloc[n]!r})"
                )

            # Economic effect is tested on the **loss allocation**, and only on
            # the loss allocation. A *distribution* that creates a deficit
            # below the floor is a different problem with a different cure (a
            # qualified income offset), and an *income* allocation can only
            # move an account upwards. So the invariant is: a loss allocation
            # may never take an account below its floor, and where the account
            # is already below it - because cash went out - the loss allocation
            # must not move it further down at all.
            terms = next(p for p in result.partners if p.name == n)
            residual_allocation = row.book_allocation - row.chargeback_income
            if (
                not terms.unlimited_dro
                and not terms.bears_residual_allocations
                and residual_allocation < -CAPITAL_ACCOUNT_TOLERANCE
            ):
                before = row.capital_after_allocation - residual_allocation
                limit = min(before, row.capital_floor)
                if row.capital_after_allocation < limit - CAPITAL_ACCOUNT_TOLERANCE:
                    raise AssertionError(
                        f"period {period.period}, partner {n}: a loss "
                        f"allocation took the §704(b) capital account to "
                        f"{row.capital_after_allocation!r}, past its floor "
                        f"{row.capital_floor!r} - the allocation would not "
                        f"have economic effect"
                    )

            if row.outside_basis_closing < -CAPITAL_ACCOUNT_TOLERANCE:
                raise AssertionError(
                    f"period {period.period}, partner {n}: outside basis went "
                    f"negative ({row.outside_basis_closing!r}); §704(d) "
                    f"forbids it"
                )

        total_alloc = sum(period.partner(n).book_allocation for n in names)
        if abs(total_alloc - period.book_income) > CAPITAL_ACCOUNT_TOLERANCE:
            raise AssertionError(
                f"period {period.period}: allocations sum to {total_alloc!r}, "
                f"book income is {period.book_income!r}"
            )
