"""The structure selector: ranking, determinism, and the hard credit gate.

The selector is the package's entry point, so the properties tested here
are about **trust**, not arithmetic: the ranking must be reproducible, the
reason for the ranking must be attached to the numbers that produced it, and a
project with no credit must never be told to sell one.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from engine import DebtTerms, ProjectInputs
from engine.tax import (
    ForeignEntityFlags,
    ForeignEntityStatus,
    MacrInputs,
    MacrMethod,
    TaxProject,
    TaxScenario,
)
from engine.tax import Technology as TaxTechnology
from engine.structures import (
    PROJECT_STRUCTURES,
    FlipConfig,
    PreferredConfig,
    SaleLeasebackConfig,
    SponsorTaxProfile,
    StructureConfigs,
    StructureKey,
    TFlipConfig,
    TransferConfig,
    build_context,
    compare_structures,
)
from engine.reference_deals import reference_deal
from engine.structures.selector import _sort_key


#: The selector tests run on the **calibrated** storage reference deal rather
#: than on an ad-hoc fixture. That is deliberate. An earlier version of this
#: file used a 100 MW / $200m case geared at 75% alongside a 30% ITC, which is
#: 105% of cost before the sponsor contributes anything: it left sponsor equity
#: at 6.5% of the stack and produced a 163% sponsor IRR. Ranking behaviour
#: asserted on inputs like that tests the artefact, not the selector. See
#: ``engine/reference_deals.py``.
_REFERENCE = reference_deal("storage_bess_contracted")


def storage_project() -> ProjectInputs:
    return _REFERENCE.project


def storage_terms() -> DebtTerms:
    return _REFERENCE.debt_terms


def storage_tax_project(**overrides: object) -> TaxProject:
    if not overrides:
        return _REFERENCE.tax_project
    return replace(_REFERENCE.tax_project, **overrides)  # type: ignore[arg-type]


def default_configs() -> StructureConfigs:
    """Configs with every commitment stated, so nothing depends on a
    placeholder derivation and the comparison is like for like."""
    return _REFERENCE.configs


def run(
    *,
    sponsor: SponsorTaxProfile | None = None,
    tax_project: TaxProject | None = None,
    configs: StructureConfigs | None = None,
    bonus_rate: float = 0.0,
):
    return compare_structures(
        storage_project(),
        storage_terms(),
        tax_project or storage_tax_project(),
        configs or default_configs(),
        tax_scenario=replace(_REFERENCE.tax_scenario, bonus_rate=bonus_rate),
        sponsor=sponsor or _REFERENCE.sponsor,
    )


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_all_five_structures_are_run_against_the_same_project() -> None:
    comparison = run()
    assert {r.result.key for r in comparison.ranked} == set(PROJECT_STRUCTURES)
    assert len(comparison.ranked) == 5
    assert [r.rank for r in comparison.ranked] == [1, 2, 3, 4, 5]
    # One project, one debt sizing, one credit determination.
    econ = comparison.context.economics
    assert econ.debt_at_cod > 0.0
    assert econ.equity_at_cod > 0.0


def test_the_comparison_table_carries_every_headline_metric() -> None:
    rows = run().table()
    required = {
        "rank",
        "structure",
        "feasible",
        "sponsor_after_tax_irr",
        "effective_cost_of_capital",
        "sponsor_equity_required",
        "total_capital_raised",
        "cash_weighted_average_years",
        "share_of_cash_by_year_5",
    }
    for row in rows:
        assert required <= set(row)


def test_ranking_is_deterministic_across_runs() -> None:
    a = [r.result.key for r in run().ranked]
    b = [r.result.key for r in run().ranked]
    assert a == b


def test_the_ranking_is_sorted_by_sponsor_after_tax_irr_descending() -> None:
    """Descending IRR — among the structures whose IRR is *meaningful*.

    A structure with a de minimis equity base, an immediate payback or an
    impossible rate is ranked on sponsor NPV instead and placed after every
    structure with a real rate; the reason travels with it. A sale-leaseback is
    the standing example: effectively 100% financing, so its IRR is computed
    over a sliver of residual equity and is not a return. See
    ``engine.structures.models.irr_meaningfulness``.
    """
    comparison = run()
    rates = [
        r.result.sponsor_after_tax_irr
        for r in comparison.ranked
        if r.result.feasible
        and r.result.sponsor_after_tax_irr is not None
        and r.result.sponsor_irr_is_meaningful
    ]
    assert rates
    assert rates == sorted(rates, reverse=True)

    # And everything ranked on NPV instead sits behind everything ranked on IRR.
    on_npv = [
        r.rank
        for r in comparison.ranked
        if r.result.feasible and not r.result.sponsor_irr_is_meaningful
    ]
    on_irr = [
        r.rank
        for r in comparison.ranked
        if r.result.feasible and r.result.sponsor_irr_is_meaningful
    ]
    if on_npv and on_irr:
        assert max(on_irr) < min(on_npv)
    for r in comparison.ranked:
        if r.result.feasible and not r.result.sponsor_irr_is_meaningful:
            assert r.result.sponsor_irr_not_meaningful_reason


def test_infeasible_structures_rank_last() -> None:
    comparison = run(
        tax_project=storage_tax_project(
            macr_inputs=MacrInputs(
                method=MacrMethod.USER_ASSERTED, asserted_ratio=0.05
            )
        )
    )
    feasible_ranks = [r.rank for r in comparison.ranked if r.result.feasible]
    infeasible_ranks = [r.rank for r in comparison.ranked if not r.result.feasible]
    assert infeasible_ranks
    assert not feasible_ranks or max(feasible_ranks) < min(infeasible_ranks)


# ---------------------------------------------------------------------------
# The credit gate
# ---------------------------------------------------------------------------


def test_a_macr_failure_cannot_leave_a_credit_dependent_structure_first() -> None:
    """Below the MACR threshold, the credit is denied outright.

    A direct transfer and a T-flip both exist only to monetise a credit. With
    no credit they must be infeasible, must not rank first, and must say why.
    """
    comparison = run(
        tax_project=storage_tax_project(
            macr_inputs=MacrInputs(
                method=MacrMethod.USER_ASSERTED, asserted_ratio=0.05
            )
        )
    )
    assert comparison.context.tax.feoc.passes is False
    assert comparison.context.credit_is_zero

    for key in (StructureKey.DIRECT_TRANSFER, StructureKey.T_FLIP):
        result = comparison.result(key)
        assert result.feasible is False
        assert comparison.rank_of(key) > 1
        assert result.infeasible_reason

    winner = comparison.winner
    if winner is not None:
        assert winner.key.requires_credit is False


def test_the_credit_gate_names_the_macr_failure() -> None:
    comparison = run(
        tax_project=storage_tax_project(
            macr_inputs=MacrInputs(
                method=MacrMethod.USER_ASSERTED, asserted_ratio=0.05
            )
        )
    )
    reasons = dict(comparison.why_this_wins.disqualified)
    assert any(
        "MACR" in reason or "Material Assistance" in reason
        for reason in reasons.values()
    )


def test_a_blocked_foreign_transferee_disqualifies_the_transfer_only() -> None:
    comparison = run(
        tax_project=storage_tax_project(
            foreign_entity_flags=ForeignEntityFlags(
                transferee_status=ForeignEntityStatus.SPECIFIED_FOREIGN_ENTITY,
                received_material_assistance_from_pfe=False,
            ),
            taxable_year_begin=date(2027, 1, 1),
        )
    )
    assert comparison.result(StructureKey.DIRECT_TRANSFER).feasible is False
    assert comparison.result(StructureKey.T_FLIP).feasible is False
    # A plain flip does not depend on a transfer and survives.
    assert comparison.result(StructureKey.PARTNERSHIP_FLIP).feasible is True


# ---------------------------------------------------------------------------
# "Why this wins"
# ---------------------------------------------------------------------------


def test_why_this_wins_is_keyed_to_the_numbers_that_produced_the_ranking() -> None:
    comparison = run()
    why = comparison.why_this_wins
    assert why is not None
    assert why.winner is comparison.ranked[0].result.key
    assert why.primary_metric == "sponsor_after_tax_irr"
    assert why.winner_value == comparison.ranked[0].result.sponsor_after_tax_irr
    assert why.runner_up is comparison.ranked[1].result.key
    assert why.margin == pytest.approx(
        comparison.ranked[0].result.sponsor_after_tax_irr
        - comparison.ranked[1].result.sponsor_after_tax_irr
    )
    names = {d.name for d in why.drivers}
    assert {
        "sponsor_after_tax_irr",
        "effective_cost_of_capital",
        "cash_weighted_average_years",
        "sponsor_equity_required",
        "sponsor_npv",
    } <= names
    for driver in why.drivers:
        if driver.winner_value is not None and driver.runner_up_value is not None:
            assert driver.delta == pytest.approx(
                driver.winner_value - driver.runner_up_value
            )


def test_placeholder_market_assumptions_reach_the_top_level_warnings() -> None:
    comparison = run(configs=StructureConfigs())
    assert any("PLACEHOLDER" in w for w in comparison.warnings)


def test_the_law_verification_date_is_carried_through() -> None:
    assert run().law_verified_on == "2026-08-06"


def test_the_unverified_macr_threshold_is_propagated_not_papered_over() -> None:
    """``engine/tax/UNVERIFIED.md`` item 1 is the largest known gap."""
    comparison = run()
    assert comparison.context.tax.feoc.threshold_is_placeholder is True
    assert any("PLACEHOLDER" in w and "Material Assistance" in w
               for w in comparison.warnings)


# ---------------------------------------------------------------------------
# A constructed case where one structure clearly dominates
# ---------------------------------------------------------------------------


def test_a_transfer_dominates_when_it_is_the_only_structure_left_standing() -> None:
    """Engineer the deal so the answer is unambiguous, then assert the reason.

    Every partnership route is switched off (no investor is willing to fund
    one) and the sale-leaseback is pushed outside the §50(d)(4) three-month
    window, so it loses the credit entirely. What remains is the direct
    transfer, and it must win *for the stated reason* — the highest sponsor
    after-tax IRR — with the others disqualified and named.
    """
    configs = StructureConfigs(
        flip=FlipConfig(investor_commitment=0.0),
        t_flip=None,
        preferred=PreferredConfig(commitment=0.0),
        transfer=TransferConfig(price_per_dollar=0.95, transaction_cost_pct=0.01),
        sale_leaseback=SaleLeasebackConfig(
            lease_term_years=24.0,
            asset_useful_life_years=25.0,
            months_after_placed_in_service=12,
        ),
    )
    comparison = run(configs=configs)
    winner = comparison.winner
    assert winner is not None
    assert winner.key is StructureKey.DIRECT_TRANSFER
    assert comparison.rank_of(StructureKey.DIRECT_TRANSFER) == 1

    why = comparison.why_this_wins
    assert why.winner is StructureKey.DIRECT_TRANSFER
    assert why.primary_metric == "sponsor_after_tax_irr"
    disqualified = dict(why.disqualified)
    assert StructureKey.PARTNERSHIP_FLIP in disqualified
    assert StructureKey.PREFERRED_EQUITY in disqualified

    # And it won on real money, not on a rounding artefact.
    assert winner.transfer_net_proceeds == pytest.approx(
        comparison.context.economics.itc_amount * (0.95 - 0.01), abs=1.0
    )


def test_a_sponsor_with_no_tax_capacity_prefers_a_partnership_to_a_transfer() -> None:
    """The structural point of the whole package.

    A sponsor that cannot use depreciation strands it in a direct transfer. A
    partnership allocates those deductions to an investor that can use them, so
    the flip must beat the transfer on the sponsor's own after-tax IRR.
    """
    comparison = run(sponsor=SponsorTaxProfile(can_use_depreciation=False))
    flip = comparison.result(StructureKey.PARTNERSHIP_FLIP)
    transfer = comparison.result(StructureKey.DIRECT_TRANSFER)
    assert flip.feasible and transfer.feasible
    assert flip.sponsor_after_tax_irr > transfer.sponsor_after_tax_irr
    assert comparison.rank_of(StructureKey.PARTNERSHIP_FLIP) < comparison.rank_of(
        StructureKey.DIRECT_TRANSFER
    )
    assert "depreciation_stranded" in {f.code for f in transfer.risks}


# ---------------------------------------------------------------------------
# Tie-breaking
# ---------------------------------------------------------------------------


def test_an_exact_tie_breaks_on_the_published_chain_and_says_so() -> None:
    """Force a tie by cloning the winner's IRR onto the runner-up."""
    comparison = run()
    first = comparison.ranked[0].result
    second = comparison.ranked[1].result
    tied = replace(
        second,
        sponsor_after_tax_irr=first.sponsor_after_tax_irr,
        effective_cost_of_capital=(
            (first.effective_cost_of_capital or 0.05) + 0.01
        ),
    )
    # The sort key must still put the lower cost of capital first.
    assert _sort_key(first) < _sort_key(tied)


def test_tie_breaks_are_reported_when_they_fire() -> None:
    from engine.structures.selector import _tie_break_labels

    comparison = run()
    first = comparison.ranked[0].result
    tied = replace(
        comparison.ranked[1].result,
        sponsor_after_tax_irr=first.sponsor_after_tax_irr,
        effective_cost_of_capital=(
            (first.effective_cost_of_capital or 0.05) + 0.01
        ),
    )
    labels = _tie_break_labels(first, tied)
    assert labels
    assert "effective cost of capital" in labels[0]


# ---------------------------------------------------------------------------
# Reuse and cheapness
# ---------------------------------------------------------------------------


def test_a_prebuilt_context_can_be_reused_across_comparisons() -> None:
    ctx = build_context(
        storage_project(),
        storage_terms(),
        storage_tax_project(),
        tax_scenario=TaxScenario(bonus_rate=0.0),
    )
    a = compare_structures(
        storage_project(),
        storage_terms(),
        storage_tax_project(),
        default_configs(),
        context=ctx,
    )
    b = compare_structures(
        storage_project(),
        storage_terms(),
        storage_tax_project(),
        default_configs(),
        context=ctx,
    )
    assert [r.result.key for r in a.ranked] == [r.result.key for r in b.ranked]
    assert a.context is ctx


def test_omitting_a_structure_leaves_it_out_entirely() -> None:
    comparison = run(
        configs=StructureConfigs(
            flip=None, t_flip=None, preferred=None, sale_leaseback=None
        )
    )
    assert [r.result.key for r in comparison.ranked] == [
        StructureKey.DIRECT_TRANSFER
    ]
