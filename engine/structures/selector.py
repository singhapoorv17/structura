"""The structure selector — run one project through all five structures.

Model all five live 2026 structures against the *same* project and return a
ranked comparison of sponsor
after-tax IRR, effective cost of capital and cash timing. Jack Cargas of BofA,
quoted in Norton Rose Fulbright's *Cost of Capital: 2026 Outlook*: *"it feels
like there are now 31 different flavors."* That is the decision the market now
agonises over, and no free tool addresses it.

What "same project" means here
------------------------------
The debt is sized and sculpted **once**, the waterfall is run **once**, and the
credit determination is made **once**, in :func:`engine.structures.build_context`.
All five structures then sit on top of identical project economics. Re-sizing
the debt per structure would make the comparison meaningless.

Ranking, and why it is boring on purpose
----------------------------------------
Ranking is **deterministic and explainable**. There is no scoring function, no
weighting, and no judgement call hidden in a constant:

1. **Sponsor after-tax IRR, descending** — the primary metric — but only
   where that rate is *meaningful*.
2. Structures whose IRR is **not meaningful** rank after those whose IRR is,
   ordered by sponsor NPV at the stated discount rate. A rate is not meaningful
   where no net sponsor investment exists, where the equity base is de minimis,
   where the whole investment returns inside a year, or where the rate is
   outside anything a project-finance structure produces. The test lives in
   :func:`engine.structures.models.irr_meaningfulness` and every structure
   carries the verdict and its reason.
3. **Infeasible structures rank last**, ordered by name, each carrying the rule
   or fact that blocked it.

Why step 2 exists
-----------------
IRR is a rate *on an equity base*. A structure that leaves the sponsor $2m in a
$200m project and hands it 5% of the cash reports a three-figure IRR while
earning almost nothing, and it will out-rank a structure returning a genuine
12%. Real sponsor equity IRRs in contracted US renewables and storage run
roughly **8-15% levered after tax**; a comparison that leads with 163% is not
wrong by a little, it is measuring the denominator. So the selector detects the
condition, refuses to lead with the number, and ranks on **sponsor NPV** with
the **effective cost of capital** displayed alongside as the cross-check.

Ties — two IRRs within :data:`RANKING_TOLERANCE` — break through a fixed,
published chain, and every break that actually fires is recorded in
:attr:`WhyThisWins.tie_breaks` so a reader can see it happened:

* lower **effective cost of capital**;
* **earlier cash** (lower cash-weighted average years to receipt);
* lower **sponsor equity required**;
* finally the structure key, alphabetically, so the result is reproducible.

The hard gate
-------------
A project that **fails the FEOC / Material Assistance Cost Ratio test has no
credit at all** (``engine.tax.feoc`` returns ``passes=False`` and
``evaluate_eligibility`` converts that into a zero credit). A credit-dependent
structure — a direct transfer, or a T-flip, which is *defined* by its transfer
leg — cannot then be ranked first, or at all. The selector enforces that
independently of the individual structure modules, because it is the kind of
result that must not depend on one module remembering to check.

The output is facts, not prose
------------------------------
:class:`WhyThisWins` is a structured comparison keyed to the numbers. The
narrator renders it; it never computes and never overrides.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from engine import DebtTerms, ProjectInputs
from engine.tax import LAW_VERIFIED_ON, TaxProject, TaxScenario
from engine.structures.defaults import RANKING_TOLERANCE
from engine.structures.flip import run_flip
from engine.structures.models import (
    RiskFlag,
    RiskSeverity,
    SponsorTaxProfile,
    StructureConfigs,
    StructureContext,
    StructureKey,
    StructureResult,
    build_context,
)
from engine.structures.partnership import CapitalAccountBreach
from engine.structures.preferred import run_preferred
from engine.structures.sale_leaseback import run_sale_leaseback
from engine.structures.tflip import run_tflip
from engine.structures.transfer import run_transfer

__all__ = [
    "Driver",
    "WhyThisWins",
    "RankedStructure",
    "StructureComparison",
    "run_all_structures",
    "compare_structures",
]

#: Ordered tie-break chain. Each entry is (label, key function, "lower is
#: better"). Published as data so the README and the tests can both point at
#: the same object rather than restating it.
_TIE_BREAKS: tuple[tuple[str, str, bool], ...] = (
    ("effective cost of capital", "effective_cost_of_capital", True),
    ("earlier sponsor cash", "cash_weighted_average_years", True),
    ("lower sponsor equity required", "sponsor_equity_required", True),
    ("structure key, alphabetically", "key_value", True),
)


@dataclass(frozen=True, slots=True)
class Driver:
    """One numeric reason the winner won, stated as a comparison."""

    name: str
    unit: str
    winner_value: float | None
    runner_up_value: float | None
    delta: float | None
    higher_is_better: bool
    note: str


@dataclass(frozen=True, slots=True)
class WhyThisWins:
    """The structured explanation. Numbers only — the narrator adds the prose."""

    winner: StructureKey
    primary_metric: str
    winner_value: float | None
    runner_up: StructureKey | None
    runner_up_value: float | None
    margin: float | None
    """Winner minus runner-up on the primary metric, in the metric's own unit
    (decimal IRR, so 0.012 is 1.2 percentage points)."""
    drivers: tuple[Driver, ...]
    disqualified: tuple[tuple[StructureKey, str], ...]
    tie_breaks: tuple[str, ...]
    caveats: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RankedStructure:
    rank: int
    result: StructureResult
    rank_basis: str


@dataclass(frozen=True, slots=True)
class StructureComparison:
    """The headline output: five structures, ranked, with the reasoning."""

    context: StructureContext
    ranked: tuple[RankedStructure, ...]
    why_this_wins: WhyThisWins | None
    warnings: tuple[str, ...] = ()
    law_verified_on: str = LAW_VERIFIED_ON.isoformat()
    citation_ids: tuple[str, ...] = ()
    capital_account_breaches: tuple[tuple[StructureKey, CapitalAccountBreach], ...] = ()
    """§704(b) capital accounts that sat below their floor, promoted out of the
    warning list because a run of deficit periods is a structural result, not a
    footnote. Each entry names the structure it arose in."""
    funding_failures: tuple[tuple[StructureKey, str], ...] = ()
    """Structures whose sources-and-uses statement does not balance, or whose
    third-party capital exceeds the funding requirement. Empty is the normal
    case and is asserted by the property tests."""

    @property
    def results(self) -> Mapping[StructureKey, StructureResult]:
        return {r.result.key: r.result for r in self.ranked}

    @property
    def headline(self) -> str:
        """One line a reader can be shown first, on the basis actually used.

        Never leads with a rate the engine has declared meaningless.
        """
        why = self.why_this_wins
        if why is None:
            return "No structure is feasible on these inputs."
        winner = self.result(why.winner)
        coc = (
            f"{winner.effective_cost_of_capital:.2%}"
            if winner.effective_cost_of_capital is not None
            else "n/a"
        )
        if why.primary_metric == "sponsor_after_tax_irr":
            return (
                f"{winner.label}: sponsor after-tax IRR "
                f"{winner.sponsor_after_tax_irr:.2%}, effective cost of capital "
                f"{coc}, sponsor equity ${winner.sponsor_equity_required:,.0f}."
            )
        return (
            f"{winner.label}: sponsor NPV ${winner.sponsor_npv:,.0f} at "
            f"{self.context.discount_rate:.1%}, effective cost of capital {coc}, "
            f"sponsor equity ${winner.sponsor_equity_required:,.0f}. Sponsor IRR "
            f"is NOT MEANINGFUL here - "
            f"{winner.sponsor_irr_not_meaningful_reason}"
        )

    def sources_and_uses_table(self) -> tuple[Mapping[str, object], ...]:
        """Sources against uses, per structure — the funding-constraint check.

        The columns a credit committee reads first, and the reason the totals
        can be trusted: post-COD credit monetisation is reported in its own
        column and is deliberately excluded from every source total.
        """
        rows: list[Mapping[str, object]] = []
        for entry in self.ranked:
            s = entry.result.sources_and_uses
            if s is None:
                continue
            rows.append(
                {
                    "structure": entry.result.key.value,
                    "uses_total": s.uses_total,
                    "capex": s.capex,
                    "idc": s.idc,
                    "fees": s.fees,
                    "reserves": s.reserves,
                    "senior_debt": s.senior_debt,
                    "third_party_equity": s.third_party_equity,
                    "credit_proceeds_at_cod": s.credit_proceeds_at_cod,
                    "sponsor_equity": s.sponsor_equity,
                    "sources_total": s.sources_total,
                    "imbalance": s.imbalance,
                    "balances": s.balances,
                    "oversubscribed": s.oversubscribed,
                    "post_cod_monetisation": s.post_cod_monetisation,
                    "post_cod_monetisation_note": s.post_cod_monetisation_note,
                }
            )
        return tuple(rows)

    @property
    def winner(self) -> StructureResult | None:
        feasible = [r for r in self.ranked if r.result.feasible]
        return feasible[0].result if feasible else None

    def result(self, key: StructureKey) -> StructureResult:
        return self.results[key]

    def rank_of(self, key: StructureKey) -> int:
        for r in self.ranked:
            if r.result.key is key:
                return r.rank
        raise KeyError(key)

    def table(self) -> tuple[Mapping[str, object], ...]:
        """Flat rows for the comparison table."""
        rows: list[Mapping[str, object]] = []
        for entry in self.ranked:
            r = entry.result
            timing = r.cash_timing
            rows.append(
                {
                    "rank": entry.rank,
                    "structure": r.key.value,
                    "label": r.label,
                    "feasible": r.feasible,
                    "sponsor_after_tax_irr": r.sponsor_after_tax_irr,
                    "sponsor_after_tax_irr_is_meaningful": (
                        r.sponsor_irr_is_meaningful
                    ),
                    "sponsor_after_tax_irr_not_meaningful_reason": (
                        r.sponsor_irr_not_meaningful_reason
                    ),
                    #: The rate a reader should be shown. ``None`` where the
                    #: engine has declared the IRR meaningless - a table that
                    #: prints this column can never lead with an absurd number.
                    "sponsor_after_tax_irr_display": (
                        r.sponsor_after_tax_irr
                        if r.sponsor_irr_is_meaningful
                        else None
                    ),
                    "sponsor_npv": r.sponsor_npv,
                    "effective_cost_of_capital": r.effective_cost_of_capital,
                    "sponsor_equity_required": r.sponsor_equity_required,
                    "third_party_capital_raised": r.third_party_capital_raised,
                    "total_capital_raised": r.total_capital_raised,
                    "post_cod_monetisation": r.post_cod_monetisation,
                    "funding_requirement": (
                        r.sources_and_uses.uses_total if r.sources_and_uses else None
                    ),
                    "sources_balance": (
                        r.sources_and_uses.balances if r.sources_and_uses else None
                    ),
                    "cash_weighted_average_years": (
                        timing.weighted_average_years if timing else None
                    ),
                    "share_of_cash_by_year_5": (
                        timing.share_received_by_year_5 if timing else None
                    ),
                    "flip_year": r.flip_year,
                    "credit_transferred": r.credit_transferred,
                    "blocking_risks": tuple(
                        f.code
                        for f in r.risks
                        if f.severity is RiskSeverity.BLOCKING
                    ),
                    "reason": r.infeasible_reason,
                    "rank_basis": entry.rank_basis,
                }
            )
        return tuple(rows)


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def run_all_structures(
    ctx: StructureContext, configs: StructureConfigs | None = None
) -> tuple[StructureResult, ...]:
    """Run every configured structure against one context, in a fixed order."""
    configs = configs or StructureConfigs()
    out: list[StructureResult] = []
    if configs.flip is not None:
        out.append(run_flip(ctx, configs.flip))
    if configs.t_flip is not None:
        out.append(run_tflip(ctx, configs.t_flip))
    if configs.preferred is not None:
        out.append(run_preferred(ctx, configs.preferred))
    if configs.transfer is not None:
        out.append(run_transfer(ctx, configs.transfer))
    if configs.sale_leaseback is not None:
        out.append(run_sale_leaseback(ctx, configs.sale_leaseback))
    return tuple(out)


def _apply_credit_gate(
    ctx: StructureContext, results: Sequence[StructureResult]
) -> tuple[StructureResult, ...]:
    """No credit means no credit-dependent structure. Enforced here, centrally.

    A FEOC / MACR failure, a missed begin-construction cliff, or a missed
    placed-in-service backstop all produce the same thing: a zero credit. A
    direct transfer or a T-flip then has nothing to monetise and is not a
    structure at all. Enforcing this in the selector rather than trusting each
    module to remember is deliberate — it is exactly the kind of result that
    must not be able to slip through.
    """
    if not ctx.credit_is_zero:
        return tuple(results)
    reason = (
        ctx.tax.credit.disqualification_reason
        or "The modelled credit is zero."
    )
    if not ctx.tax.feoc.passes and ctx.tax.feoc.applies:
        reason = (
            "FEOC / Material Assistance Cost Ratio test failed: "
            + ctx.tax.feoc.reason
        )
    out: list[StructureResult] = []
    for r in results:
        if r.key.requires_credit and r.feasible:
            out.append(
                replace(
                    r,
                    feasible=False,
                    infeasible_reason=(
                        f"{r.label} depends on a monetisable credit and there "
                        f"is none. {reason}"
                    ),
                    risks=(
                        *r.risks,
                        RiskFlag(
                            code="credit_dependent_structure_without_credit",
                            severity=RiskSeverity.BLOCKING,
                            summary="No credit to monetise",
                            detail=reason,
                            citation_ids=ctx.tax.credit.citation_ids,
                        ),
                    ),
                )
            )
        else:
            out.append(r)
    return tuple(out)


def _sort_key(result: StructureResult) -> tuple:
    """The full deterministic ordering key.

    Tier 0: feasible with a **meaningful** IRR. Tier 1: feasible, IRR not
    meaningful — ranked on sponsor NPV. Tier 2: infeasible. Within tier 0 the
    primary metric is the IRR, and the tie-break chain follows in the published
    order.
    """
    timing = result.cash_timing
    wal = timing.weighted_average_years if timing else float("inf")
    coc = (
        result.effective_cost_of_capital
        if result.effective_cost_of_capital is not None
        else float("inf")
    )
    if not result.feasible:
        return (2, 0.0, 0.0, 0.0, 0.0, result.key.value)
    if (
        result.sponsor_after_tax_irr is None
        or not result.sponsor_irr_is_meaningful
    ):
        return (1, -result.sponsor_npv, coc, wal, 0.0, result.key.value)
    return (
        0,
        -result.sponsor_after_tax_irr,
        coc,
        wal,
        result.sponsor_equity_required,
        result.key.value,
    )


def _rank_basis(result: StructureResult) -> str:
    if not result.feasible:
        return "infeasible"
    if result.sponsor_after_tax_irr is None:
        return "sponsor NPV (after-tax IRR undefined: no net sponsor equity)"
    if not result.sponsor_irr_is_meaningful:
        return (
            "sponsor NPV (after-tax IRR not meaningful: "
            + result.sponsor_irr_not_meaningful_reason.split(":")[0].lower()
            + ")"
        )
    return "sponsor after-tax IRR"


def _tie_break_labels(
    a: StructureResult, b: StructureResult
) -> tuple[str, ...]:
    """Which published tie-break actually separated ``a`` from ``b``."""
    if (
        a.sponsor_after_tax_irr is None
        or b.sponsor_after_tax_irr is None
        or not a.sponsor_irr_is_meaningful
        or not b.sponsor_irr_is_meaningful
        or abs(a.sponsor_after_tax_irr - b.sponsor_after_tax_irr)
        > RANKING_TOLERANCE
    ):
        return ()
    labels: list[str] = []
    a_wal = a.cash_timing.weighted_average_years if a.cash_timing else float("inf")
    b_wal = b.cash_timing.weighted_average_years if b.cash_timing else float("inf")
    a_coc = (
        a.effective_cost_of_capital
        if a.effective_cost_of_capital is not None
        else float("inf")
    )
    b_coc = (
        b.effective_cost_of_capital
        if b.effective_cost_of_capital is not None
        else float("inf")
    )
    if a_coc != b_coc:
        labels.append(
            f"{a.label} beat {b.label} on the first tie-break "
            f"({_TIE_BREAKS[0][0]}: {a_coc:.4%} vs {b_coc:.4%}) after the "
            f"sponsor after-tax IRRs tied."
        )
    elif a_wal != b_wal:
        labels.append(
            f"{a.label} beat {b.label} on the second tie-break "
            f"({_TIE_BREAKS[1][0]}: {a_wal:.2f}y vs {b_wal:.2f}y)."
        )
    elif a.sponsor_equity_required != b.sponsor_equity_required:
        labels.append(
            f"{a.label} beat {b.label} on the third tie-break "
            f"({_TIE_BREAKS[2][0]}: ${a.sponsor_equity_required:,.0f} vs "
            f"${b.sponsor_equity_required:,.0f})."
        )
    else:
        labels.append(
            f"{a.label} and {b.label} are identical on every published metric; "
            f"the order is the structure key, alphabetically."
        )
    return tuple(labels)


def _build_why(
    ctx: StructureContext, ranked: Sequence[RankedStructure]
) -> WhyThisWins | None:
    feasible = [r for r in ranked if r.result.feasible]
    if not feasible:
        return None
    winner = feasible[0].result
    runner_up = feasible[1].result if len(feasible) > 1 else None

    # The headline follows the basis the winner was actually ranked on. A
    # comparison must never lead with a number the engine has just declared
    # meaningless.
    on_irr = (
        winner.sponsor_after_tax_irr is not None
        and winner.sponsor_irr_is_meaningful
    )
    primary_metric = "sponsor_after_tax_irr" if on_irr else "sponsor_npv"

    def _primary(r: StructureResult | None) -> float | None:
        if r is None:
            return None
        return r.sponsor_after_tax_irr if on_irr else r.sponsor_npv

    margin: float | None = None
    winner_value = _primary(winner)
    runner_up_value = _primary(runner_up)
    if winner_value is not None and runner_up_value is not None:
        margin = winner_value - runner_up_value

    def _pair(
        get, higher_is_better: bool, name: str, unit: str, note: str
    ) -> Driver:
        w = get(winner)
        r = get(runner_up) if runner_up is not None else None
        delta = (w - r) if (w is not None and r is not None) else None
        return Driver(
            name=name,
            unit=unit,
            winner_value=w,
            runner_up_value=r,
            delta=delta,
            higher_is_better=higher_is_better,
            note=note,
        )

    drivers = (
        _pair(
            lambda x: x.sponsor_after_tax_irr,
            True,
            "sponsor_after_tax_irr",
            "decimal IRR p.a.",
            "The primary ranking metric.",
        ),
        _pair(
            lambda x: x.effective_cost_of_capital,
            False,
            "effective_cost_of_capital",
            "decimal IRR p.a.",
            "IRR of all third-party capital in and everything paid or "
            "surrendered to it, with tax attributes valued at what the "
            "recipient realises.",
        ),
        _pair(
            lambda x: (
                x.cash_timing.weighted_average_years if x.cash_timing else None
            ),
            False,
            "cash_weighted_average_years",
            "years from COD",
            "When the sponsor actually gets paid. A transfer front-loads; a "
            "flip defers past the flip point.",
        ),
        _pair(
            lambda x: (
                x.cash_timing.share_received_by_year_5 if x.cash_timing else None
            ),
            True,
            "share_of_sponsor_cash_by_year_5",
            "fraction",
            "Share of lifetime sponsor cash received in the first five years.",
        ),
        _pair(
            lambda x: x.sponsor_equity_required,
            False,
            "sponsor_equity_required",
            "US$",
            "Sponsor cash the structure ties up at closing.",
        ),
        _pair(
            lambda x: x.third_party_capital_raised,
            True,
            "third_party_capital_raised",
            "US$",
            "Debt plus investor capital plus credit proceeds.",
        ),
        _pair(
            lambda x: x.sponsor_npv,
            True,
            "sponsor_npv",
            f"US$ at {ctx.discount_rate:.1%}",
            "Present value of the sponsor's after-tax cashflow.",
        ),
    )

    disqualified = tuple(
        (r.result.key, r.result.infeasible_reason)
        for r in ranked
        if not r.result.feasible
    )

    tie_breaks: list[str] = []
    for i in range(len(feasible) - 1):
        tie_breaks.extend(
            _tie_break_labels(feasible[i].result, feasible[i + 1].result)
        )

    caveats: list[str] = []
    if not on_irr:
        # Leading caveat, first in the list, because it changes how every other
        # number below it should be read.
        caveats.append(
            "HEADLINE METRIC: sponsor NPV at "
            f"{ctx.discount_rate:.1%}, not IRR. "
            + winner.sponsor_irr_not_meaningful_reason
            + (
                f" The reported rate of {winner.sponsor_after_tax_irr:.1%} is "
                "carried for completeness and must not be quoted as a return."
                if winner.sponsor_after_tax_irr is not None
                else ""
            )
            + f" Effective cost of capital: "
            + (
                f"{winner.effective_cost_of_capital:.2%}."
                if winner.effective_cost_of_capital is not None
                else "not computable."
            )
        )
    non_meaningful = [
        r.result
        for r in feasible
        if r.result is not winner and not r.result.sponsor_irr_is_meaningful
    ]
    if non_meaningful:
        caveats.append(
            "Ranked on sponsor NPV rather than IRR because the rate is not "
            "meaningful: "
            + ", ".join(r.label for r in non_meaningful)
            + "."
        )
    if margin is not None and on_irr and abs(margin) < 0.0025:
        caveats.append(
            f"The margin over {runner_up.label if runner_up else 'the runner-up'} "
            f"is {abs(margin) * 100:.2f} percentage points - inside the range "
            f"that any of the placeholder market assumptions could move. Treat "
            f"the two as equivalent."
        )
    for w in winner.warnings:
        if "PLACEHOLDER" in w:
            caveats.append(w)
    for flag in winner.risks:
        if flag.severity is RiskSeverity.BLOCKING:
            caveats.append(f"BLOCKING RISK on the winner: {flag.summary}")

    return WhyThisWins(
        winner=winner.key,
        primary_metric=primary_metric,
        winner_value=winner_value,
        runner_up=runner_up.key if runner_up is not None else None,
        runner_up_value=runner_up_value,
        margin=margin,
        drivers=drivers,
        disqualified=disqualified,
        tie_breaks=tuple(tie_breaks),
        caveats=tuple(dict.fromkeys(caveats)),
    )


def compare_structures(
    project: ProjectInputs,
    debt_terms: DebtTerms,
    tax_inputs: TaxProject,
    structure_configs: StructureConfigs | None = None,
    *,
    tax_scenario: TaxScenario | None = None,
    sponsor: SponsorTaxProfile | None = None,
    discount_rate: float = 0.10,
    lockup_dscr: float | None = None,
    context: StructureContext | None = None,
) -> StructureComparison:
    """Run one project through all five structures and rank them.

    ``context`` may be supplied to reuse an already-built
    :class:`StructureContext` (scenario sweeps run much faster that way); it is
    otherwise built from the project, debt terms and tax inputs.
    """
    ctx = context or build_context(
        project,
        debt_terms,
        tax_inputs,
        tax_scenario=tax_scenario,
        sponsor=sponsor,
        discount_rate=discount_rate,
        lockup_dscr=lockup_dscr,
    )
    results = _apply_credit_gate(ctx, run_all_structures(ctx, structure_configs))
    ordered = sorted(results, key=_sort_key)
    ranked = tuple(
        RankedStructure(rank=i + 1, result=r, rank_basis=_rank_basis(r))
        for i, r in enumerate(ordered)
    )

    warnings: list[str] = list(ctx.economics.warnings)
    for r in results:
        warnings.extend(r.warnings)
    for warning in ctx.tax.credit.warnings:
        warnings.append(f"engine.tax: {warning}")
    if ctx.tax.feoc.threshold_is_placeholder:
        warnings.append(
            "engine.tax: the Material Assistance Cost Ratio threshold applied "
            "to this project is a PLACEHOLDER - see engine/tax/UNVERIFIED.md "
            "item 1. Every structure below inherits that uncertainty."
        )

    citations: list[str] = list(ctx.tax.citation_ids)
    for r in results:
        citations.extend(r.citation_ids)

    # Promote the two structural diagnostics out of the warning list. Both are
    # results, not footnotes, and both must reach a reader at the same level as
    # the ranking itself.
    breaches: list[tuple[StructureKey, CapitalAccountBreach]] = []
    funding_failures: list[tuple[StructureKey, str]] = []
    for r in results:
        if r.partnership is not None:
            for breach in r.partnership.capital_account_breaches:
                breaches.append((r.key, breach))
        s = r.sources_and_uses
        if s is not None and (s.oversubscribed or not s.balances):
            funding_failures.append((r.key, s.describe()))

    return StructureComparison(
        context=ctx,
        ranked=ranked,
        why_this_wins=_build_why(ctx, ranked),
        warnings=tuple(dict.fromkeys(warnings)),
        citation_ids=tuple(dict.fromkeys(citations)),
        capital_account_breaches=tuple(breaches),
        funding_failures=tuple(funding_failures),
    )
