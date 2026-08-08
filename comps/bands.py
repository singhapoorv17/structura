"""Market bands — what the market prices for a shape of deal.

These are never attached to a named transaction. A band says what deals of a
given shape clear at; it does not say what any particular deal priced at, and
the serialiser keeps the two in separate response panels.

Every band below comes from a free, dated, publicly readable document.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

from comps.schema import MarketBand

NRF_COC = "Norton Rose Fulbright, 'Cost of Capital: 2026 Outlook'"
NRF_COC_URL = "https://www.projectfinance.law/publications/cost-of-capital-2026-outlook"
NRF_COC_DATE = dt.date(2026, 1, 29)

NRF_RFU = "Norton Rose Fulbright, 'Renewables Financing Update'"
NRF_RFU_DATE = dt.date(2026, 6, 9)

#: LevelTen publishes the index quarterly. The figures themselves sit behind
#: its Report Center, so the citation is to the trade press that carries them,
#: with LevelTen named as the originator.
LEVELTEN_VIA_PVMAG = "pv magazine USA, reporting the LevelTen PPA Price Index"
LEVELTEN_URL = (
    "https://pv-magazine-usa.com/2026/07/27/solar-ppa-prices-dip-in-q2-while-"
    "wind-climbs-as-july-4-tax-credit-deadline-looms-reports-levelten/"
)
LEVELTEN_DATE = dt.date(2026, 7, 27)
LEVELTEN_ORIGIN = "LevelTen Energy, North American PPA Price Index, Q2 2026"

CPUC_RA = (
    "California Public Utilities Commission, Energy Division staff report on "
    "the 2024-2025 Resource Adequacy Market Price Benchmark"
)
CPUC_RA_URL = (
    "https://docs.cpuc.ca.gov/PublishedDocs/Efile/G000/M557/K608/557608990.PDF"
)
CPUC_RA_DATE = dt.date(2025, 2, 26)

CRUX = "Crux, '1Q 2026 market update'"
CRUX_URL = "https://www.crux.com/insights/1q2026-market-update-qa-josh-price"
CRUX_DATE = dt.date(2026, 5, 4)


def _nrf(key, label, applies_to, low, high, unit, note=""):
    return MarketBand(
        key=key,
        label=label,
        applies_to=tuple(applies_to),
        low=low,
        high=high,
        unit=unit,
        source=NRF_COC,
        source_url=NRF_COC_URL,
        source_date=NRF_COC_DATE,
        note=note,
    )


BANDS: Final[tuple[MarketBand, ...]] = (
    # -- debt pricing ------------------------------------------------------
    _nrf(
        "spread.construction",
        "Construction loan spread",
        ("solar", "wind", "storage", "digital"),
        125.0,
        150.0,
        "bps over SOFR",
        "150bp is the general case; 125-137.5bp is the aggressive end.",
    ),
    _nrf(
        "spread.term",
        "Term loan spread",
        ("solar", "wind", "storage", "digital"),
        162.5,
        187.5,
        "bps over SOFR",
    ),
    _nrf(
        "spread.bridge_insured",
        "Tax credit bridge, insured",
        ("solar", "wind", "storage"),
        150.0,
        150.0,
        "bps over SOFR",
        "Quoted alongside a 98% advance rate.",
    ),
    _nrf(
        "spread.bridge_uncovered",
        "Tax credit bridge, uncovered",
        ("solar", "wind", "storage"),
        225.0,
        225.0,
        "bps over SOFR",
        "Quoted alongside a 75% advance rate.",
    ),
    _nrf(
        "spread.pre_ntp",
        "Pre-NTP facility",
        ("solar", "wind", "storage"),
        350.0,
        450.0,
        "bps over SOFR",
    ),
    _nrf(
        "spread.borrowing_base",
        "Borrowing base facility",
        ("solar", "wind", "storage"),
        450.0,
        600.0,
        "bps over SOFR",
    ),
    _nrf(
        "spread.pre_ntp_high_risk",
        "High-risk pre-NTP facility",
        ("solar", "wind", "storage"),
        600.0,
        800.0,
        "bps over SOFR",
    ),
    # -- advance rates -----------------------------------------------------
    _nrf(
        "advance.bridge_insured",
        "Insured tax credit bridge advance rate",
        ("solar", "wind", "storage"),
        0.98,
        0.98,
        "of projected proceeds",
    ),
    _nrf(
        "advance.bridge_uncovered",
        "Uncovered tax credit bridge advance rate",
        ("solar", "wind", "storage"),
        0.75,
        0.75,
        "of projected proceeds",
    ),
    # -- coverage ----------------------------------------------------------
    _nrf("dscr.solar", "Minimum DSCR, solar P50", ("solar",), 1.25, 1.30, "x"),
    _nrf("dscr.wind", "Minimum DSCR, wind", ("wind",), 1.35, 1.40, "x"),
    _nrf("dscr.storage", "Minimum DSCR, storage", ("storage",), 1.15, 1.20, "x"),
    _nrf(
        "dscr.data_centre",
        "Minimum DSCR, data centre",
        ("digital",),
        1.05,
        1.15,
        "x",
        "1.15x is the general case; portfolio leases price to 1.05x.",
    ),
    # -- tax credit pricing ------------------------------------------------
    MarketBand(
        key="credit_price.itc_2026",
        label="ITC transfer price, 2026 vintage",
        applies_to=("solar", "storage", "digital"),
        low=0.895,
        high=0.895,
        unit="$ per credit dollar",
        source=CRUX,
        source_url=CRUX_URL,
        source_date=CRUX_DATE,
        note="2025 vintage averaged $0.909, utility-scale to $0.926.",
    ),
    MarketBand(
        key="credit_price.ptc_2026",
        label="PTC transfer price, 2026 vintage",
        applies_to=("solar", "wind"),
        low=0.917,
        high=0.917,
        unit="$ per credit dollar",
        source=CRUX,
        source_url=CRUX_URL,
        source_date=CRUX_DATE,
    ),
    # -- contract pricing --------------------------------------------------
    #
    # The largest single input in the model, and until now the least sourced.
    # LevelTen's index is the market reference for PPA pricing; the CPUC
    # benchmark is the only free, audited capacity price in the US, and it is
    # California-specific.
    MarketBand(
        key="contract_price.solar_ppa",
        label="Solar PPA price",
        applies_to=("solar",),
        low=61.40,
        high=64.49,
        point=61.40,
        unit="$/MWh",
        source=LEVELTEN_VIA_PVMAG,
        source_url=LEVELTEN_URL,
        source_date=LEVELTEN_DATE,
        restates=LEVELTEN_ORIGIN,
        note=(
            "Q2 2026 market-averaged benchmark of $61.40, against $64.49 in "
            "Q1 — the first quarterly fall in two years. Continental North "
            "America; individual markets diverge widely from this."
        ),
    ),
    MarketBand(
        key="contract_price.wind_ppa",
        label="Wind PPA price",
        applies_to=("wind",),
        low=79.40,
        high=83.79,
        point=83.79,
        unit="$/MWh",
        source=LEVELTEN_VIA_PVMAG,
        source_url=LEVELTEN_URL,
        source_date=LEVELTEN_DATE,
        restates=LEVELTEN_ORIGIN,
        note=(
            "Q2 2026 benchmark of $83.79, up 5.5% on the quarter and 17.5% on "
            "the year. Continental North America."
        ),
    ),
    MarketBand(
        key="capacity_price.storage_ra",
        label="Storage capacity payment",
        applies_to=("storage",),
        low=10.24,
        high=26.26,
        point=14.19,
        unit="$/kW-month",
        source=CPUC_RA,
        source_url=CPUC_RA_URL,
        source_date=CPUC_RA_DATE,
        note=(
            "2024 final system Resource Adequacy market price benchmarks "
            "across the California IOUs, weighted average $14.19. This is a "
            "California capacity price, not a tolling price, and not a "
            "national figure: no free source publishes toll pricing. The "
            "commission notes forecast system RA now surpassing $40/kW-month "
            "on a subset of transactions it considers may reflect market "
            "power."
        ),
    ),

    # -- ticket sizes ------------------------------------------------------
    MarketBand(
        key="ticket.tax_equity_minimum",
        label="Tax equity minimum ticket",
        applies_to=("solar", "wind", "storage"),
        low=200_000_000.0,
        high=300_000_000.0,
        unit="USD",
        source=NRF_RFU,
        source_url="https://www.projectfinance.law/publications/",
        source_date=NRF_RFU_DATE,
        note="JPMorgan, quoted on panel: 'two to three hundred million'.",
    ),
    MarketBand(
        key="ticket.lender_final_hold_floor",
        label="Lender final hold floor",
        applies_to=("solar", "wind", "storage", "digital"),
        low=75_000_000.0,
        high=75_000_000.0,
        unit="USD",
        source=NRF_RFU,
        source_url="https://www.projectfinance.law/publications/",
        source_date=NRF_RFU_DATE,
        note="Rabobank: below this a final hold is 'hard to justify'.",
    ),
)

BY_KEY: Final[dict[str, MarketBand]] = {b.key: b for b in BANDS}


def bands_for(family: str) -> tuple[MarketBand, ...]:
    """Bands that apply to a technology family."""
    return tuple(b for b in BANDS if family in b.applies_to)
