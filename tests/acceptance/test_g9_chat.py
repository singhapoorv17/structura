"""G9 — every chat turn is a model operation, or an explicit refusal."""

from __future__ import annotations

import datetime as dt

import pytest

TODAY = dt.date(2026, 8, 8)


@pytest.fixture
def spec():
    from intake import ContractSpec, DealSpec

    return DealSpec(
        asset_type="SOLAR_PLUS_STORAGE",
        size={"mwac": 430.0, "mwh": 340.0},
        state="TX",
        contract=ContractSpec("PPA", 15),
        cod="2028-06",
    )


MUTATIONS = [
    ("what if the PPA is 22 years?", "contract_tenor_years", 22.0),
    ("price $52/MWh", "contract_price", 52.0),
    ("capex $780m", "capex", 780_000_000.0),
    ("cod 2027-06", "cod", "2027-06"),
    ("make it 600 MWh", "size.mwh", 600.0),
    ("switch to a hedge", "contract_kind", "HEDGE"),
]


@pytest.mark.gate("G9.1")
@pytest.mark.parametrize("text,field,expected", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_a_recognised_turn_changes_the_deal_and_re_runs(spec, text, field, expected):
    from chat import ask
    from compare import build_comparison
    from intake import resolve

    turn = ask(spec, text, today=TODAY)
    assert turn.understood, f"{text!r} was not understood"
    assert turn.mutated, f"{text!r} produced no model delta"
    assert field in turn.delta
    assert turn.delta[field][1] == expected
    assert turn.spec is not None

    # The mutated deal must actually run.
    table = build_comparison(resolve(turn.spec, today=TODAY), today=TODAY)
    assert table.quantitative


@pytest.mark.gate("G9.1")
def test_a_turn_that_is_not_a_model_operation_is_refused(spec):
    """Prose with no model behind it is the failure mode this rail avoids."""
    from chat import ask

    for text in (
        "tell me about project finance",
        "what do you think of this deal",
        "explain tax equity to me",
        "",
    ):
        turn = ask(spec, text, today=TODAY)
        assert not turn.understood, f"{text!r} was answered without a model change"
        assert turn.answer == "", "a refusal must not carry an answer"
        assert turn.needed.strip(), f"{text!r} was refused with no explanation"


@pytest.mark.gate("G9.1")
def test_why_not_is_answered_from_the_gates_not_from_prose(spec):
    from chat import ask

    blocked = ask(spec, "why not a direct transfer?", today=TODAY)
    assert blocked.understood and blocked.intent == "why-not"
    assert "blocked" in blocked.answer
    # The answer carries the gate's own fact and its citation.
    assert "4 July 2026" in blocked.answer
    assert "(" in blocked.answer and ")" in blocked.answer

    available = ask(spec, "why not sale-leaseback?", today=TODAY)
    assert available.understood
    assert "available" in available.answer

    unknown = ask(spec, "why not a mezzanine bridge?", today=TODAY)
    assert not unknown.understood
    assert "does not name a structure" in unknown.needed


@pytest.mark.gate("G9.2")
def test_a_chat_change_is_badged_like_any_other_input(spec):
    from chat import ask
    from intake import resolve

    before = resolve(spec, today=TODAY)
    turn = ask(spec, "price $52/MWh", today=TODAY)
    after = resolve(turn.spec, today=TODAY)

    assert "contract_price" in after.inputs
    cell = after.inputs["contract_price"]
    assert cell.provenance.value == "stated", (
        "a value the user supplied through chat is still user input"
    )
    assert cell.value == 52.0
    assert after.confidence["total"] >= before.confidence["total"]
    assert after.confidence["total"] == sum(
        after.confidence[k]
        for k in ("stated", "benchmark", "assumed", "not_disclosed")
    )


@pytest.mark.gate("G9.2")
def test_a_no_op_turn_says_so_rather_than_pretending_to_re_run(spec):
    from chat import ask

    turn = ask(spec, "what if the PPA is 15 years?", today=TODAY)
    assert turn.understood
    assert not turn.mutated
    assert "already" in turn.answer
