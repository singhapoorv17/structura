"""The qualitative matrix — how the structures differ where numbers don't reach.

Ten dimensions, six structures, sixty cells. Every cell carries a rule id and a
one-line reason, because a pros-and-cons table with no reasoning behind it is
just an opinion in a grid.

Ratings run 1 to 5 and always point the same way: **higher is better for the
sponsor**. So a 5 on ``execution_complexity`` means simple to execute, not
complex. Keeping the polarity uniform is what lets the ranking add them up
without a sign table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from engine.structures.models import StructureKey

__all__ = ["DIMENSIONS", "Cell", "cell", "matrix_for"]

K = StructureKey


@dataclass(frozen=True, slots=True)
class Dimension:
    id: str
    label: str
    question: str


DIMENSIONS: Final[tuple[Dimension, ...]] = (
    Dimension("execution_complexity", "Execution complexity", "How hard is it to close?"),
    Dimension("time_to_close", "Time to close", "How long from term sheet to funding?"),
    Dimension("counterparty_depth", "Counterparty depth", "How many parties will actually do this?"),
    Dimension("documentation_burden", "Documentation burden", "How much paper?"),
    Dimension("recapture_exposure", "Recapture exposure", "What happens if the asset is disposed of or fails?"),
    Dimension("exit_flexibility", "Exit and transferability", "Can the sponsor sell out cleanly?"),
    Dimension("accounting_treatment", "Accounting treatment", "How does it present on the balance sheet?"),
    Dimension("covenant_burden", "Covenant intrusiveness", "How much control does the sponsor give up?"),
    Dimension("tax_law_sensitivity", "Sensitivity to tax law change", "What breaks if the rules move?"),
    Dimension("optionality", "Optionality preserved", "What can the sponsor still do afterwards?"),
)


@dataclass(frozen=True, slots=True)
class Cell:
    structure: StructureKey
    dimension: str
    rating: int
    reason: str
    rule_id: str

    def __post_init__(self) -> None:
        if not 1 <= self.rating <= 5:
            raise ValueError(f"{self.rule_id}: rating must lie in 1..5")
        if not self.reason.strip():
            raise ValueError(f"{self.rule_id}: a cell without a reason cannot render")

    def to_dict(self) -> dict:
        return {
            "structure": self.structure.value,
            "dimension": self.dimension,
            "rating": self.rating,
            "reason": self.reason,
            "rule_id": self.rule_id,
        }


def _c(structure, dimension, rating, reason) -> Cell:
    return Cell(
        structure=structure,
        dimension=dimension,
        rating=rating,
        reason=reason,
        rule_id=f"{structure.value}.{dimension}",
    )


MATRIX: Final[tuple[Cell, ...]] = (
    # -- partnership flip ---------------------------------------------------
    _c(K.PARTNERSHIP_FLIP, "execution_complexity", 2, "Capital accounts, DRO caps and a flip solve; the most demanding of the renewable set to close correctly."),
    _c(K.PARTNERSHIP_FLIP, "time_to_close", 2, "Tax equity diligence and negotiation typically run months, not weeks."),
    _c(K.PARTNERSHIP_FLIP, "counterparty_depth", 2, "A short list of banks and insurers, and each has a minimum ticket."),
    _c(K.PARTNERSHIP_FLIP, "documentation_burden", 2, "An LLC agreement with allocation mechanics, plus a tax opinion."),
    _c(K.PARTNERSHIP_FLIP, "recapture_exposure", 2, "The investor stays in the partnership through the five-year ITC recapture period."),
    _c(K.PARTNERSHIP_FLIP, "exit_flexibility", 2, "The sponsor cannot sell cleanly before the flip without the investor's consent."),
    _c(K.PARTNERSHIP_FLIP, "accounting_treatment", 3, "HLBV is standard but adds reporting the sponsor may not otherwise carry."),
    _c(K.PARTNERSHIP_FLIP, "covenant_burden", 2, "The investor holds consent rights over major decisions until the flip."),
    _c(K.PARTNERSHIP_FLIP, "tax_law_sensitivity", 2, "Allocation and recapture mechanics sit directly on the rules that keep moving."),
    _c(K.PARTNERSHIP_FLIP, "optionality", 3, "Post-flip the sponsor regains most of the economics and control."),
    # -- T-flip -------------------------------------------------------------
    _c(K.T_FLIP, "execution_complexity", 2, "A flip plus a transfer: everything the flip requires, and a credit sale on top."),
    _c(K.T_FLIP, "time_to_close", 3, "The transfer leg closes faster than pure tax equity and can be run in parallel."),
    _c(K.T_FLIP, "counterparty_depth", 4, "The transfer leg reaches ordinary corporate buyers, which widens the pool considerably."),
    _c(K.T_FLIP, "documentation_burden", 2, "Partnership documents and a transfer agreement, with indemnities on both."),
    _c(K.T_FLIP, "recapture_exposure", 2, "Recapture risk is split between the partnership and the transferee, which complicates the indemnity."),
    _c(K.T_FLIP, "exit_flexibility", 3, "Selling the credits early removes one constraint on the sponsor's later exit."),
    _c(K.T_FLIP, "accounting_treatment", 3, "Two monetisation routes to present rather than one."),
    _c(K.T_FLIP, "covenant_burden", 2, "Investor consent rights persist alongside transferee covenants."),
    _c(K.T_FLIP, "tax_law_sensitivity", 2, "Exposed on both legs: allocation rules and the transfer regime."),
    _c(K.T_FLIP, "optionality", 4, "Splitting the credit from the depreciation lets each be placed with whoever values it most."),
    # -- preferred equity ---------------------------------------------------
    _c(K.PREFERRED_EQUITY, "execution_complexity", 3, "A priority return and a redemption schedule; simpler than a flip, harder than a loan."),
    _c(K.PREFERRED_EQUITY, "time_to_close", 3, "Faster than tax equity, slower than a straight credit sale."),
    _c(K.PREFERRED_EQUITY, "counterparty_depth", 3, "Infrastructure funds and credit funds, not only tax equity desks."),
    _c(K.PREFERRED_EQUITY, "documentation_burden", 3, "One instrument with a defined return, rather than allocation mechanics."),
    _c(K.PREFERRED_EQUITY, "recapture_exposure", 3, "Less exposed than a flip where the preferred does not take the credit."),
    _c(K.PREFERRED_EQUITY, "exit_flexibility", 3, "Redemption gives a defined exit date the sponsor can plan around."),
    _c(K.PREFERRED_EQUITY, "accounting_treatment", 3, "Classification between debt and equity depends on the redemption terms."),
    _c(K.PREFERRED_EQUITY, "covenant_burden", 3, "Protective rather than participating rights in most cases."),
    _c(K.PREFERRED_EQUITY, "tax_law_sensitivity", 4, "The priority return does not depend on the credit surviving."),
    _c(K.PREFERRED_EQUITY, "optionality", 3, "Redemption clears the capital stack for a later refinancing."),
    # -- direct transfer ----------------------------------------------------
    _c(K.DIRECT_TRANSFER, "execution_complexity", 5, "A sale of a credit. No partnership, no allocations, no flip."),
    _c(K.DIRECT_TRANSFER, "time_to_close", 5, "Weeks rather than months once the credit is determined."),
    _c(K.DIRECT_TRANSFER, "counterparty_depth", 5, "Any corporate with tax capacity is a potential buyer."),
    _c(K.DIRECT_TRANSFER, "documentation_burden", 5, "A transfer agreement and an indemnity, and little else."),
    _c(K.DIRECT_TRANSFER, "recapture_exposure", 2, "Recapture sits with the transferee, so the indemnity the buyer demands is heavy."),
    _c(K.DIRECT_TRANSFER, "exit_flexibility", 5, "Nothing about the sale constrains the sponsor's later disposal."),
    _c(K.DIRECT_TRANSFER, "accounting_treatment", 4, "A single receipt against the credit, straightforward to present."),
    _c(K.DIRECT_TRANSFER, "covenant_burden", 5, "The buyer takes a credit, not a governance position."),
    _c(K.DIRECT_TRANSFER, "tax_law_sensitivity", 3, "Depends on the transfer regime surviving, but on nothing else."),
    _c(K.DIRECT_TRANSFER, "optionality", 4, "Leaves depreciation with the sponsor to place separately."),
    # -- sale-leaseback -----------------------------------------------------
    _c(K.SALE_LEASEBACK, "execution_complexity", 3, "A sale, a lease and a true-lease opinion, within the three-month window."),
    _c(K.SALE_LEASEBACK, "time_to_close", 3, "Constrained by the §50(d)(4) window rather than by negotiation."),
    _c(K.SALE_LEASEBACK, "counterparty_depth", 2, "A narrow set of lessors, and pricing is not published anywhere."),
    _c(K.SALE_LEASEBACK, "documentation_burden", 3, "Sale documents, a lease, and a true-lease analysis."),
    _c(K.SALE_LEASEBACK, "recapture_exposure", 3, "The lessor holds the credit and the recapture risk with it."),
    _c(K.SALE_LEASEBACK, "exit_flexibility", 2, "The sponsor no longer owns the asset; exit runs through the lease."),
    _c(K.SALE_LEASEBACK, "accounting_treatment", 2, "The asset leaves the balance sheet and a lease liability arrives."),
    _c(K.SALE_LEASEBACK, "covenant_burden", 2, "Lease covenants bind operations for the whole term."),
    _c(K.SALE_LEASEBACK, "tax_law_sensitivity", 3, "The true-lease tests are long-settled, though the credit itself is not."),
    _c(K.SALE_LEASEBACK, "optionality", 2, "A purchase option at the end, and little flexibility before it."),
    # -- equipment lease ----------------------------------------------------
    _c(K.EQUIPMENT_LEASE, "execution_complexity", 2, "A bankruptcy-remote vehicle, tranched notes and a third-party guarantee to negotiate."),
    _c(K.EQUIPMENT_LEASE, "time_to_close", 2, "Rated or privately placed notes take a full syndication cycle."),
    _c(K.EQUIPMENT_LEASE, "counterparty_depth", 3, "Private credit and asset-backed investors, reachable but concentrated."),
    _c(K.EQUIPMENT_LEASE, "documentation_burden", 2, "Vehicle formation, an indenture, a lease and a guarantee."),
    _c(K.EQUIPMENT_LEASE, "recapture_exposure", 5, "No tax credit is involved, so there is nothing to recapture."),
    _c(K.EQUIPMENT_LEASE, "exit_flexibility", 4, "The operator never owned the equipment and can walk at the end of the term."),
    _c(K.EQUIPMENT_LEASE, "accounting_treatment", 5, "The assets sit off the operator's balance sheet and rent is an operating cost."),
    _c(K.EQUIPMENT_LEASE, "covenant_burden", 3, "Lease covenants bind the operator, but there is no project-level debt package."),
    _c(K.EQUIPMENT_LEASE, "tax_law_sensitivity", 5, "The structure does not depend on any credit regime."),
    _c(K.EQUIPMENT_LEASE, "optionality", 3, "Renewal or return at term end; the residual belongs to the vehicle."),
)

BY_STRUCTURE: Final[dict[StructureKey, dict[str, Cell]]] = {}
for _cell in MATRIX:
    BY_STRUCTURE.setdefault(_cell.structure, {})[_cell.dimension] = _cell


def cell(structure: StructureKey, dimension: str) -> Cell:
    return BY_STRUCTURE[structure][dimension]


def matrix_for(structures) -> tuple[Cell, ...]:
    return tuple(
        BY_STRUCTURE[s][d.id] for s in structures for d in DIMENSIONS
    )
