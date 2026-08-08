"""Shared fixtures and gate bookkeeping for the acceptance suite.

Every test here carries a ``gate`` marker naming the criterion it asserts. The
hook below stamps those ids onto the report so the scorer can group outcomes by
gate rather than by test.
"""

from __future__ import annotations

import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent


def pytest_collection_modifyitems(items):
    """Mark the tests in this package, and only these.

    The hook is handed every collected item in the session, not just the ones
    under this conftest, so the path check is what keeps the marker local.
    """
    for item in items:
        path = pathlib.Path(str(item.fspath)).resolve()
        if path.is_relative_to(HERE):
            item.add_marker(pytest.mark.acceptance)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    report.gate_ids = [
        arg
        for marker in item.iter_markers(name="gate")
        for arg in marker.args
    ]


# ---------------------------------------------------------------------------
# Canonical deals — the six specs every phase is scored against
# ---------------------------------------------------------------------------


CANONICAL_SPECS = [
    {
        "key": "ercot_solar_storage",
        "asset_type": "SOLAR_PLUS_STORAGE",
        "size": {"mwac": 430.0, "mwh": 340.0},
        "state": "TX",
        "contract": {"kind": "PPA", "tenor_years": 15},
        "cod": "2028-06",
    },
    {
        "key": "standalone_storage_toll",
        "asset_type": "STORAGE",
        "size": {"mw": 150.0, "mwh": 300.0},
        "state": "CA",
        "contract": {"kind": "TOLLING", "tenor_years": 15},
        "cod": "2028-01",
    },
    {
        "key": "onshore_wind_hedge",
        "asset_type": "WIND",
        "size": {"mw": 300.0},
        "state": "OK",
        "contract": {"kind": "HEDGE", "tenor_years": 12},
        "cod": "2027-12",
    },
    {
        "key": "dg_portfolio",
        "asset_type": "SOLAR",
        "size": {"mwac": 120.0, "asset_count": 55},
        "state": "NY",
        "contract": {"kind": "PPA", "tenor_years": 20},
        "cod": "2027-06",
    },
    {
        "key": "hyperscale_data_centre",
        "asset_type": "DATA_CENTRE",
        "size": {"it_mw": 250.0},
        "state": "VA",
        "contract": {"kind": "HYPERSCALE_LEASE", "tenor_years": 15},
        "cod": "2028-09",
    },
    {
        "key": "ai_compute_lease",
        "asset_type": "AI_COMPUTE",
        "size": {"units": 1_000_000, "mw": 1000.0},
        "state": "US",
        "contract": {"kind": "EQUIPMENT_LEASE", "tenor_years": None},
        "cod": "2026-06",
    },
]


@pytest.fixture(scope="session")
def canonical_specs():
    return CANONICAL_SPECS


@pytest.fixture(scope="session", params=CANONICAL_SPECS, ids=lambda s: s["key"])
def canonical_spec(request):
    return request.param
