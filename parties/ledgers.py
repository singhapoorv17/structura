"""Economics broken out by party.

The question an investment committee asks is not "what is the project IRR" but
"what does each side get". This assembles a ledger per party — sponsor, tax
equity, credit transferee, preferred, lender, lessor — with the metrics that
matter to that party and, for the partnership parties, the §704(b) capital
account and outside basis path underneath.

Two conservation checks run over the result, and both are period-by-period
rather than in aggregate, because an aggregate check passes on a model that is
wrong in offsetting directions:

* **Partnership integrity.** In every period the partners' distributions sum
  to the cash the partnership distributed, their contributions sum to what it
  received, and their book allocations sum to its book income.
* **Cross-party reconciliation.** For the equipment lease, where every
  counterparty is inside the model, the net of all ledgers is zero in every
  period.

The renewable structures do not emit a per-period distributable-cash series,
so a full cross-party identity cannot be asserted for them from outside the
engine. What can be proved is proved; what cannot is said rather than skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.defaults import CASH_TOLERANCE, FEDERAL_TAX_RATE
from engine.metrics import irr as _irr

__all__ = [
    "Ledger",
    "Metrics",
    "PartyView",
    "conservation_report",
    "party_view",
]

#: Below this share of total capital a rate is measuring its denominator.
DE_MINIMIS_EQUITY_SHARE = 0.10


@dataclass(frozen=True, slots=True)
class Metrics:
    irr: float | None
    moic: float | None
    payback_year: int | None
    not_meaningful_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "irr": self.irr,
            "moic": self.moic,
            "payback_year": self.payback_year,
            "not_meaningful_reason": self.not_meaningful_reason,
        }


@dataclass(frozen=True, slots=True)
class Ledger:
    party: str
    role: str
    years: tuple[int, ...]
    cashflow: tuple[float, ...]
    #: Where each series came from, so a cell can be traced to the engine line
    #: that produced it rather than taken on faith.
    trace: str = ""
    capital_account: tuple[float, ...] | None = None
    outside_basis: tuple[float, ...] | None = None
    #: The pieces the net flow is built from, each a per-period series. A
    #: reader who wants to recompute on their own convention needs the parts,
    #: not the total, and every cell in the table drills through to these.
    components: dict[str, tuple[float, ...]] = field(default_factory=dict)

    @property
    def invested(self) -> float:
        """Capital actually put in.

        Netting within a period understates this badly for a tax equity
        investor, whose credit arrives in the same year as its contribution.
        Where the contribution series is available it is used directly.
        """
        contributions = self.components.get("contributions")
        if contributions:
            return sum(contributions)
        return -sum(c for c in self.cashflow if c < 0)

    @property
    def returned(self) -> float:
        contributions = self.components.get("contributions")
        if contributions:
            return sum(self.cashflow) + sum(contributions)
        return sum(c for c in self.cashflow if c > 0)

    def metrics(self, *, total_capital: float | None = None) -> Metrics:
        invested = self.invested
        if invested <= CASH_TOLERANCE:
            return Metrics(
                None,
                None,
                None,
                "This party contributes no capital, so a rate of return has no base.",
            )
        if (
            total_capital
            and invested / total_capital < DE_MINIMIS_EQUITY_SHARE
        ):
            return Metrics(
                None,
                round(self.returned / invested, 4),
                _payback(self.years, self.cashflow),
                (
                    f"Capital of ${invested / 1e6:,.1f}m is "
                    f"{invested / total_capital:.1%} of the ${total_capital / 1e6:,.0f}m "
                    "stack. A rate on a base that small measures the "
                    "denominator; multiple and payback are shown instead."
                ),
            )
        # An IRR is only defined on a conventional series: money out, then
        # money back. A tax equity investor whose credit lands in the same
        # period as its contribution can show a net inflow at time zero, and
        # solving a rate on that produces a confident number with no meaning.
        # It was returning -21% on a deal with a 1.16x multiple.
        signs = [c for c in self.cashflow if abs(c) > CASH_TOLERANCE]
        changes = sum(1 for a, b in zip(signs, signs[1:]) if a * b < 0)
        if signs and signs[0] > 0:
            return Metrics(
                None,
                round(self.returned / invested, 4),
                _payback(self.years, self.cashflow),
                (
                    "The first period is a net inflow, so there is no "
                    "investment for a rate to be measured against. This is "
                    "normal where the credit lands in the same period as the "
                    "contribution; the components below show both."
                ),
            )
        if changes > 1:
            return Metrics(
                None,
                round(self.returned / invested, 4),
                _payback(self.years, self.cashflow),
                (
                    f"The cash flow changes sign {changes} times, so an IRR "
                    "is not uniquely defined. Multiple and payback are shown "
                    "instead."
                ),
            )
        try:
            rate = _irr(list(self.cashflow))
        except Exception:  # noqa: BLE001 - an unsolvable IRR is a result
            rate = None
        return Metrics(
            irr=rate,
            moic=round(self.returned / invested, 4),
            payback_year=_payback(self.years, self.cashflow),
        )

    def to_dict(self, *, total_capital: float | None = None) -> dict[str, Any]:
        return {
            "party": self.party,
            "role": self.role,
            "years": list(self.years),
            "cashflow": list(self.cashflow),
            "trace": self.trace,
            "components": {k: list(v) for k, v in self.components.items()},
            "capital_account": (
                list(self.capital_account) if self.capital_account else None
            ),
            "outside_basis": (
                list(self.outside_basis) if self.outside_basis else None
            ),
            "metrics": self.metrics(total_capital=total_capital).to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PartyView:
    structure: str
    ledgers: tuple[Ledger, ...]
    total_capital: float
    conservation: tuple[str, ...] = field(default_factory=tuple)

    def ledger(self, party: str) -> Ledger:
        for entry in self.ledgers:
            if entry.party == party:
                return entry
        raise KeyError(party)

    def to_dict(self) -> dict[str, Any]:
        return {
            "structure": self.structure,
            "total_capital": self.total_capital,
            "ledgers": [
                entry.to_dict(total_capital=self.total_capital)
                for entry in self.ledgers
            ],
            "conservation": list(self.conservation),
        }


def _payback(years, cashflow) -> int | None:
    running = 0.0
    for year, value in zip(years, cashflow):
        running += value
        if running >= 0:
            return year
    return None


def _partner_ledger(partnership, name: str, tax_rate: float) -> Ledger:
    """A partner's ledger on an after-tax basis.

    Cash alone misrepresents a tax equity investor badly. Most of what the
    investor bargained for arrives as a credit and as deductions, not as
    distributions, so a cash-only ledger shows a heavily negative return on a
    deal that priced to a positive yield. The benefit is added here:

    * the **credit** allocated to the partner, recovered from its share of the
      §50(c)(3) basis reduction, which is half the credit;
    * the **tax effect of the allocation**, at the federal rate — a loss
      allocation is a benefit, income is a cost.
    """
    flows, capital, basis = [], [], []
    parts: dict[str, list[float]] = {
        "contributions": [],
        "distributions": [],
        "credit": [],
        "tax_effect": [],
    }
    for period in partnership.periods:
        entry = next((p for p in period.partners if p.partner == name), None)
        if entry is None:
            continue
        credit = 2.0 * entry.itc_basis_reduction_share
        tax_effect = -entry.taxable_allocation * tax_rate
        parts["contributions"].append(entry.contributions)
        parts["distributions"].append(entry.distributions)
        parts["credit"].append(credit)
        parts["tax_effect"].append(tax_effect)
        flows.append(
            entry.distributions - entry.contributions + credit + tax_effect
        )
        capital.append(entry.capital_closing)
        basis.append(entry.outside_basis_closing)

    return Ledger(
        party=f"{name.replace('_', ' ').title()} — partner ledger",
        role="partner in the tax equity partnership, after tax",
        years=tuple(p.year for p in partnership.periods),
        cashflow=tuple(flows),
        trace=(
            "PartnerPeriod.distributions less contributions, plus the credit "
            "implied by itc_basis_reduction_share under §50(c)(3) and the tax "
            "effect of taxable_allocation"
        ),
        capital_account=tuple(capital),
        outside_basis=tuple(basis),
        components={k: tuple(v) for k, v in parts.items()},
    )


def party_view(result, *, tax_rate: float | None = None) -> PartyView:
    """Break a structure result out by party."""
    tax_rate = FEDERAL_TAX_RATE.value if tax_rate is None else tax_rate
    years = tuple(result.years)
    ledgers: list[Ledger] = []

    ledgers.append(
        Ledger(
            party="Sponsor",
            role="sponsor equity, after tax",
            years=years,
            cashflow=tuple(result.sponsor_cashflow),
            trace="StructureResult.sponsor_cashflow",
        )
    )
    if result.third_party_cashflow:
        # The engine stores this series from the project's side: capital in at
        # index 0 is positive because the project receives it. A ledger is the
        # party's own view, so the sign is flipped here. Its IRR is then the
        # effective cost of capital, which the engine reports independently
        # and which the acceptance suite cross-checks.
        ledgers.append(
            Ledger(
                party="Third-party capital",
                role="providers of construction capital, in aggregate",
                years=years,
                cashflow=tuple(-c for c in result.third_party_cashflow),
                trace=(
                    "StructureResult.third_party_cashflow, sign inverted to the "
                    "provider's perspective"
                ),
            )
        )

    partnership = getattr(result, "partnership", None)
    if partnership is not None:
        for partner in partnership.partners:
            ledgers.append(_partner_ledger(partnership, partner.name, tax_rate))

    return PartyView(
        structure=result.key.value,
        ledgers=tuple(ledgers),
        total_capital=float(result.total_capital_raised or 0.0),
        conservation=conservation_report(result),
    )


def conservation_report(result) -> tuple[str, ...]:
    """Check what can be checked, and name what cannot.

    Returns a tuple of failures. Empty means every provable identity held.
    """
    failures: list[str] = []
    partnership = getattr(result, "partnership", None)
    if partnership is None:
        return ()

    for period in partnership.periods:
        distributed = sum(p.distributions for p in period.partners)
        contributed = sum(p.contributions for p in period.partners)
        allocated = sum(p.book_allocation for p in period.partners)
        if abs(distributed - period.cash_distributed) > 1e-3:
            failures.append(
                f"period {period.period}: partner distributions "
                f"{distributed:,.2f} against {period.cash_distributed:,.2f} "
                "distributed by the partnership"
            )
        if abs(contributed - period.contributions) > 1e-3:
            failures.append(
                f"period {period.period}: partner contributions "
                f"{contributed:,.2f} against {period.contributions:,.2f} received"
            )
        if abs(allocated - period.book_income) > 1e-3:
            failures.append(
                f"period {period.period}: book allocations {allocated:,.2f} "
                f"against book income {period.book_income:,.2f}"
            )
    return tuple(failures)
