"""The market-benchmark library.

These tests are provenance tests as much as value tests. SPEC.md §4.1 makes
currency the moat: every default must carry a source and a verified-on date, or
the claim that Structura is current is unsupported.
"""

from __future__ import annotations

from datetime import date

import pytest

from engine.defaults import (
    BASE_SPREAD_BPS,
    MIN_DSCR,
    Benchmark,
    DebtPhase,
    RevenueContractType,
    Technology,
    all_in_rate,
    all_in_spread_bps,
    benchmark_registry,
    merchant_spread_adder_bps,
    min_dscr,
)


def test_every_benchmark_carries_a_source_and_a_verification_date() -> None:
    for name, bench in benchmark_registry().items():
        assert bench.source, f"{name} has no source"
        assert isinstance(bench.verified_on, date), f"{name} has no verified_on"
        assert bench.verified_on <= date(2026, 12, 31)


def test_published_dscr_benchmarks_match_the_spec() -> None:
    """SPEC.md §2.7, from NRF's Cost of Capital: 2026 Outlook."""
    assert min_dscr(Technology.SOLAR).low == 1.25
    assert min_dscr(Technology.SOLAR).high == 1.30
    assert min_dscr(Technology.WIND).low == 1.35
    assert min_dscr(Technology.WIND).high == 1.40
    assert min_dscr(Technology.STORAGE).low == 1.15
    assert min_dscr(Technology.STORAGE).high == 1.20
    assert min_dscr(Technology.DATA_CENTER).value == 1.15
    assert (
        min_dscr(
            Technology.DATA_CENTER, RevenueContractType.HYPERSCALER_CONTRACTED
        ).value
        == 1.05
    )


def test_merchant_dscr_benchmarks_match_the_spec() -> None:
    m = RevenueContractType.MERCHANT_P50
    assert min_dscr(Technology.SOLAR, m).value == 1.75
    assert min_dscr(Technology.WIND, m).value == 1.80
    assert min_dscr(Technology.STORAGE, m).value == 2.00


def test_merchant_always_asks_more_coverage_than_contracted() -> None:
    for tech in (Technology.SOLAR, Technology.WIND, Technology.STORAGE):
        assert (
            min_dscr(tech, RevenueContractType.MERCHANT_P50).value
            > min_dscr(tech, RevenueContractType.CONTRACTED).value
        )


def test_unpublished_combination_raises_rather_than_guessing() -> None:
    with pytest.raises(KeyError, match="No published DSCR benchmark"):
        min_dscr(Technology.GAS)


def test_debt_pricing_matches_the_spec() -> None:
    assert BASE_SPREAD_BPS[DebtPhase.CONSTRUCTION].value == 150.0
    assert BASE_SPREAD_BPS[DebtPhase.CONSTRUCTION].low == 125.0
    assert BASE_SPREAD_BPS[DebtPhase.PERMANENT].low == 162.5
    assert BASE_SPREAD_BPS[DebtPhase.PERMANENT].high == 187.5


def test_merchant_spread_adders_match_the_published_bands() -> None:
    assert merchant_spread_adder_bps(0.00).value == 0.0
    assert merchant_spread_adder_bps(0.15).value == 25.0
    assert merchant_spread_adder_bps(0.35).value == 50.0
    with pytest.raises(ValueError):
        merchant_spread_adder_bps(1.5)


def test_interpolated_and_extrapolated_bands_are_flagged_as_such() -> None:
    """Numbers the engine invented must say so, or the citation is a lie."""
    assert "INTERPOLATED" in merchant_spread_adder_bps(0.25).note
    assert "EXTRAPOLATED" in merchant_spread_adder_bps(0.60).note


def test_all_in_rate_adds_base_and_spread() -> None:
    assert all_in_spread_bps(DebtPhase.PERMANENT, 0.15) == 200.0
    assert all_in_rate(DebtPhase.PERMANENT, 0.15, base_rate=0.04) == pytest.approx(
        0.06, abs=1e-12
    )


def test_sofr_placeholder_is_labelled_a_placeholder() -> None:
    """The engine ships no rates feed; that must be visible, not silent."""
    from engine.defaults import SOFR_PLACEHOLDER

    assert "PLACEHOLDER" in SOFR_PLACEHOLDER.source


def test_benchmark_range_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="range inverted"):
        Benchmark(1.0, "x", "test", date(2026, 8, 6), low=2.0, high=1.0)


def test_describe_is_auditable() -> None:
    text = min_dscr(Technology.SOLAR).describe()
    assert "1.3" in text
    assert "Norton Rose Fulbright" in text
    assert "2026-08-06" in text


def test_registry_covers_every_dscr_benchmark() -> None:
    registry = benchmark_registry()
    assert len(registry) >= len(MIN_DSCR) + len(BASE_SPREAD_BPS)
    assert "min_dscr.storage.contracted" in registry
    assert "max_gearing" in registry
