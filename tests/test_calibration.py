"""The funding-constraint invariant and the headline-metric robustness guards.

These are the two properties that make a structure comparison *believable*
rather than merely correct, and both were added after a demo configuration
produced a 163% sponsor IRR alongside third-party capital exceeding the cost of
the project. Neither number came from a solver bug. Both came from reporting a
quantity that had never been constrained.

What is asserted here
---------------------
1. **Sources cannot exceed uses.** A property test across all five structures,
   over several deliberately hostile configurations: debt plus third-party
   equity plus sponsor equity must equal capex plus IDC plus fees plus reserves,
   or the structure must say plainly that it is over-subscribed.
2. **Post-COD monetisation is not construction funding.** A §6418 transfer
   settles after the property is placed in service, and a sale-leaseback pays
   after the asset exists. Neither may appear in a source total, and both must
   still be visible in their own column.
3. **The comparison never leads with an absurd number.** A structure with a de
   minimis equity base, an immediate payback or an impossible rate is marked
   ``not_meaningful`` with a reason, is ranked on sponsor NPV, and its rate is
   suppressed from the display column.
4. **A §704(b) capital-account breach is structured and prominent**, carrying
   the periods and the magnitude, not a sentence in a warning list.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from engine import DebtTerms, ProjectInputs
from engine.structures import (
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
from engine.structures.defaults import (
    DE_MINIMIS_SPONSOR_EQUITY_SHARE,
    IMPLAUSIBLE_SPONSOR_IRR,
)
from engine.structures.models import irr_meaningfulness
from engine.tax import MacrInputs, MacrMethod, TaxProject, TaxScenario
from engine.tax import Technology as TaxTechnology
from engine.reference_deals import REFERENCE_DEALS


# ---------------------------------------------------------------------------
# Fixtures: the original broken demo, plus deliberately hostile variants
# ---------------------------------------------------------------------------


def _project(**overrides) -> ProjectInputs:
    base = dict(
        name="Calibration probe",
        capex=200_000_000.0,
        opex_year1=5_000_000.0,
        production_p50=400_000.0,
        contracted_price=70.0,
        contract_years=25.0,
        project_life_years=25.0,
    )
    base.update(overrides)
    return ProjectInputs(**base)


def _tax_project(**overrides) -> TaxProject:
    base = dict(
        technology=TaxTechnology.STORAGE,
        capacity_mw=100.0,
        capex=200_000_000.0,
        placed_in_service_date=date(2027, 1, 1),
        begin_construction_date=date(2026, 3, 1),
        physical_work_commenced=True,
        is_pwa_compliant=True,
        macr_inputs=MacrInputs(method=MacrMethod.USER_ASSERTED, asserted_ratio=0.80),
    )
    base.update(overrides)
    return TaxProject(**base)  # type: ignore[arg-type]


def _configs(commitment: float = 40_000_000.0) -> StructureConfigs:
    flip = FlipConfig(
        target_after_tax_irr=0.07, investor_commitment=commitment
    )
    return StructureConfigs(
        flip=flip,
        t_flip=TFlipConfig(flip=flip),
        preferred=PreferredConfig(commitment=commitment),
        transfer=TransferConfig(),
        sale_leaseback=SaleLeasebackConfig(lease_term_years=15.0),
    )


def _run(*, commitment: float = 40_000_000.0, terms: DebtTerms | None = None):
    return compare_structures(
        _project(),
        terms or DebtTerms(),
        _tax_project(),
        _configs(commitment),
        tax_scenario=TaxScenario(bonus_rate=0.0),
        sponsor=SponsorTaxProfile(),
    )


#: The original demo, plus variants chosen to stress the identity from both
#: sides: a tiny commitment (sponsor funds nearly everything), a commitment
#: larger than the equity the project needs (over-subscription), and a highly
#: geared case where the equity cheque is small in absolute terms.
_CASES = {
    "original_demo": dict(commitment=40_000_000.0),
    "tiny_commitment": dict(commitment=1_000_000.0),
    "oversubscribed": dict(commitment=300_000_000.0),
    "high_gearing": dict(
        commitment=40_000_000.0,
        terms=DebtTerms(max_gearing=0.80, target_dscr=1.20),
    ),
    "low_gearing": dict(
        commitment=40_000_000.0,
        terms=DebtTerms(max_gearing=0.30, target_dscr=1.20),
    ),
}

_ALL_COMPARISONS = [
    pytest.param(name, id=name) for name in _CASES
] + [pytest.param(f"reference:{k}", id=f"reference_{k}") for k in REFERENCE_DEALS]


def _comparison(name: str):
    if name.startswith("reference:"):
        return REFERENCE_DEALS[name.split(":", 1)[1]].compare()
    return _run(**_CASES[name])


# ---------------------------------------------------------------------------
# 1. The funding constraint — sources cannot exceed uses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _ALL_COMPARISONS)
def test_sources_never_exceed_uses_in_any_structure(case: str) -> None:
    """Total capital raised ≤ total funding requirement, in all five structures.

    The property is stated as an inequality because the honest failure mode is
    over-subscription — a stated commitment larger than the project needs — and
    that must be *reported*, not floored away. So either the stack balances, or
    it is flagged over-subscribed with a BLOCKING risk naming the excess.
    """
    comparison = _comparison(case)
    checked = 0
    for entry in comparison.ranked:
        result = entry.result
        if not result.feasible or result.sources_and_uses is None:
            continue
        checked += 1
        s = result.sources_and_uses
        if s.oversubscribed:
            codes = {f.code for f in result.risks}
            assert "funding_oversubscribed" in codes, (
                f"{result.key.value} is over-subscribed but carries no "
                f"BLOCKING risk saying so"
            )
            continue
        assert s.sources_total <= s.uses_total + s.tolerance, (
            f"{result.key.value}: sources ${s.sources_total:,.0f} exceed uses "
            f"${s.uses_total:,.0f}. {s.describe()}"
        )
        assert s.balances, (
            f"{result.key.value}: sources and uses differ by "
            f"${s.imbalance:,.0f}. {s.describe()}"
        )
        assert result.total_capital_raised == pytest.approx(s.sources_total)
        assert result.third_party_capital_raised == pytest.approx(
            s.third_party_construction_capital
        )
    assert checked >= 3


@pytest.mark.parametrize("case", _ALL_COMPARISONS)
def test_uses_reconcile_to_the_phase_1_funding_solve(case: str) -> None:
    """The uses side is not restated here — it is the Phase 1 total project cost."""
    comparison = _comparison(case)
    expected = comparison.context.economics.total_project_cost
    for entry in comparison.ranked:
        s = entry.result.sources_and_uses
        if s is None:
            continue
        assert s.uses_total == pytest.approx(expected)
        assert s.capex + s.idc + s.fees + s.reserves == pytest.approx(
            s.uses_total, abs=s.tolerance
        )


@pytest.mark.parametrize("case", _ALL_COMPARISONS)
def test_post_cod_monetisation_is_excluded_from_every_source_total(
    case: str,
) -> None:
    """§6418 proceeds and a sale-leaseback price are reimbursement, not funding.

    This is the specific defect the invariant exists to prevent: the credit does
    not exist until the property is placed in service, so its sale cannot have
    funded construction. Both must be visible in their own column and absent
    from every source line.
    """
    comparison = _comparison(case)
    for entry in comparison.ranked:
        result = entry.result
        s = result.sources_and_uses
        if s is None or not result.feasible:
            continue
        assert s.credit_proceeds_at_cod == 0.0, (
            "No structure currently models a credit monetised before COD; "
            "funding construction against an expected credit needs an ITC "
            "bridge loan, which is declared unmodelled."
        )
        assert result.post_cod_monetisation == pytest.approx(
            s.post_cod_monetisation
        )
        if s.post_cod_monetisation > 0.0:
            assert s.post_cod_monetisation_note, (
                f"{result.key.value} reports post-COD monetisation without "
                f"saying what it is or why it is not funding"
            )
            # The whole point: excluding it is what makes the identity hold.
            assert (
                s.sources_total + s.post_cod_monetisation > s.uses_total
            ), "test fixture no longer exercises the exclusion"


def test_the_transfer_proceeds_used_to_be_counted_as_construction_capital() -> None:
    """Regression on the exact defect: a T-flip must not out-raise the project.

    Before the fix, ``third_party_capital_raised`` for the T-flip was
    ``debt + tax equity + transfer net proceeds`` — $255.3m against a $216.7m
    funding requirement — because the §6418 proceeds were added to the
    construction stack. The flip and the T-flip differ only in the transfer leg,
    so on identical configs their construction capital must now be identical.
    """
    comparison = _run()
    flip = comparison.result(StructureKey.PARTNERSHIP_FLIP)
    tflip = comparison.result(StructureKey.T_FLIP)
    assert tflip.post_cod_monetisation > 0.0
    assert flip.post_cod_monetisation == 0.0
    assert tflip.third_party_capital_raised == pytest.approx(
        flip.third_party_capital_raised
    )
    assert tflip.total_capital_raised == pytest.approx(flip.total_capital_raised)
    assert tflip.total_capital_raised <= (
        comparison.context.economics.total_project_cost + 1.0
    )


def test_an_oversubscribed_stack_is_blocked_not_silently_floored() -> None:
    """A commitment larger than the equity the project needs is a hard stop."""
    comparison = _run(commitment=300_000_000.0)
    flip = comparison.result(StructureKey.PARTNERSHIP_FLIP)
    assert flip.sources_and_uses is not None
    assert flip.sources_and_uses.oversubscribed
    assert flip.sources_and_uses.sponsor_equity == 0.0
    blocking = [f for f in flip.risks if f.code == "funding_oversubscribed"]
    assert blocking and blocking[0].severity.value == "blocking"
    assert (StructureKey.PARTNERSHIP_FLIP, flip.sources_and_uses.describe()) in [
        (k, d) for k, d in comparison.funding_failures
    ]


def test_the_sources_and_uses_table_is_available_for_every_feasible_structure() -> None:
    comparison = _run()
    rows = comparison.sources_and_uses_table()
    assert rows
    for row in rows:
        assert set(row) >= {
            "structure",
            "uses_total",
            "senior_debt",
            "third_party_equity",
            "sponsor_equity",
            "sources_total",
            "post_cod_monetisation",
            "balances",
        }


# ---------------------------------------------------------------------------
# 2. Headline-metric robustness
# ---------------------------------------------------------------------------


def test_a_de_minimis_equity_base_makes_the_irr_not_meaningful() -> None:
    meaningful, reason = irr_meaningfulness(
        sponsor_after_tax_irr=1.63,
        sponsor_equity_required=2_000_000.0,
        funding_requirement=200_000_000.0,
        payback_years=8.0,
    )
    assert meaningful is False
    assert "de minimis" in reason.lower()
    assert f"{DE_MINIMIS_SPONSOR_EQUITY_SHARE:.0%}" in reason


def test_an_immediate_payback_makes_the_irr_not_meaningful() -> None:
    meaningful, reason = irr_meaningfulness(
        sponsor_after_tax_irr=0.35,
        sponsor_equity_required=60_000_000.0,
        funding_requirement=200_000_000.0,
        payback_years=0.4,
    )
    assert meaningful is False
    assert "payback" in reason.lower()


def test_an_impossible_rate_is_never_reported_as_a_return() -> None:
    meaningful, reason = irr_meaningfulness(
        sponsor_after_tax_irr=IMPLAUSIBLE_SPONSOR_IRR + 0.01,
        sponsor_equity_required=60_000_000.0,
        funding_requirement=200_000_000.0,
        payback_years=9.0,
    )
    assert meaningful is False
    assert "8-15%" in reason


def test_an_ordinary_project_finance_return_is_meaningful() -> None:
    meaningful, reason = irr_meaningfulness(
        sponsor_after_tax_irr=0.12,
        sponsor_equity_required=45_000_000.0,
        funding_requirement=200_000_000.0,
        payback_years=8.0,
    )
    assert meaningful is True
    assert reason == ""


def test_the_original_demo_no_longer_leads_with_a_three_figure_irr() -> None:
    """The headline is the point of the whole exercise.

    On the original demo inputs the ranked table led with a 163.66% sponsor IRR.
    Those inputs are still supported — Structura does not refuse a configuration
    — but the comparison must now refuse to *present* the number as a return.
    """
    comparison = _run()
    why = comparison.why_this_wins
    assert why is not None
    winner = comparison.result(why.winner)
    if winner.sponsor_after_tax_irr is not None:
        assert (
            winner.sponsor_irr_is_meaningful is False
            or winner.sponsor_after_tax_irr <= IMPLAUSIBLE_SPONSOR_IRR
        )
    if not winner.sponsor_irr_is_meaningful:
        assert why.primary_metric == "sponsor_npv"
        assert "NOT MEANINGFUL" in comparison.headline
        assert winner.sponsor_irr_not_meaningful_reason
    assert "163" not in comparison.headline


@pytest.mark.parametrize("case", _ALL_COMPARISONS)
def test_the_headline_never_quotes_an_implausible_rate_as_a_return(
    case: str,
) -> None:
    comparison = _comparison(case)
    why = comparison.why_this_wins
    if why is None:
        return
    winner = comparison.result(why.winner)
    if why.primary_metric == "sponsor_after_tax_irr":
        assert winner.sponsor_after_tax_irr is not None
        assert winner.sponsor_irr_is_meaningful
        assert winner.sponsor_after_tax_irr <= IMPLAUSIBLE_SPONSOR_IRR
    else:
        assert why.primary_metric == "sponsor_npv"


@pytest.mark.parametrize("case", _ALL_COMPARISONS)
def test_the_display_column_suppresses_a_meaningless_rate(case: str) -> None:
    for row in _comparison(case).table():
        if row["sponsor_after_tax_irr_is_meaningful"]:
            assert row["sponsor_after_tax_irr_display"] == (
                row["sponsor_after_tax_irr"]
            )
        else:
            assert row["sponsor_after_tax_irr_display"] is None
            if row["feasible"]:
                assert row["sponsor_after_tax_irr_not_meaningful_reason"]


@pytest.mark.parametrize("case", _ALL_COMPARISONS)
def test_effective_cost_of_capital_is_always_available_as_the_cross_check(
    case: str,
) -> None:
    """The sanity check must survive whatever happens to the headline metric."""
    comparison = _comparison(case)
    for row in comparison.table():
        assert "effective_cost_of_capital" in row
    why = comparison.why_this_wins
    if why is not None:
        assert "effective_cost_of_capital" in {d.name for d in why.drivers}
        assert "effective cost of capital" in comparison.headline


@pytest.mark.parametrize("case", _ALL_COMPARISONS)
def test_structures_with_a_meaningful_irr_rank_ahead_of_those_without(
    case: str,
) -> None:
    comparison = _comparison(case)
    seen_non_meaningful = False
    for entry in comparison.ranked:
        if not entry.result.feasible:
            continue
        meaningful = (
            entry.result.sponsor_after_tax_irr is not None
            and entry.result.sponsor_irr_is_meaningful
        )
        if not meaningful:
            seen_non_meaningful = True
        else:
            assert not seen_non_meaningful, (
                "a structure ranked on NPV appeared ahead of one ranked on a "
                "meaningful IRR"
            )


@pytest.mark.parametrize("case", _ALL_COMPARISONS)
def test_the_rank_basis_states_which_metric_was_used(case: str) -> None:
    for entry in _comparison(case).ranked:
        if not entry.result.feasible:
            assert entry.rank_basis == "infeasible"
        elif entry.result.sponsor_irr_is_meaningful:
            assert entry.rank_basis == "sponsor after-tax IRR"
        else:
            assert entry.rank_basis.startswith("sponsor NPV")


# ---------------------------------------------------------------------------
# 3. The §704(b) capital-account breach, promoted out of the warning list
# ---------------------------------------------------------------------------


def test_a_capital_account_breach_is_structured_with_periods_and_magnitude() -> None:
    """The original demo breached for 25 consecutive periods.

    It is a config artefact plus the declared missing qualified income offset —
    no allocation can cause it, because the DRO-cap mechanic caps allocations at
    the floor and ``assert_capital_account_integrity`` raises if one ever gets
    past. What was wrong was the *reporting*: a single sentence at the end of a
    warning list. It now arrives as a structured record.
    """
    comparison = _run()
    assert comparison.capital_account_breaches, (
        "the original demo inputs must still reproduce the breach"
    )
    keys = {k for k, _ in comparison.capital_account_breaches}
    assert StructureKey.T_FLIP in keys or StructureKey.PARTNERSHIP_FLIP in keys
    for key, breach in comparison.capital_account_breaches:
        assert breach.n_periods >= 1
        assert len(breach.years) == breach.n_periods
        assert breach.worst_breach < 0.0
        assert breach.worst_period in breach.periods
        assert breach.cause == "distributions"
        assert "qualified income offset" in breach.describe()


def test_a_sustained_breach_reaches_the_structure_as_a_blocking_risk() -> None:
    comparison = _run()
    for key, breach in comparison.capital_account_breaches:
        result = comparison.result(key)
        flags = [f for f in result.risks if f.code == "capital_account_below_floor"]
        assert flags, f"{key.value} breach did not become a risk flag"
        expected = "blocking" if breach.n_periods > 1 else "caution"
        assert any(f.severity.value == expected for f in flags)
        assert any(str(breach.worst_year) in f.summary for f in flags)


def test_no_reference_deal_carries_a_capital_account_breach() -> None:
    """Calibration, not suppression: the reference deals do not trigger it."""
    for key, deal in REFERENCE_DEALS.items():
        comparison = deal.compare()
        total = sum(b.n_periods for _, b in comparison.capital_account_breaches)
        assert total <= deal.expected.max_capital_account_breach_periods, (
            f"{key}: {total} breach period(s), expected at most "
            f"{deal.expected.max_capital_account_breach_periods} - "
            + "; ".join(b.describe() for _, b in comparison.capital_account_breaches)
        )


def test_an_allocation_can_never_cause_a_breach() -> None:
    """The distinction the whole diagnostic rests on.

    Economic effect is tested on the *allocation*. A distribution that creates a
    deficit is a different problem with a different cure. If an allocation ever
    breached a floor, ``run_partnership`` would have raised — so every breach
    the engine can report must be distribution-driven.
    """
    for case in ("original_demo", "tiny_commitment", "high_gearing"):
        comparison = _comparison(case)
        for _key, breach in comparison.capital_account_breaches:
            assert breach.cause == "distributions"


def test_the_breach_warning_still_appears_in_the_warning_list_too() -> None:
    """Promoting it must not remove it from where a reader already looks."""
    comparison = _run()
    assert any("capital" in w and "floor" in w for w in comparison.warnings)


# ---------------------------------------------------------------------------
# 4. Determinism, unchanged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _ALL_COMPARISONS)
def test_the_calibrated_ranking_is_still_deterministic(case: str) -> None:
    a = [r.result.key for r in _comparison(case).ranked]
    b = [r.result.key for r in _comparison(case).ranked]
    assert a == b


def test_reusing_a_context_does_not_change_any_result() -> None:
    deal = REFERENCE_DEALS["storage_bess_contracted"]
    ctx = deal.build_context()
    a = deal.compare(ctx)
    b = deal.compare(ctx)
    for x, y in zip(a.ranked, b.ranked):
        assert x.result.key is y.result.key
        assert x.result.sponsor_npv == pytest.approx(y.result.sponsor_npv)


def test_replacing_a_result_does_not_break_the_sort_key() -> None:
    """The sort key reads the new fields, so it must tolerate a bare result."""
    from engine.structures.selector import _sort_key

    comparison = _run()
    first = comparison.ranked[0].result
    stripped = replace(
        first, sponsor_irr_is_meaningful=True, sponsor_after_tax_irr=0.11
    )
    assert _sort_key(stripped)[0] == 0
