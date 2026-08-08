"""Formula-versus-engine agreement: the test that makes the export claim honest.

The Python numeric model and the emitted Excel model must
agree within a documented tolerance, asserted in tests. Excel is not available
here, so the workbook is read back and its **formula graph is evaluated** by
``test_export_evaluator`` - iteratively, exactly as Excel does with
``iterate="1"`` - and the result is compared line by line against the engine.

That is a strictly stronger test than checking that the cells contain strings
beginning with ``=``. It proves that the arithmetic the formulas encode is the
arithmetic the engine performs, that the circular funding chain converges, and
that it converges to the same fixed point Brent's method finds in Python.

Tolerances
----------
Money is compared at a **relative 1e-7** - a cent on a nine-figure facility -
because the two paths differ only in floating-point association order (Excel
sums a row left to right; the engine accumulates in a Python loop). Ratios and
rates are compared at an **absolute 1e-9**. Neither is a modelling tolerance;
both are floating-point noise floors.
"""

from __future__ import annotations

import pytest

from engine import (
    AmortizationStyle,
    DebtTerms,
    ProductionCase,
    ProjectInputs,
    TaxTreatment,
    Technology,
)
from test_export_evaluator import evaluated_case

#: Relative tolerance on currency amounts.
MONEY_REL = 1e-7
#: Absolute tolerance on a coverage ratio, an IRR or a percentage.
RATIO_ABS = 1e-9


# ---------------------------------------------------------------------------
# The deal shapes exercised. Each one puts a different test in the binding
# seat, or a different branch of the formula chain in play.
# ---------------------------------------------------------------------------

CASES: dict[str, tuple[ProjectInputs, DebtTerms]] = {
    # Gearing-bound: the default deal. Exercises the full circular chain,
    # because the gearing cap is a function of total project cost.
    "base": (ProjectInputs(), DebtTerms()),
    # DSCR-bound: a capex-heavy deal where the gearing cap is slack, so the
    # sculpt sets the quantum outright and every DSCR lands on target.
    "dscr_bound": (ProjectInputs(capex=400_000_000.0), DebtTerms()),
    # Level payment and fixed principal: the two CHOOSE() branches that are not
    # the default.
    "level": (
        ProjectInputs(capex=400_000_000.0),
        DebtTerms(amortization=AmortizationStyle.LEVEL),
    ),
    "fixed_principal": (
        ProjectInputs(capex=400_000_000.0),
        DebtTerms(amortization=AmortizationStyle.FIXED_PRINCIPAL),
    ),
    # A two-year interest-only holiday: exercises the grace branch of the
    # service formula and the interest-only coverage cap.
    "grace": (
        ProjectInputs(capex=400_000_000.0),
        DebtTerms(grace_period_months=24),
    ),
    # Semi-annual periods: every /Periods_Per_Year and every months-to-periods
    # conversion in the workbook.
    "semi_annual": (
        ProjectInputs(periods_per_year=2, capex=400_000_000.0),
        DebtTerms(),
    ),
    # A merchant tail: contracted for ten years, merchant thereafter, so CFADS
    # steps down and the sculpted profile is genuinely shaped rather than flat.
    "merchant_tail": (
        ProjectInputs(
            capex=400_000_000.0,
            contract_years=10.0,
            contracted_share=0.8,
            merchant_price=38.0,
            technology=Technology.SOLAR,
        ),
        DebtTerms(target_dscr=1.35),
    ),
    # Tail-bound: a 24-year tenor against a 25-year life and a 2-year tail
    # requirement, so the tenor is cut and the tail test binds.
    "tail_bound": (
        ProjectInputs(capex=400_000_000.0),
        DebtTerms(tenor_years=24.0),
    ),
    # LLCR floor set high enough to bind before DSCR or gearing.
    "llcr_bound": (
        ProjectInputs(capex=400_000_000.0),
        DebtTerms(min_llcr=2.0),
    ),
    # A 50% cash sweep: exercises the inverse-order prepayment mechanics in the
    # waterfall, which is the hardest thing on the sheet to express in formulas.
    "sweep": (ProjectInputs(), DebtTerms(cash_sweep_pct=0.5)),
    # Full project-level tax: switches on the second circularity, where cash
    # tax depends on interest which depends on the debt which depends on CFADS.
    "full_tax": (
        ProjectInputs(tax_treatment=TaxTreatment.FULL, capex=400_000_000.0),
        DebtTerms(),
    ),
    # A P90 storage deal on a time-varying DSCR target - 1.20x while
    # contracted, 1.60x once the offtake rolls off.
    "time_varying_dscr": (
        ProjectInputs(
            capex=400_000_000.0,
            production_p90=360_000.0,
            production_case=ProductionCase.P90,
            contract_years=12.0,
        ),
        DebtTerms(
            target_dscr=tuple([1.20] * 12 + [1.60] * 6),
            tenor_years=18.0,
        ),
    ),
}

ALL_CASES = sorted(CASES)


def _case(name: str):
    project, terms = CASES[name]
    return evaluated_case(name, project, terms)


def _assert_series(got, want, *, rel=MONEY_REL, abs_=1e-6, label=""):
    assert len(got) >= len(want), f"{label}: {len(got)} values vs {len(want)}"
    for i, expected in enumerate(want):
        assert got[i] == pytest.approx(expected, rel=rel, abs=abs_), (
            f"{label} period {i + 1}: workbook {got[i]!r} vs engine {expected!r}"
        )


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALL_CASES)
def test_the_formula_graph_converges(name):
    """The circular chain must settle - and settle well inside Excel's budget.

    ``iterateCount`` is 100. This evaluator uses a plain column-major sweep,
    which is a cruder schedule than Excel's dependency chain, so its iteration
    count is an upper bound on what Excel needs.
    """
    model, _ = _case(name)
    assert model.iterations < 100, (
        f"{name} took {model.iterations} passes; Excel's iterateCount is 100"
    )
    assert model.residual <= 1e-6


# ---------------------------------------------------------------------------
# Funding: the circularity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALL_CASES)
def test_debt_quantum_matches_the_engine(name):
    model, (solution, _, _) = _case(name)
    assert model.name("Senior_Debt") == pytest.approx(
        solution.debt_size, rel=MONEY_REL
    )


@pytest.mark.parametrize("name", ALL_CASES)
def test_binding_constraint_matches_the_engine(name):
    model, (solution, _, _) = _case(name)
    assert model.name("Binding_Constraint") == (
        solution.sizing.binding_constraint.value.upper()
    )


@pytest.mark.parametrize("name", ALL_CASES)
def test_construction_funding_matches_the_engine(name):
    """IDC, fees, DSRA, total project cost, gearing and the equity cheque.

    This is the fixed point Brent's method solves in ``engine/circularity.py``
    and Excel resolves by iteration. Both must land on the same point.
    """
    model, (solution, _, _) = _case(name)
    construction = solution.construction
    for label, got, want in (
        ("IDC", model.name("IDC"), construction.idc),
        (
            "upfront fee",
            model.name("Upfront_Fee_Amount"),
            construction.upfront_fee,
        ),
        (
            "commitment fee",
            model.name("Commitment_Fee_Total"),
            construction.commitment_fee,
        ),
        ("initial DSRA", model.name("DSRA_Initial"), construction.dsra_initial),
        (
            "total project cost",
            model.name("Total_Project_Cost"),
            construction.total_project_cost,
        ),
        ("debt at COD", model.name("Debt_At_COD"), construction.debt_at_cod),
        (
            "equity at COD",
            model.name("Equity_At_COD"),
            construction.equity_at_cod,
        ),
    ):
        assert got == pytest.approx(want, rel=MONEY_REL, abs=1e-4), label
    assert model.name("Gearing_Achieved") == pytest.approx(
        construction.gearing, abs=1e-9
    )


@pytest.mark.parametrize("name", ALL_CASES)
def test_the_circularity_check_row_is_zero(name):
    """The workbook asserts its own convergence, and the assertion holds."""
    model, _ = _case(name)
    assert abs(model.name("Circularity_Check")) < 1e-4


@pytest.mark.parametrize("name", ALL_CASES)
def test_sources_equal_uses(name):
    model, _ = _case(name)
    assert model.name("Total_Sources") == pytest.approx(
        model.name("Total_Uses"), rel=MONEY_REL
    )


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALL_CASES)
def test_operating_model_matches_the_engine(name):
    model, (solution, _, _) = _case(name)
    cashflow = solution.cashflow
    _assert_series(model.series("Revenue_Series"), cashflow.revenue, label="revenue")
    _assert_series(model.series("Opex_Series"), cashflow.opex, label="opex")
    _assert_series(model.series("EBITDA_Series"), cashflow.ebitda, label="EBITDA")
    _assert_series(model.series("Cash_Tax_Series"), cashflow.cash_tax, label="tax")
    _assert_series(model.series("CFADS_Series"), cashflow.cfads, label="CFADS")


@pytest.mark.parametrize("name", ALL_CASES)
def test_the_cfads_identity_holds_on_the_sheet(name):
    model, _ = _case(name)
    for i, value in enumerate(model.series("CFADS_Check_Series")):
        assert abs(value) < 1e-6, f"CFADS identity broken in period {i + 1}"


# ---------------------------------------------------------------------------
# The debt schedule - the heart of the claim
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALL_CASES)
def test_debt_schedule_matches_the_engine(name):
    """Opening balance, interest, debt service, principal, closing balance.

    Every one of these is an Excel formula reading the cell to its left or
    above; none is a pasted number. Reproducing the engine's schedule from that
    chain is the proof that the workbook is a model rather than a report.
    """
    model, (solution, _, _) = _case(name)
    debt = solution.debt.debt if hasattr(solution, "debt") else solution.sizing.debt
    n = debt.n_periods
    for label, series, expected in (
        ("opening balance", "Debt_Opening_Balance_Series", debt.opening_balance),
        ("interest", "Senior_Interest_Series", debt.interest),
        ("debt service", "Senior_Debt_Service_Series", debt.debt_service),
        ("principal", "Senior_Principal_Series", debt.principal),
        ("closing balance", "Debt_Closing_Balance_Series", debt.closing_balance),
    ):
        _assert_series(
            model.series(series)[:n], list(expected), label=f"{name} {label}"
        )


@pytest.mark.parametrize("name", ALL_CASES)
def test_the_encoded_arithmetic_is_the_arithmetic_a_lender_expects(name):
    """Re-derive the schedule from the workbook's own numbers.

    Independently of the engine: interest must be the rate times the opening
    balance, principal must be debt service less interest, and the closing
    balance must be the opening balance less principal. Then the chain must
    terminate at zero. This is the identity a credit officer checks by hand.
    """
    model, (solution, _, _) = _case(name)
    rate = model.name("Rate_Per_Period")
    n = int(model.name("Debt_Periods"))
    opening = model.series("Debt_Opening_Balance_Series")
    interest = model.series("Senior_Interest_Series")
    service = model.series("Senior_Debt_Service_Series")
    principal = model.series("Senior_Principal_Series")
    closing = model.series("Debt_Closing_Balance_Series")

    balance = model.name("Senior_Debt")
    for t in range(n):
        assert opening[t] == pytest.approx(balance, rel=MONEY_REL, abs=1e-4)
        assert interest[t] == pytest.approx(
            rate * opening[t], rel=MONEY_REL, abs=1e-4
        ), f"period {t + 1}: interest is not rate x opening balance"
        assert principal[t] == pytest.approx(
            service[t] - interest[t], rel=MONEY_REL, abs=1e-4
        ), f"period {t + 1}: principal is not debt service less interest"
        assert closing[t] == pytest.approx(
            opening[t] - principal[t], rel=MONEY_REL, abs=1e-4
        ), f"period {t + 1}: closing is not opening less principal"
        balance = closing[t]

    assert balance == pytest.approx(0.0, abs=1e-4), (
        "the facility does not amortise to zero - the PV identity behind the "
        "sculpt is broken"
    )
    assert sum(principal[:n]) == pytest.approx(
        solution.debt_size, rel=MONEY_REL
    ), "principal repaid does not sum to the facility drawn"


@pytest.mark.parametrize("name", ALL_CASES)
def test_dscr_is_computed_in_excel_and_matches_the_engine(name):
    model, (solution, _, _) = _case(name)
    debt = solution.sizing.debt
    n = debt.n_periods
    got = model.series("DSCR_Series")[:n]
    _assert_series(got, list(debt.dscr), rel=1e-9, abs_=RATIO_ABS, label="DSCR")
    cfads = model.series("CFADS_Series")
    service = model.series("Senior_Debt_Service_Series")
    for t in range(n):
        assert got[t] == pytest.approx(cfads[t] / service[t], rel=1e-9), (
            f"period {t + 1}: the DSCR row is not CFADS / debt service"
        )


@pytest.mark.parametrize("name", ALL_CASES)
def test_coverage_ratios_match_the_engine(name):
    model, (solution, _, _) = _case(name)
    sizing = solution.sizing
    assert model.name("Min_DSCR_Achieved") == pytest.approx(
        sizing.min_dscr, abs=1e-9
    )
    assert model.name("LLCR_At_COD") == pytest.approx(sizing.llcr, abs=1e-9)
    assert model.name("PLCR_At_COD") == pytest.approx(sizing.plcr, abs=1e-9)
    assert model.name("Debt_WAL_Years") == pytest.approx(
        sizing.debt.average_life_years, abs=1e-9
    )


@pytest.mark.parametrize("name", ALL_CASES)
def test_dsra_targets_match_the_engine(name):
    """The reserve is forward-looking, and the engine's index 0 is the balance
    required at COD - which is one of the uses that makes funding circular."""
    model, (solution, _, _) = _case(name)
    targets = solution.sizing.dsra_target
    n = solution.sizing.debt.n_periods
    assert model.name("DSRA_Initial") == pytest.approx(
        targets[0], rel=MONEY_REL, abs=1e-4
    )
    _assert_series(
        model.series("DSRA_Target_Series")[:n], list(targets[1:]), label="DSRA"
    )


# ---------------------------------------------------------------------------
# Waterfall
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALL_CASES)
def test_waterfall_matches_the_engine(name):
    model, (_, waterfall, _) = _case(name)
    _assert_series(
        model.series("Distributions_Series"),
        list(waterfall.distributions),
        label="distributions",
    )
    _assert_series(
        model.series("DSRA_Closing_Series"),
        list(waterfall.dsra_closing),
        label="DSRA closing",
    )
    _assert_series(
        model.series("Waterfall_Closing_Balance_Series"),
        list(waterfall.closing_balance),
        label="senior closing balance",
    )


@pytest.mark.parametrize("name", ALL_CASES)
def test_the_waterfall_conserves_cash_in_every_period(name):
    """The single most valuable assertion in a waterfall, restated in Excel."""
    model, _ = _case(name)
    for i, value in enumerate(model.series("Cash_Check_Series")):
        assert abs(value) < 1e-4, f"cash not conserved in period {i + 1}: {value}"


# ---------------------------------------------------------------------------
# Returns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALL_CASES)
def test_equity_cashflows_match_the_engine(name):
    model, (_, _, returns) = _case(name)
    _assert_series(
        model.series("Equity_Cashflow_Series"),
        list(returns.equity_cashflows),
        label="equity cashflow",
    )


@pytest.mark.parametrize("name", ALL_CASES)
def test_excel_own_irr_npv_and_payback_match_the_engine(name):
    """IRR, NPV and payback are computed by Excel's functions over the
    workbook's own rows - not pasted from Python - and still agree."""
    model, (_, _, returns) = _case(name)
    assert model.name("Equity_IRR") == pytest.approx(
        returns.equity_irr_post_tax, abs=1e-9
    )
    assert model.name("Equity_NPV") == pytest.approx(
        returns.equity_npv, rel=1e-7, abs=1e-4
    )
    assert model.name("Equity_MOIC") == pytest.approx(
        returns.equity_moic, rel=1e-9
    )
    payback = model.name("Equity_Payback_Years")
    if returns.payback_years is None:
        # The engine returns None when cumulative cash never turns positive.
        # The workbook says so in words rather than printing a wrong number.
        assert isinstance(payback, str) and payback.startswith("not within"), payback
    else:
        assert payback == pytest.approx(returns.payback_years, abs=1e-7)


@pytest.mark.parametrize("name", ALL_CASES)
def test_cost_of_capital_matches_the_engine(name):
    model, (_, _, returns) = _case(name)
    assert model.name("Effective_Cost_Of_Debt") == pytest.approx(
        returns.effective_cost_of_debt, abs=1e-9
    )
    assert model.name("After_Tax_Cost_Of_Debt") == pytest.approx(
        returns.after_tax_cost_of_debt, abs=1e-9
    )
    assert model.name("WACC") == pytest.approx(
        returns.weighted_average_cost_of_capital, abs=1e-9
    )


# ---------------------------------------------------------------------------
# The point of the whole exercise
# ---------------------------------------------------------------------------


def test_changing_the_dscr_input_re_sizes_the_facility():
    """The golden test, run against the formula graph.

    Change the DSCR target cell - nothing else - and the debt quantum, the
    sculpted profile, IDC, the equity cheque and the sponsor's IRR must all
    move, consistently, to the answer the engine gives for the new target.
    """
    from engine import run_model
    from test_export_evaluator import EvaluatedWorkbook, build_case

    path, _ = build_case("dscr_bound", *CASES["dscr_bound"])
    model = EvaluatedWorkbook.load(path)

    target_cell = model.names["Target_DSCR"]
    sheet, _, address = target_cell.partition("!")
    key = (sheet.strip("'"), address.replace("$", ""))
    assert key in model.statics, "Target_DSCR must be an input, not a formula"

    model.values[key] = 1.50
    model.calculate()

    project, terms = CASES["dscr_bound"]
    from dataclasses import replace

    expected_solution, _, expected_returns = run_model(
        project, replace(terms, target_dscr=1.50)
    )
    assert model.name("Senior_Debt") == pytest.approx(
        expected_solution.debt_size, rel=MONEY_REL
    )
    assert model.name("Min_DSCR_Achieved") == pytest.approx(1.50, abs=1e-9)
    assert model.name("IDC") == pytest.approx(
        expected_solution.construction.idc, rel=MONEY_REL
    )
    assert model.name("Equity_At_COD") == pytest.approx(
        expected_solution.construction.equity_at_cod, rel=MONEY_REL
    )
    assert model.name("Equity_IRR") == pytest.approx(
        expected_returns.equity_irr_post_tax, abs=1e-9
    )


def test_changing_the_interest_rate_moves_idc_and_the_debt_quantum():
    """A second driver, to show the first was not a coincidence."""
    from dataclasses import replace

    from engine import run_model
    from test_export_evaluator import EvaluatedWorkbook, build_case

    path, _ = build_case("dscr_bound", *CASES["dscr_bound"])
    model = EvaluatedWorkbook.load(path)
    sheet, _, address = model.names["Interest_Rate"].partition("!")
    model.values[(sheet.strip("'"), address.replace("$", ""))] = 0.0800
    model.calculate()

    project, terms = CASES["dscr_bound"]
    expected, _, _ = run_model(project, replace(terms, interest_rate=0.0800))
    assert model.name("Senior_Debt") == pytest.approx(
        expected.debt_size, rel=MONEY_REL
    )
    assert model.name("IDC") == pytest.approx(
        expected.construction.idc, rel=MONEY_REL
    )


def test_switching_the_amortisation_style_re_sizes_the_facility():
    """``Amort_Style_Code`` drives a live ``CHOOSE()``, not a re-export."""
    from dataclasses import replace

    from engine import run_model
    from test_export_evaluator import EvaluatedWorkbook, build_case

    path, _ = build_case("dscr_bound", *CASES["dscr_bound"])
    model = EvaluatedWorkbook.load(path)
    sheet, _, address = model.names["Amort_Style_Code"].partition("!")
    model.values[(sheet.strip("'"), address.replace("$", ""))] = 2  # level payment
    model.calculate()

    project, terms = CASES["dscr_bound"]
    expected, _, _ = run_model(
        project, replace(terms, amortization=AmortizationStyle.LEVEL)
    )
    assert model.name("Senior_Debt") == pytest.approx(
        expected.debt_size, rel=MONEY_REL
    )
