"""Equipment lease through an owning SPV, with a third-party residual guarantee.

A sixth structure, and the one the AI-compute market is actually using. It is
not a sale-leaseback: nobody sells an asset they already own. A bankruptcy-
remote vehicle is capitalised with tranched debt and a thin equity slice, buys
the equipment new, and leases it to an operator.

Three things make it behave unlike the renewable structures:

**The operator pays rent, not debt service.** There is no borrowing at the
operator, so no debt schedule and no coverage ratio at that level. The rent is
an operating cost, and the assets sit off the operator's balance sheet. What a
lender underwrites is the operator's ability to pay rent plus whatever the
equipment is worth if it stops.

**Credit support is asymmetric.** A manufacturer or other third party
guarantees the residual value of some tranches and not others. The guaranteed
tranches price off the guarantor's credit; the unguaranteed tranche prices off
the equipment. That gap is the whole structure, so the model reports it rather
than blending it away.

**The residual is the credit question.** Debt is repaid from rent during the
term and from the sale of the equipment after it. Where the residual falls
short, the unguaranteed tranche absorbs it first and the guarantor covers the
rest of the guaranteed tranches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from scipy.optimize import brentq

from engine.defaults import CASH_TOLERANCE

__all__ = [
    "EquipmentLeaseConfig",
    "EquipmentLeaseResult",
    "LeaseTranche",
    "PartyLedger",
    "run_equipment_lease",
]


@dataclass(frozen=True, slots=True)
class LeaseTranche:
    """One class of notes issued by the owning vehicle."""

    name: str
    amount: float
    #: All-in annual rate. For a spread quote, add the benchmark before
    #: constructing: the module does not hold a curve.
    rate: float
    #: True where a third party guarantees this tranche against a residual
    #: shortfall.
    guaranteed: bool = False
    #: Issue price as a fraction of par. 0.985 is a 98.5 OID.
    issue_price: float = 1.0

    def __post_init__(self) -> None:
        if self.amount <= 0.0:
            raise ValueError(f"{self.name}: amount must be > 0")
        if not 0.0 < self.issue_price <= 1.0:
            raise ValueError(f"{self.name}: issue_price must lie in (0, 1]")

    @property
    def proceeds(self) -> float:
        """Cash raised, which is below par where the notes are issued at a discount."""
        return self.amount * self.issue_price


@dataclass(frozen=True, slots=True)
class EquipmentLeaseConfig:
    tranches: tuple[LeaseTranche, ...]
    equity: float
    asset_cost: float
    lease_term_years: float
    #: Residual value the notes were sized against, as a fraction of original
    #: cost. The balloon left outstanding at term end is set from this.
    expected_residual_pct: float
    #: Straight-line tax life of the equipment inside the vehicle.
    tax_life_years: float
    #: Residual actually realised on sale. Defaults to the expected figure;
    #: setting it lower is the residual stress the guarantee exists for, and
    #: it is where the difference between the guaranteed and unguaranteed
    #: tranches becomes visible.
    realised_residual_pct: float | None = None
    tax_rate: float = 0.21
    guarantor_name: str = "Guarantor"
    lessee_name: str = "Lessee"
    #: Target after-tax return on the vehicle's equity. Rent is solved to it.
    equity_target_after_tax_irr: float = 0.12

    def __post_init__(self) -> None:
        if not self.tranches:
            raise ValueError("an equipment lease needs at least one tranche")
        if self.lease_term_years <= 0.0:
            raise ValueError("lease_term_years must be > 0")
        if not 0.0 <= self.expected_residual_pct <= 1.0:
            raise ValueError("expected_residual_pct must lie in [0, 1]")
        if self.realised_residual_pct is not None and not (
            0.0 <= self.realised_residual_pct <= 1.0
        ):
            raise ValueError("realised_residual_pct must lie in [0, 1]")
        if self.tax_life_years <= 0.0:
            raise ValueError("tax_life_years must be > 0")

    @property
    def debt(self) -> float:
        return sum(t.amount for t in self.tranches)

    @property
    def proceeds(self) -> float:
        return sum(t.proceeds for t in self.tranches)

    @property
    def sources(self) -> float:
        return self.proceeds + self.equity

    @property
    def guaranteed_amount(self) -> float:
        return sum(t.amount for t in self.tranches if t.guaranteed)

    @property
    def unguaranteed_amount(self) -> float:
        return sum(t.amount for t in self.tranches if not t.guaranteed)

    @property
    def years(self) -> int:
        return int(round(self.lease_term_years))

    @property
    def realised_residual(self) -> float:
        pct = (
            self.realised_residual_pct
            if self.realised_residual_pct is not None
            else self.expected_residual_pct
        )
        return self.asset_cost * pct

    @property
    def balloon(self) -> float:
        """Principal deliberately left to be repaid from the residual sale."""
        return min(self.debt, self.asset_cost * self.expected_residual_pct)


@dataclass(frozen=True, slots=True)
class PartyLedger:
    """One party's cash flows, index 0 at closing."""

    party: str
    role: str
    cashflow: tuple[float, ...]

    @property
    def total(self) -> float:
        return sum(self.cashflow)


@dataclass(frozen=True, slots=True)
class EquipmentLeaseResult:
    config: EquipmentLeaseConfig
    annual_rent: float
    ledgers: tuple[PartyLedger, ...]
    residual_proceeds: float
    residual_shortfall: float
    guarantor_payment: float
    unguaranteed_loss: float
    notes: tuple[str, ...] = field(default_factory=tuple)

    def ledger(self, party: str) -> PartyLedger:
        for entry in self.ledgers:
            if entry.party == party:
                return entry
        raise KeyError(party)

    def reconciliation(self) -> tuple[float, ...]:
        """Net cash across every party, period by period.

        Every dollar leaving one party enters another. A non-zero entry here
        means the structure is inventing or destroying cash.
        """
        length = max(len(entry.cashflow) for entry in self.ledgers)
        out = []
        for i in range(length):
            out.append(
                sum(
                    entry.cashflow[i] if i < len(entry.cashflow) else 0.0
                    for entry in self.ledgers
                )
            )
        return tuple(out)

    def guarantee_asymmetry(self) -> str:
        """Say plainly which tranches are covered and which are not."""
        cfg = self.config
        covered = [t.name for t in cfg.tranches if t.guaranteed]
        exposed = [t.name for t in cfg.tranches if not t.guaranteed]
        if not covered:
            return "No tranche carries a residual value guarantee."
        if not exposed:
            return (
                f"{cfg.guarantor_name} guarantees every tranche "
                f"(${cfg.guaranteed_amount / 1e9:,.1f}bn)."
            )
        return (
            f"{cfg.guarantor_name} guarantees {' and '.join(covered)} "
            f"(${cfg.guaranteed_amount / 1e9:,.1f}bn) against a residual "
            f"shortfall. {' and '.join(exposed)} "
            f"(${cfg.unguaranteed_amount / 1e9:,.1f}bn) is unguaranteed and "
            "absorbs a shortfall first, which is why it prices off the "
            "equipment rather than off the guarantor."
        )


# ---------------------------------------------------------------------------


def run_equipment_lease(config: EquipmentLeaseConfig) -> EquipmentLeaseResult:
    """Solve the rent, then walk every party's cash."""
    rent = _solve_rent(config)
    return _build(config, rent)


def _solve_rent(config: EquipmentLeaseConfig) -> float:
    """Level annual rent that returns the vehicle's equity at its target."""

    def gap(rent: float) -> float:
        result = _build(config, rent)
        equity = result.ledger("SPV equity").cashflow
        return _npv(equity, config.equity_target_after_tax_irr)

    lo = 0.0
    hi = max(config.asset_cost, 1.0)
    # Rent scales the equity return monotonically, so a widening bracket finds
    # a sign change whenever one exists.
    for _ in range(60):
        if gap(hi) > 0.0:
            break
        hi *= 1.6
    else:  # pragma: no cover - defensive
        raise RuntimeError("no rent clears the equity target")
    return brentq(gap, lo, hi, xtol=1e-6, rtol=1e-12, maxiter=200)


def _build(config: EquipmentLeaseConfig, rent: float) -> EquipmentLeaseResult:
    years = config.years
    n = years + 1

    # -- the vehicle's debt -------------------------------------------------
    #
    # Rent amortises the notes down to a balloon sized on the residual the
    # deal was underwritten against. The balloon is repaid from the sale of
    # the equipment, which is what makes the residual the credit question
    # rather than a footnote.

    amortising = max(0.0, config.debt - config.balloon)
    annual_principal = amortising / years if years else 0.0

    balance = [0.0] * n
    interest = [0.0] * n
    principal = [0.0] * n
    balance[0] = config.debt
    blended_rate = (
        sum(t.amount * t.rate for t in config.tranches) / config.debt
        if config.debt
        else 0.0
    )
    for year in range(1, years + 1):
        interest[year] = balance[year - 1] * blended_rate
        principal[year] = annual_principal
        balance[year] = balance[year - 1] - annual_principal

    # -- residual, and who absorbs a miss -----------------------------------

    residual = config.realised_residual
    outstanding = balance[years]
    shortfall = max(0.0, outstanding - residual)

    unguaranteed_amount = config.unguaranteed_amount
    unguaranteed_share = (
        unguaranteed_amount / config.debt if config.debt else 0.0
    )
    unguaranteed_outstanding = outstanding * unguaranteed_share
    unguaranteed_loss = min(shortfall, unguaranteed_outstanding)
    guarantor_payment = shortfall - unguaranteed_loss

    # -- vehicle tax --------------------------------------------------------

    depreciation = config.asset_cost / config.tax_life_years
    tax = [0.0] * n
    for year in range(1, years + 1):
        charge = depreciation if year <= config.tax_life_years else 0.0
        tax[year] = (rent - interest[year] - charge) * config.tax_rate

    # -- ledgers ------------------------------------------------------------

    ledgers: list[PartyLedger] = []

    lessee = [0.0] * n
    for year in range(1, years + 1):
        lessee[year] = -rent
    ledgers.append(
        PartyLedger(
            config.lessee_name, "lessee (rent, not debt service)", tuple(lessee)
        )
    )

    for t in config.tranches:
        share = t.amount / config.debt if config.debt else 0.0
        flow = [0.0] * n
        flow[0] = -t.proceeds
        for year in range(1, years + 1):
            flow[year] = interest[year] * share + principal[year] * share
        repaid = outstanding * share
        if not t.guaranteed and unguaranteed_amount:
            repaid -= unguaranteed_loss * (t.amount / unguaranteed_amount)
        flow[years] += repaid
        ledgers.append(PartyLedger(t.name, "noteholder", tuple(flow)))

    guarantor = [0.0] * n
    guarantor[years] = -guarantor_payment
    ledgers.append(
        PartyLedger(
            config.guarantor_name, "residual value guarantor", tuple(guarantor)
        )
    )

    equity = [0.0] * n
    equity[0] = -config.equity
    for year in range(1, years + 1):
        equity[year] = rent - interest[year] - principal[year] - tax[year]
    equity[years] += residual + guarantor_payment + unguaranteed_loss - outstanding
    ledgers.append(PartyLedger("SPV equity", "vehicle sponsor", tuple(equity)))

    # The vendor sells the equipment at closing, the tax authority collects
    # each year, and a buyer takes the residual at term end. All three sit
    # outside the structure, so they are recorded to close the reconciliation
    # rather than analysed.
    external = [0.0] * n
    external[0] = config.asset_cost
    for year in range(1, years + 1):
        external[year] += tax[year]
    external[years] -= residual
    ledgers.append(
        PartyLedger(
            "External", "vendor, tax authority, residual buyer", tuple(external)
        )
    )

    notes = []
    if shortfall > CASH_TOLERANCE:
        notes.append(
            f"Realised residual of ${residual / 1e9:,.2f}bn falls "
            f"${shortfall / 1e9:,.2f}bn short of the ${outstanding / 1e9:,.2f}bn "
            f"balloon. {config.guarantor_name} covers "
            f"${guarantor_payment / 1e9:,.2f}bn; the unguaranteed notes absorb "
            f"${unguaranteed_loss / 1e9:,.2f}bn."
        )
    if abs(config.sources - config.asset_cost) > CASH_TOLERANCE:
        notes.append(
            f"Sources of ${config.sources / 1e9:,.2f}bn do not equal the "
            f"${config.asset_cost / 1e9:,.2f}bn asset cost."
        )

    return EquipmentLeaseResult(
        config=config,
        annual_rent=rent,
        ledgers=tuple(ledgers),
        residual_proceeds=residual,
        residual_shortfall=shortfall,
        guarantor_payment=guarantor_payment,
        unguaranteed_loss=unguaranteed_loss,
        notes=tuple(notes),
    )


def _npv(series: tuple[float, ...] | list[float], rate: float) -> float:
    return sum(value / (1.0 + rate) ** i for i, value in enumerate(series))


def iter_party_names(result: EquipmentLeaseResult) -> Iterator[str]:
    for entry in result.ledgers:
        yield entry.party
