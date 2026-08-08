"""Partnership flip: the yield-based solve, the flip mechanics, the T-flip.

The property that matters most here is the one in the module docstring of
:mod:`engine.structures.flip`: the flip point is an **output** of a numerical
solve, and at the solved point the tax-equity investor's after-tax IRR equals
its contracted target. Everything else - monotonicity, the fixed-date variant,
the T-flip's effect on the flip point - hangs off that.
"""

from __future__ import annotations

from datetime import date

import pytest

from engine import DebtTerms, ProjectInputs
from engine.metrics import irr
from engine.tax import (
    MacrInputs,
    MacrMethod,
    TaxProject,
    TaxScenario,
)
from engine.tax import Technology as TaxTechnology
from engine.structures import (
    FlipConfig,
    FlipTrigger,
    SponsorTaxProfile,
    StructureKey,
    TFlipConfig,
    build_context,
    build_flip_partnership,
    flip_sharing_ratios,
    run_flip,
    run_tflip,
    solve_flip_point,
)
from engine.structures.defaults import CAPITAL_ACCOUNT_TOLERANCE
from engine.structures.flip import SPONSOR, TAX_EQUITY, investor_after_tax_series

TOL = 1e-6


def storage_project() -> ProjectInputs:
    """A contracted 100 MW storage deal. Storage keeps §48E to 2033."""
    return ProjectInputs(
        name="Structures test - storage",
        capex=200_000_000.0,
        opex_year1=5_000_000.0,
        production_p50=400_000.0,
        contracted_price=70.0,
        contract_years=25.0,
        project_life_years=25.0,
        periods_per_year=1,
    )


def storage_tax_project(**overrides: object) -> TaxProject:
    base = dict(
        technology=TaxTechnology.STORAGE,
        capacity_mw=100.0,
        capex=200_000_000.0,
        placed_in_service_date=date(2027, 1, 1),
        begin_construction_date=date(2026, 3, 1),
        physical_work_commenced=True,
        is_pwa_compliant=True,
        macr_inputs=MacrInputs(
            method=MacrMethod.USER_ASSERTED, asserted_ratio=0.80
        ),
    )
    base.update(overrides)
    return TaxProject(**base)  # type: ignore[arg-type]


def make_context(
    *,
    bonus_rate: float = 0.0,
    sponsor: SponsorTaxProfile | None = None,
    tax_project: TaxProject | None = None,
):
    """A context with bonus switched off, so depreciation runs the MACRS table.

    Full bonus expensing dumps the entire deduction into year one, which makes
    a tax-equity investor hit any plausible target yield almost immediately and
    leaves nothing interesting to solve. The MACRS 5-year table spreads it and
    produces a flip point in the range a practitioner would recognise.
    """
    return build_context(
        storage_project(),
        DebtTerms(),
        tax_project or storage_tax_project(),
        tax_scenario=TaxScenario(bonus_rate=bonus_rate),
        sponsor=sponsor or SponsorTaxProfile(),
    )


# ---------------------------------------------------------------------------
# Sharing ratios
# ---------------------------------------------------------------------------


def test_flip_ratios_switch_at_the_flip_point() -> None:
    config = FlipConfig()
    ratios = flip_sharing_ratios(config, 10, flip_year=6.0)
    for i in range(6):
        assert ratios[i].income[TAX_EQUITY] == pytest.approx(0.99)
        assert ratios[i].cash[SPONSOR] == pytest.approx(0.01)
    for i in range(6, 10):
        assert ratios[i].income[TAX_EQUITY] == pytest.approx(0.05)
        assert ratios[i].cash[SPONSOR] == pytest.approx(0.95)


def test_a_fractional_flip_point_blends_the_straddled_year() -> None:
    """Continuity is what lets Brent's method solve for the flip point."""
    ratios = flip_sharing_ratios(FlipConfig(), 5, flip_year=2.25)
    assert ratios[1].income[TAX_EQUITY] == pytest.approx(0.99)
    # 0.25 of year 3 is pre-flip: 0.25*0.99 + 0.75*0.05
    assert ratios[2].income[TAX_EQUITY] == pytest.approx(0.25 * 0.99 + 0.75 * 0.05)
    assert ratios[3].income[TAX_EQUITY] == pytest.approx(0.05)


def test_every_ratio_set_sums_to_one() -> None:
    for flip in (0.0, 3.7, 12.0, 25.0):
        for r in flip_sharing_ratios(FlipConfig(), 25, flip_year=flip):
            for mapping in (r.income, r.loss, r.credit, r.cash):
                assert sum(mapping.values()) == pytest.approx(1.0, abs=1e-12)


# ---------------------------------------------------------------------------
# The yield-based solve
# ---------------------------------------------------------------------------


def test_yield_based_solve_hits_the_target_after_tax_irr() -> None:
    """At the solved flip point the investor's after-tax IRR IS the target."""
    ctx = make_context()
    config = FlipConfig(
        trigger=FlipTrigger.YIELD_BASED,
        target_after_tax_irr=0.07,
        investor_commitment=40_000_000.0,
    )
    solve = solve_flip_point(ctx, config, investor_commitment=40_000_000.0)
    assert solve.solved
    assert 0.0 < solve.flip_year < ctx.economics.n_years
    assert solve.achieved_investor_irr == pytest.approx(0.07, abs=1e-6)


def test_the_solved_flip_point_is_reproducible() -> None:
    ctx = make_context()
    config = FlipConfig(target_after_tax_irr=0.07, investor_commitment=40_000_000.0)
    a = solve_flip_point(ctx, config, investor_commitment=40_000_000.0)
    b = solve_flip_point(ctx, config, investor_commitment=40_000_000.0)
    assert a.flip_year == b.flip_year


def test_a_later_flip_monotonically_increases_the_investor_return() -> None:
    """The monotonicity property the root find depends on.

    A later flip leaves the investor holding 99% of income, loss, credits and
    cash for longer, so its after-tax IRR is strictly increasing in the flip
    point. If this ever fails, the bracket in ``solve_flip_point`` is not
    guaranteed to contain a single root and the solve is not trustworthy.
    """
    ctx = make_context()
    commitment = 40_000_000.0
    config = FlipConfig(investor_commitment=commitment)
    previous = None
    for flip_year in (1.0, 2.0, 4.0, 6.0, 9.0, 13.0, 18.0, 25.0):
        partnership = build_flip_partnership(
            ctx, config, flip_year=flip_year, investor_commitment=commitment
        )
        rate = irr(
            investor_after_tax_series(
                partnership, investor_commitment=commitment, tax_rate=0.21
            )
        )
        assert rate is not None
        if previous is not None:
            assert rate > previous, f"IRR fell going to flip year {flip_year}"
        previous = rate


def test_a_higher_target_yield_pushes_the_flip_point_out() -> None:
    ctx = make_context()
    commitment = 40_000_000.0
    years = []
    for target in (0.06, 0.07, 0.08):
        solve = solve_flip_point(
            ctx,
            FlipConfig(target_after_tax_irr=target, investor_commitment=commitment),
            investor_commitment=commitment,
        )
        assert solve.solved
        years.append(solve.flip_year)
    assert years[0] < years[1] < years[2]


def test_an_unreachable_target_is_reported_not_extrapolated() -> None:
    ctx = make_context()
    commitment = 40_000_000.0
    solve = solve_flip_point(
        ctx,
        FlipConfig(target_after_tax_irr=25.0, investor_commitment=commitment),
        investor_commitment=commitment,
    )
    assert solve.solved is False
    assert solve.flip_year == float(ctx.economics.n_years)
    assert "cannot reach" in solve.reason


def test_a_flip_with_no_investor_commitment_is_infeasible() -> None:
    ctx = make_context()
    result = run_flip(ctx, FlipConfig(investor_commitment=0.0))
    assert result.feasible is False
    assert "nothing to flip" in result.infeasible_reason


# ---------------------------------------------------------------------------
# Fixed-date variant
# ---------------------------------------------------------------------------


def test_fixed_date_flip_uses_the_stated_year_and_reports_the_achieved_yield() -> None:
    ctx = make_context()
    result = run_flip(
        ctx,
        FlipConfig(
            trigger=FlipTrigger.FIXED_DATE,
            fixed_flip_year=8.0,
            investor_commitment=40_000_000.0,
        ),
    )
    assert result.feasible
    assert result.flip_year == pytest.approx(8.0)
    assert result.investor_achieved_irr is not None


def test_fixed_date_and_yield_based_agree_when_the_date_is_the_solved_point() -> None:
    ctx = make_context()
    commitment = 40_000_000.0
    solve = solve_flip_point(
        ctx,
        FlipConfig(target_after_tax_irr=0.07, investor_commitment=commitment),
        investor_commitment=commitment,
    )
    fixed = run_flip(
        ctx,
        FlipConfig(
            trigger=FlipTrigger.FIXED_DATE,
            fixed_flip_year=solve.flip_year,
            investor_commitment=commitment,
        ),
    )
    assert fixed.investor_achieved_irr == pytest.approx(0.07, abs=1e-6)


# ---------------------------------------------------------------------------
# The capital-account engine inside the flip
# ---------------------------------------------------------------------------


def test_flip_capital_accounts_reconcile_in_every_period() -> None:
    ctx = make_context()
    commitment = 40_000_000.0
    partnership = build_flip_partnership(
        ctx, FlipConfig(), flip_year=7.0, investor_commitment=commitment
    )
    cum = {SPONSOR: 0.0, TAX_EQUITY: 0.0}
    dist = {SPONSOR: 0.0, TAX_EQUITY: 0.0}
    contrib = {SPONSOR: 0.0, TAX_EQUITY: 0.0}
    itc = {SPONSOR: 0.0, TAX_EQUITY: 0.0}
    for period in partnership.periods:
        for name in (SPONSOR, TAX_EQUITY):
            row = period.partner(name)
            cum[name] += row.book_allocation
            dist[name] += row.distributions
            contrib[name] += row.contributions
            itc[name] += row.itc_basis_reduction_share
            assert (
                row.capital_closing + dist[name] - contrib[name] + itc[name]
            ) == pytest.approx(cum[name], abs=CAPITAL_ACCOUNT_TOLERANCE)


def test_golden_flip_first_three_periods() -> None:
    """The first three periods of a flip, tied back to the project economics.

    Everything below is arithmetic on :class:`ProjectEconomics`, which is why
    it is checkable by hand: the sharing ratios are 99/1 throughout (the flip is
    set well past year 3), so each partner's allocation is simply its ratio
    times the partnership's book income, and the ITC basis reduction is half
    the credit split on the credit ratio.
    """
    ctx = make_context()
    econ = ctx.economics
    commitment = 40_000_000.0
    partnership = build_flip_partnership(
        ctx, FlipConfig(), flip_year=10.0, investor_commitment=commitment
    )
    book = econ.book_income()
    sponsor_commitment = econ.equity_at_cod - commitment

    # Period 1: contributions, the credit and its §50(c)(3) capital-account
    # adjustment, the year's loss, then the cash distribution.
    p0 = partnership.periods[0]
    te0, sp0 = p0.partner(TAX_EQUITY), p0.partner(SPONSOR)
    assert te0.contributions == pytest.approx(commitment, abs=TOL)
    assert sp0.contributions == pytest.approx(sponsor_commitment, abs=TOL)
    assert te0.credit_allocated == pytest.approx(0.99 * econ.itc_amount, abs=1e-3)
    assert te0.itc_basis_reduction_share == pytest.approx(
        0.99 * econ.itc_basis_reduction, abs=1e-3
    )
    assert econ.itc_basis_reduction == pytest.approx(
        0.5 * econ.itc_amount, abs=1e-3
    )
    assert te0.distributions == pytest.approx(
        0.99 * econ.distributable_cash[0], abs=1e-3
    )
    assert te0.capital_closing == pytest.approx(
        commitment
        - te0.itc_basis_reduction_share
        + te0.book_allocation
        - te0.distributions,
        abs=TOL,
    )
    assert te0.book_allocation + sp0.book_allocation == pytest.approx(
        book[0], abs=1e-3
    )

    # Periods 2 and 3: no credit, no contribution; a clean 99/1 split of book
    # income and of cash, and a capital account that rolls forward exactly.
    for i in (1, 2):
        te = partnership.periods[i].partner(TAX_EQUITY)
        sp = partnership.periods[i].partner(SPONSOR)
        assert te.contributions == 0.0
        assert te.credit_allocated == 0.0
        assert te.book_allocation == pytest.approx(0.99 * book[i], abs=1e-3)
        assert sp.book_allocation == pytest.approx(0.01 * book[i], abs=1e-3)
        assert te.distributions == pytest.approx(
            0.99 * econ.distributable_cash[i], abs=1e-3
        )
        assert te.capital_closing == pytest.approx(
            te.capital_opening + te.book_allocation - te.distributions, abs=TOL
        )


def test_the_itc_basis_reduction_is_half_the_credit_and_hits_capital_accounts() -> None:
    """§50(c)(3) and Treas. Reg. §1.704-1(b)(2)(iv)(j), tied together."""
    ctx = make_context()
    partnership = build_flip_partnership(
        ctx, FlipConfig(), flip_year=7.0, investor_commitment=40_000_000.0
    )
    p0 = partnership.periods[0]
    total = sum(p.itc_basis_reduction_share for p in p0.partners)
    assert total == pytest.approx(0.5 * ctx.economics.itc_amount, abs=1e-3)
    assert ctx.tax.depreciation.depreciable_basis == pytest.approx(
        ctx.economics.capex - total, abs=1.0
    )


# ---------------------------------------------------------------------------
# T-flip
# ---------------------------------------------------------------------------


def test_tflip_sells_the_credit_and_defers_the_flip_point() -> None:
    """The interaction that gives the T-flip its name.

    With the credit sold, the investor is buying depreciation and cash only, so
    it needs longer to reach the same target yield.
    """
    ctx = make_context()
    flip_cfg = FlipConfig(
        target_after_tax_irr=0.07, investor_commitment=40_000_000.0
    )
    pure = run_flip(ctx, flip_cfg)
    hybrid = run_tflip(
        ctx, TFlipConfig(flip=flip_cfg, transferred_credit_share=1.0)
    )
    assert hybrid.feasible
    assert hybrid.credit_transferred == pytest.approx(ctx.economics.itc_amount)
    assert hybrid.credit_retained == pytest.approx(0.0)
    assert hybrid.transfer_net_proceeds > 0.0
    assert hybrid.flip_year > pure.flip_year
    assert hybrid.detail["flip_year_deferred_by"] == pytest.approx(
        hybrid.flip_year - pure.flip_year, abs=1e-6
    )


def test_tflip_retains_the_untransferred_share_of_the_credit() -> None:
    ctx = make_context()
    hybrid = run_tflip(
        ctx,
        TFlipConfig(
            flip=FlipConfig(investor_commitment=40_000_000.0),
            transferred_credit_share=0.4,
        ),
    )
    assert hybrid.credit_transferred == pytest.approx(
        0.4 * ctx.economics.itc_amount, abs=1.0
    )
    assert hybrid.credit_retained == pytest.approx(
        0.6 * ctx.economics.itc_amount, abs=1.0
    )
    assert hybrid.key is StructureKey.T_FLIP


def test_the_basis_reduction_survives_a_full_credit_transfer() -> None:
    """§6418 moves the credit, not the §50(c)(3) basis adjustment."""
    ctx = make_context()
    hybrid = run_tflip(
        ctx,
        TFlipConfig(
            flip=FlipConfig(investor_commitment=40_000_000.0),
            transferred_credit_share=1.0,
        ),
    )
    assert hybrid.partnership is not None
    p0 = hybrid.partnership.periods[0]
    assert sum(p.credit_allocated for p in p0.partners) == pytest.approx(0.0, abs=1.0)
    assert sum(p.itc_basis_reduction_share for p in p0.partners) == pytest.approx(
        0.5 * ctx.economics.itc_amount, abs=1e-3
    )


def test_tflip_is_infeasible_without_a_credit() -> None:
    ctx = make_context(
        tax_project=storage_tax_project(
            macr_inputs=MacrInputs(
                method=MacrMethod.USER_ASSERTED, asserted_ratio=0.05
            )
        )
    )
    assert ctx.credit_is_zero
    result = run_tflip(ctx)
    assert result.feasible is False
    assert "no credit to transfer" in result.infeasible_reason.lower()


# ---------------------------------------------------------------------------
# Risk reporting
# ---------------------------------------------------------------------------


def test_a_flip_inside_the_recapture_period_is_flagged_as_blocking() -> None:
    ctx = make_context()
    result = run_flip(
        ctx,
        FlipConfig(
            trigger=FlipTrigger.FIXED_DATE,
            fixed_flip_year=3.0,
            investor_commitment=40_000_000.0,
        ),
    )
    codes = {f.code: f for f in result.risks}
    assert "flip_inside_recapture_period" in codes
    assert codes["flip_inside_recapture_period"].severity.value == "blocking"


def test_a_flip_after_year_five_carries_no_recapture_timing_flag() -> None:
    ctx = make_context()
    result = run_flip(
        ctx,
        FlipConfig(
            trigger=FlipTrigger.FIXED_DATE,
            fixed_flip_year=7.0,
            investor_commitment=40_000_000.0,
        ),
    )
    assert "flip_inside_recapture_period" not in {f.code for f in result.risks}
    assert "itc_recapture" in {f.code for f in result.risks}


def test_placeholder_assumptions_are_surfaced_as_warnings() -> None:
    ctx = make_context()
    result = run_flip(ctx, FlipConfig())
    assert any("PLACEHOLDER" in w for w in result.warnings)
