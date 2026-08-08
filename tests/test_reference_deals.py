"""The reference deal library — calibration regression, not arithmetic.

Every assertion here answers the question a practitioner asks in the first ten
seconds: *do these numbers look like a real deal?* Arithmetic correctness is
tested elsewhere and passes regardless; a model can be exactly right and still
produce a 163% sponsor IRR on a stack that raises more than the project costs.

So this file fences the **calibration**:

* sponsor after-tax IRR inside a defensible band;
* achieved minimum DSCR clearing the published market floor;
* sources equal uses, with post-COD monetisation excluded;
* the right number of structures feasible, for the right reason;
* every unsourced input labelled and surfaced.

If a change to the engine moves a reference deal outside its band, one of the
two is wrong and somebody has to look. That is the point.
"""

from __future__ import annotations

import pytest

from engine.defaults import MIN_DSCR, RevenueContractType, Technology
from engine.reference_deals import (
    REFERENCE_DEALS,
    REFERENCE_DEALS_VERIFIED_ON,
    Assumption,
    ReferenceDeal,
    reference_deal,
    reference_deal_keys,
)
from engine.structures import StructureKey
from engine.structures.defaults import DE_MINIMIS_SPONSOR_EQUITY_SHARE

_KEYS = list(REFERENCE_DEALS)
_CASES = [pytest.param(k, id=k) for k in _KEYS]


@pytest.fixture(scope="module")
def comparisons() -> dict[str, object]:
    """Run each deal once; the flip solves are not free."""
    return {k: REFERENCE_DEALS[k].compare() for k in _KEYS}


# ---------------------------------------------------------------------------
# Shape and provenance
# ---------------------------------------------------------------------------


def test_the_library_covers_the_three_technologies_spec_asks_for() -> None:
    """Storage and data centres are forward pipeline; solar is safe-harboured."""
    assert set(reference_deal_keys()) == {
        "storage_bess_contracted",
        "solar_safe_harboured",
        "data_center_powered_shell",
    }


def test_an_unknown_key_names_the_available_deals() -> None:
    with pytest.raises(KeyError) as exc:
        reference_deal("nope")
    assert "storage_bess_contracted" in str(exc.value)


@pytest.mark.parametrize("case", _CASES)
def test_every_assumption_carries_a_source_and_a_date(case: str) -> None:
    deal = REFERENCE_DEALS[case]
    assert deal.assumptions
    for a in deal.assumptions:
        assert isinstance(a, Assumption)
        assert a.source.strip()
        assert a.unit is not None
        assert a.verified_on <= REFERENCE_DEALS_VERIFIED_ON


@pytest.mark.parametrize("case", _CASES)
def test_every_unsourced_number_is_labelled_a_placeholder(case: str) -> None:
    """The engine pattern throughout: never fabricate a market number."""
    deal = REFERENCE_DEALS[case]
    for a in deal.assumptions:
        if "PLACEHOLDER" in a.source:
            assert a.is_placeholder, (
                f"{a.name} carries a placeholder source but is not flagged"
            )
        if a.is_placeholder:
            assert "PLACEHOLDER" in a.source


@pytest.mark.parametrize("case", _CASES)
def test_the_placeholder_warning_names_every_placeholder(case: str) -> None:
    deal = REFERENCE_DEALS[case]
    placeholders = deal.placeholder_assumptions()
    assert placeholders, (
        "no reference deal can be fully sourced - offtake pricing has no free "
        "public source - so a deal claiming none is a lie"
    )
    warning = deal.placeholder_warning()
    for a in placeholders:
        assert a.name in warning


@pytest.mark.parametrize("case", _CASES)
def test_revenue_and_capex_are_never_presented_as_sourced(case: str) -> None:
    deal = REFERENCE_DEALS[case]
    names = {a.name: a for a in deal.assumptions}
    assert names["capex"].is_placeholder
    revenue = next(
        a
        for name, a in names.items()
        if name in ("contracted_revenue", "ppa_price", "contracted_rent")
    )
    assert revenue.is_placeholder


@pytest.mark.parametrize("case", _CASES)
def test_the_dscr_assumption_is_taken_from_the_published_benchmark(
    case: str,
) -> None:
    """The one number that is *not* a placeholder must trace to NRF."""
    deal = REFERENCE_DEALS[case]
    dscr = next(a for a in deal.assumptions if a.name == "target_dscr")
    assert not dscr.is_placeholder
    assert "Norton Rose Fulbright" in dscr.source


# ---------------------------------------------------------------------------
# Gearing and coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _CASES)
def test_the_achieved_minimum_dscr_clears_the_published_floor(
    case: str, comparisons
) -> None:
    deal = REFERENCE_DEALS[case]
    sizing = comparisons[case].context.funding.sizing
    assert sizing.min_dscr >= deal.expected.min_dscr_floor, (
        f"{case}: achieved min DSCR {sizing.min_dscr:.3f}x is below the "
        f"{deal.expected.min_dscr_floor:.2f}x floor for "
        f"{deal.project.technology.value} ({deal.dscr_benchmark})"
    )


def test_each_deal_uses_its_own_technology_dscr_benchmark() -> None:
    """No deal silently borrows another technology's coverage requirement."""
    expected = {
        "storage_bess_contracted": (Technology.STORAGE, 1.20),
        "solar_safe_harboured": (Technology.SOLAR, 1.30),
        "data_center_powered_shell": (Technology.DATA_CENTER, 1.15),
    }
    for key, (tech, floor) in expected.items():
        deal = REFERENCE_DEALS[key]
        bench = MIN_DSCR[(tech, RevenueContractType.CONTRACTED)]
        assert deal.debt_terms.target_dscr == pytest.approx(floor)
        assert bench.low <= floor <= bench.high
        assert deal.expected.min_dscr_floor == pytest.approx(floor)


@pytest.mark.parametrize("case", _CASES)
def test_gearing_stays_inside_a_financeable_range(case: str, comparisons) -> None:
    construction = comparisons[case].context.funding.construction
    assert 0.25 <= construction.gearing <= 0.85, (
        f"{case}: gearing {construction.gearing:.1%} is outside anything a "
        f"non-recourse lender would write"
    )


def test_an_itc_deal_is_geared_below_the_ordinary_cap_and_says_why() -> None:
    """The central calibration finding, asserted so it cannot regress quietly.

    A 30% §48E credit is a *source*, not a return. Gear an ITC deal at the
    customary 75% cap and the stack reaches 105% of cost before the sponsor
    contributes anything — which is precisely how the original demo produced a
    de minimis sponsor equity base and a three-figure IRR.
    """
    for key in ("storage_bess_contracted", "solar_safe_harboured"):
        deal = REFERENCE_DEALS[key]
        assert deal.debt_terms.max_gearing < 0.75
        note = next(a for a in deal.assumptions if a.name == "max_gearing")
        assert "credit" in note.note
        assert "Structura modelling convention" in note.source

    # The data centre has no credit, so the ordinary cap applies unmodified.
    dc = REFERENCE_DEALS["data_center_powered_shell"]
    assert dc.debt_terms.max_gearing == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# The headline: sponsor returns in a defensible band
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _CASES)
def test_the_winning_structure_returns_a_defensible_sponsor_irr(
    case: str, comparisons
) -> None:
    deal = REFERENCE_DEALS[case]
    comparison = comparisons[case]
    band = deal.expected.winner_sponsor_irr
    if band is None:
        return
    winner = comparison.winner
    assert winner is not None
    assert winner.sponsor_irr_is_meaningful, (
        f"{case}: the winner was ranked on NPV because its IRR is not "
        f"meaningful - {winner.sponsor_irr_not_meaningful_reason}"
    )
    low, high = band
    assert low <= winner.sponsor_after_tax_irr <= high, (
        f"{case}: winner {winner.key.value} returns "
        f"{winner.sponsor_after_tax_irr:.2%}, outside the calibrated "
        f"{low:.0%}-{high:.0%} band"
    )


@pytest.mark.parametrize("case", _CASES)
def test_no_feasible_structure_reports_an_impossible_rate(
    case: str, comparisons
) -> None:
    deal = REFERENCE_DEALS[case]
    low, high = deal.expected.all_meaningful_irr
    for entry in comparisons[case].ranked:
        r = entry.result
        if not r.feasible or not r.sponsor_irr_is_meaningful:
            continue
        assert r.sponsor_after_tax_irr is not None
        assert low <= r.sponsor_after_tax_irr <= high, (
            f"{case}/{r.key.value}: {r.sponsor_after_tax_irr:.2%} is outside "
            f"the plausible envelope {low:.0%}-{high:.0%}"
        )


@pytest.mark.parametrize("case", _CASES)
def test_the_headline_leads_with_the_metric_it_ranked_on(
    case: str, comparisons
) -> None:
    comparison = comparisons[case]
    why = comparison.why_this_wins
    assert why is not None
    if why.primary_metric == "sponsor_after_tax_irr":
        assert "sponsor after-tax IRR" in comparison.headline
        assert "NOT MEANINGFUL" not in comparison.headline
    else:
        assert "sponsor NPV" in comparison.headline
    assert "effective cost of capital" in comparison.headline


@pytest.mark.parametrize("case", _CASES)
def test_the_effective_cost_of_capital_is_a_credible_cross_check(
    case: str, comparisons
) -> None:
    """It is a cost, so it must be positive and this side of distressed."""
    for entry in comparisons[case].ranked:
        r = entry.result
        if not r.feasible or r.effective_cost_of_capital is None:
            continue
        assert 0.0 < r.effective_cost_of_capital < 0.25, (
            f"{case}/{r.key.value}: effective cost of capital "
            f"{r.effective_cost_of_capital:.2%}"
        )


@pytest.mark.parametrize("case", _CASES)
def test_a_sale_leaseback_is_flagged_rather_than_allowed_to_win_on_leverage(
    case: str, comparisons
) -> None:
    """Sale-leaseback is ~100% financing, so its IRR is a leverage artefact.

    It is not disqualified — it is frequently the right answer on cash — but it
    must not be allowed to top the table on a rate computed over a sliver of
    residual equity.
    """
    result = comparisons[case].result(StructureKey.SALE_LEASEBACK)
    if not result.feasible or result.sponsor_after_tax_irr is None:
        return
    if not result.sponsor_irr_is_meaningful:
        assert result.sponsor_irr_not_meaningful_reason
        assert comparisons[case].rank_of(StructureKey.SALE_LEASEBACK) > 1


# ---------------------------------------------------------------------------
# Sources and uses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _CASES)
def test_sources_equal_uses_exactly_in_every_feasible_structure(
    case: str, comparisons
) -> None:
    for entry in comparisons[case].ranked:
        r = entry.result
        if not r.feasible or r.sources_and_uses is None:
            continue
        s = r.sources_and_uses
        assert s.balances, f"{case}/{r.key.value}: {s.describe()}"
        assert not s.oversubscribed


@pytest.mark.parametrize("case", _CASES)
def test_no_reference_deal_reports_a_funding_failure(
    case: str, comparisons
) -> None:
    assert comparisons[case].funding_failures == ()


@pytest.mark.parametrize("case", _CASES)
def test_sponsor_equity_is_a_real_share_of_the_stack(
    case: str, comparisons
) -> None:
    """At least one structure must leave the sponsor genuine equity at risk.

    A library in which every structure is fully financed would prove nothing
    about the IRR fix; it would just be five de minimis bases. The floor is set
    above the de minimis threshold the selector applies, so a reference deal
    always has at least one structure whose IRR is meaningful on its own terms.
    """
    comparison = comparisons[case]
    uses = comparison.context.economics.total_project_cost
    shares = [
        e.result.sponsor_equity_required / uses
        for e in comparison.ranked
        if e.result.feasible and e.result.sources_and_uses is not None
    ]
    assert shares
    assert max(shares) > DE_MINIMIS_SPONSOR_EQUITY_SHARE


# ---------------------------------------------------------------------------
# Structure-specific: the credit gate and the transfer leg
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _CASES)
def test_the_expected_number_of_structures_is_feasible(
    case: str, comparisons
) -> None:
    deal = REFERENCE_DEALS[case]
    feasible = [e for e in comparisons[case].ranked if e.result.feasible]
    assert len(feasible) == deal.expected.feasible_structures


def test_a_powered_shell_has_no_credit_so_the_gate_disqualifies_two_structures() -> None:
    """§48E reaches clean electricity facilities and storage. Not a building."""
    comparison = REFERENCE_DEALS["data_center_powered_shell"].compare()
    assert comparison.context.credit_is_zero
    for key in (StructureKey.DIRECT_TRANSFER, StructureKey.T_FLIP):
        result = comparison.result(key)
        assert result.feasible is False
        assert result.infeasible_reason
        assert comparison.rank_of(key) > 1
    winner = comparison.winner
    assert winner is not None and winner.key.requires_credit is False


def test_the_two_credit_deals_actually_generate_a_credit() -> None:
    for key, expected_rate in (
        ("storage_bess_contracted", 0.30),
        ("solar_safe_harboured", 0.30),
    ):
        deal = REFERENCE_DEALS[key]
        ctx = deal.build_context()
        assert ctx.credit_amount == pytest.approx(
            deal.tax_project.capex * expected_rate
        )


def test_the_solar_deal_is_on_the_right_side_of_the_begin_construction_cliff() -> None:
    """Under OBBBA, wind and solar must have begun construction by 2026-07-04."""
    deal = REFERENCE_DEALS["solar_safe_harboured"]
    assert deal.tax_project.begin_construction_date is not None
    assert deal.tax_project.begin_construction_date.isoformat() <= "2026-07-04"
    assert deal.build_context().credit_amount > 0.0


def test_storage_keeps_its_runway_and_needs_no_safe_harbour() -> None:
    """OBBBA left standalone storage untouched by the accelerated cliff."""
    deal = REFERENCE_DEALS["storage_bess_contracted"]
    ctx = deal.build_context()
    assert ctx.credit_amount > 0.0
    assert deal.tax_project.placed_in_service_date.year >= 2027


def test_the_t_flip_investor_writes_a_smaller_cheque_than_the_plain_flip() -> None:
    """It is buying depreciation and cash only — the credit has been sold."""
    for key in ("storage_bess_contracted", "solar_safe_harboured"):
        configs = REFERENCE_DEALS[key].configs
        assert configs.flip is not None and configs.t_flip is not None
        assert (
            configs.t_flip.flip.investor_commitment
            < configs.flip.investor_commitment
        )
        # §50(c)(5) allocates the basis reduction on the credit ratio, so an
        # investor with no credit bears no share of it.
        assert configs.t_flip.flip.pre_flip_te_credit == 0.0


def test_the_transfer_settles_outside_the_partnership_and_why() -> None:
    """§6418(b) excludes the proceeds from gross income.

    Paying them into the partnership therefore distributes cash with no matching
    book allocation, which drives the tax-equity capital account below its floor
    and keeps it there. Selling at the holdco is both market practice and the
    configuration that keeps every capital account intact.
    """
    for key in ("storage_bess_contracted", "solar_safe_harboured"):
        assert REFERENCE_DEALS[key].configs.t_flip.proceeds_to_partnership is False


@pytest.mark.parametrize("case", _CASES)
def test_a_flip_never_lands_inside_the_five_year_recapture_period(
    case: str, comparisons
) -> None:
    """§50(a)(1): 20% vesting per full year. Real flip dates clear year five."""
    for entry in comparisons[case].ranked:
        r = entry.result
        if not r.feasible or r.flip_year is None:
            continue
        if comparisons[case].context.economics.itc_amount <= 0.0:
            continue
        assert r.flip_year >= 5.0, (
            f"{case}/{r.key.value}: flip in year {r.flip_year:.2f}, inside the "
            f"§50(a) recapture period"
        )
        assert not any(
            f.code == "flip_inside_recapture_period" for f in r.risks
        )


# ---------------------------------------------------------------------------
# The deals stay runnable and the docs stay honest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _CASES)
def test_each_deal_states_how_it_was_calibrated(case: str) -> None:
    deal = REFERENCE_DEALS[case]
    assert deal.summary.strip()
    assert deal.calibration_note.strip()
    assert deal.dscr_benchmark.strip()


@pytest.mark.parametrize("case", _CASES)
def test_the_placeholder_uncertainty_reaches_the_comparison_warnings(
    case: str, comparisons
) -> None:
    assert any("PLACEHOLDER" in w for w in comparisons[case].warnings)


@pytest.mark.parametrize("case", _CASES)
def test_a_deal_can_be_rerun_from_a_shared_context(case: str) -> None:
    deal: ReferenceDeal = REFERENCE_DEALS[case]
    ctx = deal.build_context()
    a = deal.compare(ctx)
    b = deal.compare(ctx)
    assert [r.result.key for r in a.ranked] == [r.result.key for r in b.ranked]
