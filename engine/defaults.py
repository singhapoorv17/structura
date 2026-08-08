"""Market-benchmark default library and engine-wide numerical constants.

Every benchmark in this module is a *public* market data point carried with its
source and the date it was verified. Nothing here comes from a real transaction
or from any employer's data.

The benchmarks are the August-2026 market as reported in Norton Rose Fulbright's
*Cost of Capital: 2026 Outlook* (published 2026-01-29), which is the standard
annual practitioner survey of energy project-finance terms.

Design rule: **no magic numbers anywhere else in the engine.** Tolerances,
day-count conventions and market defaults all live here so that a reviewer can
audit every assumption from one file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Final

# ---------------------------------------------------------------------------
# Numerical / calendar constants
# ---------------------------------------------------------------------------

MONTHS_PER_YEAR: Final[int] = 12

#: Absolute cash tolerance, in currency units, used by conservation-of-cash and
#: full-amortisation assertions. Project cashflows are denominated in whole
#: dollars and are typically 1e8-1e9, so 1e-6 is ~1e-15 relative - i.e. floating
#: point noise only.
CASH_TOLERANCE: Final[float] = 1e-6

#: Absolute tolerance on a coverage ratio (DSCR/LLCR/PLCR) comparison.
RATIO_TOLERANCE: Final[float] = 1e-9

#: Default convergence tolerance (currency units) for the construction-funding
#: circularity solve (IDC <-> debt size <-> fees <-> DSRA).
CIRCULARITY_TOLERANCE: Final[float] = 1e-6

#: Hard iteration cap for the circularity solver. Chosen well above the ~40
#: iterations Brent's method needs for a 1e-6 tolerance on a $1bn bracket.
CIRCULARITY_MAX_ITER: Final[int] = 200

#: Bracket padding for the outer debt-size root-find. The root always lies in
#: [0, D_dscr]; we search [0, D_dscr * (1 + eps)] so a root exactly at the upper
#: bound is not lost to floating-point.
BRACKET_PADDING: Final[float] = 1e-9

#: Sentinel for "no numeric limit applies to this sizing test".
NO_LIMIT: Final[float] = float("inf")


# ---------------------------------------------------------------------------
# Benchmark container
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Benchmark:
    """A single market data point with its provenance.

    Attributes
    ----------
    value:
        The point estimate the engine uses when the caller supplies nothing.
    low, high:
        The published range. ``value`` is normally the conservative (lender-
        friendly) end for DSCR and the mid-point for pricing.
    unit:
        Free text, e.g. ``"x"`` for a coverage ratio, ``"bps over SOFR"``.
    source:
        Citation string. Must identify a *public* document.
    verified_on:
        Date the citation was checked. Every default carries the date it was
        last looked at.
    note:
        Any interpretation the engine applies on top of the raw citation.
    """

    value: float
    unit: str
    source: str
    verified_on: date
    low: float | None = None
    high: float | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError(f"benchmark range inverted: {self.low} > {self.high}")

    def describe(self) -> str:
        """One-line audit string: value, range, source and verification date."""
        rng = ""
        if self.low is not None and self.high is not None:
            rng = f" (range {self.low}-{self.high} {self.unit})"
        return (
            f"{self.value} {self.unit}{rng} | {self.source} "
            f"| verified {self.verified_on.isoformat()}"
        )


NRF_2026: Final[str] = (
    "Norton Rose Fulbright, 'Cost of Capital: 2026 Outlook', 2026-01-29"
)
VERIFIED: Final[date] = date(2026, 8, 6)


class Technology(str, Enum):
    """Asset classes the default library distinguishes."""

    SOLAR = "solar"
    WIND = "wind"
    STORAGE = "storage"
    DATA_CENTER = "data_center"
    GAS = "gas"
    OTHER = "other"


class RevenueContractType(str, Enum):
    """Revenue-risk profile, which is what actually drives the DSCR ask."""

    CONTRACTED = "contracted"
    MERCHANT_P50 = "merchant_p50"
    HYPERSCALER_CONTRACTED = "hyperscaler_contracted"


class DebtPhase(str, Enum):
    CONSTRUCTION = "construction"
    PERMANENT = "permanent"


# ---------------------------------------------------------------------------
# Minimum DSCR by technology and revenue-risk profile
# ---------------------------------------------------------------------------

MIN_DSCR: Final[dict[tuple[Technology, RevenueContractType], Benchmark]] = {
    (Technology.SOLAR, RevenueContractType.CONTRACTED): Benchmark(
        value=1.30, low=1.25, high=1.30, unit="x", source=NRF_2026,
        verified_on=VERIFIED,
        note="Engine defaults to the lender-friendly top of the published range.",
    ),
    (Technology.WIND, RevenueContractType.CONTRACTED): Benchmark(
        value=1.40, low=1.35, high=1.40, unit="x", source=NRF_2026,
        verified_on=VERIFIED,
        note="Wind carries a higher ask than solar for resource volatility.",
    ),
    (Technology.STORAGE, RevenueContractType.CONTRACTED): Benchmark(
        value=1.20, low=1.15, high=1.20, unit="x", source=NRF_2026,
        verified_on=VERIFIED,
        note="Tolling/capacity-contracted BESS; no volumetric resource risk.",
    ),
    (Technology.DATA_CENTER, RevenueContractType.CONTRACTED): Benchmark(
        value=1.15, low=1.15, high=1.15, unit="x", source=NRF_2026,
        verified_on=VERIFIED,
        note="NRF publishes 1.05-1.15x for data centres; 1.15x is the general case.",
    ),
    (Technology.DATA_CENTER, RevenueContractType.HYPERSCALER_CONTRACTED): Benchmark(
        value=1.05, low=1.05, high=1.05, unit="x", source=NRF_2026,
        verified_on=VERIFIED,
        note="Investment-grade hyperscaler portfolio leases only.",
    ),
    (Technology.SOLAR, RevenueContractType.MERCHANT_P50): Benchmark(
        value=1.75, low=1.75, high=1.75, unit="x", source=NRF_2026,
        verified_on=VERIFIED, note="Sized on the P50 merchant curve.",
    ),
    (Technology.WIND, RevenueContractType.MERCHANT_P50): Benchmark(
        value=1.80, low=1.80, high=1.80, unit="x", source=NRF_2026,
        verified_on=VERIFIED, note="Sized on the P50 merchant curve.",
    ),
    (Technology.STORAGE, RevenueContractType.MERCHANT_P50): Benchmark(
        value=2.00, low=2.00, high=2.00, unit="x", source=NRF_2026,
        verified_on=VERIFIED,
        note="Merchant BESS spread revenue is the least bankable cashflow in the set.",
    ),
}


def min_dscr(
    technology: Technology,
    contract_type: RevenueContractType = RevenueContractType.CONTRACTED,
) -> Benchmark:
    """Return the market minimum DSCR benchmark for a technology/risk profile.

    Raises
    ------
    KeyError
        If the combination is not published. The engine never guesses a DSCR:
        an unpublished combination is a modelling decision the user must make.
    """
    try:
        return MIN_DSCR[(technology, contract_type)]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(
            f"No published DSCR benchmark for {technology.value}/{contract_type.value}. "
            "Supply target_dscr explicitly."
        ) from exc


# ---------------------------------------------------------------------------
# Debt pricing
# ---------------------------------------------------------------------------

BASE_SPREAD_BPS: Final[dict[DebtPhase, Benchmark]] = {
    DebtPhase.CONSTRUCTION: Benchmark(
        value=150.0, low=125.0, high=150.0, unit="bps over SOFR", source=NRF_2026,
        verified_on=VERIFIED,
        note="125-137.5bps reserved for the strongest sponsors/credits.",
    ),
    DebtPhase.PERMANENT: Benchmark(
        value=175.0, low=162.5, high=187.5, unit="bps over SOFR", source=NRF_2026,
        verified_on=VERIFIED, note="Mid-point of the published permanent range.",
    ),
}

#: Merchant-exposure spread adders. Keyed by the upper bound of the merchant
#: revenue share band. NRF publishes +25bps for 10-20% and +50bps for 30-40%;
#: the 20-30% band is linearly interpolated by this engine and flagged as such.
MERCHANT_SPREAD_ADDER_BPS: Final[tuple[tuple[float, Benchmark], ...]] = (
    (0.10, Benchmark(0.0, "bps", NRF_2026, VERIFIED,
                     note="Fully contracted: no merchant adder.")),
    (0.20, Benchmark(25.0, "bps", NRF_2026, VERIFIED,
                     note="Published: +25bps for 10-20% merchant exposure.")),
    (0.30, Benchmark(37.5, "bps", NRF_2026, VERIFIED,
                     note="INTERPOLATED by Structura between the +25 and +50 "
                          "published bands; not itself a published figure.")),
    (0.40, Benchmark(50.0, "bps", NRF_2026, VERIFIED,
                     note="Published: +50bps for 30-40% merchant exposure.")),
)

MERCHANT_ADDER_ABOVE_RANGE: Final[Benchmark] = Benchmark(
    50.0, "bps", NRF_2026, VERIFIED,
    note="EXTRAPOLATED: merchant share above 40% exceeds the published range. "
         "NRF also notes ERCOT merchant exposure is typically capped at 25-30%, "
         "so a >40% merchant deal may simply not be bankable at any spread.",
)


def merchant_spread_adder_bps(merchant_share: float) -> Benchmark:
    """Spread adder in bps for a given merchant revenue share (0.0-1.0)."""
    if not 0.0 <= merchant_share <= 1.0:
        raise ValueError("merchant_share must be between 0 and 1")
    for upper, bench in MERCHANT_SPREAD_ADDER_BPS:
        if merchant_share <= upper:
            return bench
    return MERCHANT_ADDER_ABOVE_RANGE


def all_in_spread_bps(phase: DebtPhase, merchant_share: float = 0.0) -> float:
    """Base spread plus merchant adder, in bps over SOFR."""
    return BASE_SPREAD_BPS[phase].value + merchant_spread_adder_bps(merchant_share).value


#: SOFR is a market rate, not a benchmark this repo can freeze. It is exposed as
#: an explicit, dated placeholder so that no downstream code silently assumes a
#: rate: the caller is expected to override it with a live curve point.
SOFR_PLACEHOLDER: Final[Benchmark] = Benchmark(
    value=0.0400, unit="decimal p.a.",
    source="PLACEHOLDER - not a published benchmark. Override with a live SOFR fix.",
    verified_on=VERIFIED,
    note="Structura does not ship a rates feed. This exists so the default all-in "
         "rate is traceable rather than hard-coded in a model file.",
)


def all_in_rate(
    phase: DebtPhase,
    merchant_share: float = 0.0,
    base_rate: float | None = None,
) -> float:
    """All-in nominal annual interest rate = base rate + spread."""
    base = SOFR_PLACEHOLDER.value if base_rate is None else base_rate
    return base + all_in_spread_bps(phase, merchant_share) / 10_000.0


# ---------------------------------------------------------------------------
# Structural defaults
# ---------------------------------------------------------------------------

MAX_GEARING: Final[Benchmark] = Benchmark(
    value=0.75, low=0.60, high=0.80, unit="debt / total project cost",
    source="NRF 2026 Outlook + standard non-recourse practice", verified_on=VERIFIED,
    note="Gearing is normally an outcome of the DSCR sculpt, with a hard cap "
         "imposed by the credit agreement. 75% is the customary cap.",
)

DSRA_MONTHS: Final[Benchmark] = Benchmark(
    value=6.0, low=6.0, high=12.0, unit="months of debt service",
    source="Standard non-recourse credit-agreement practice", verified_on=VERIFIED,
    note="6 months is the market norm; 12 months appears on weaker credits.",
)

TAIL_YEARS: Final[Benchmark] = Benchmark(
    value=2.0, low=1.0, high=5.0, unit="years",
    source="Standard non-recourse credit-agreement practice", verified_on=VERIFIED,
    note="Tail = project life minus debt tenor. Lenders require the asset to "
         "outlive the loan so there is residual value to restructure against.",
)

CASH_SWEEP_PCT: Final[Benchmark] = Benchmark(
    value=0.0, low=0.0, high=1.00, unit="fraction of distributable surplus",
    source="Deal-specific; no market default", verified_on=VERIFIED,
    note="Zero by default. Merchant-exposed and refinancing-dependent deals "
         "commonly carry 50-100% sweeps.",
)

UPFRONT_FEE: Final[Benchmark] = Benchmark(
    value=0.0125, low=0.0100, high=0.0200, unit="fraction of facility",
    source="Standard non-recourse practice", verified_on=VERIFIED,
    note="Arrangement/upfront fee, financed by the facility itself.",
)

COMMITMENT_FEE: Final[Benchmark] = Benchmark(
    value=0.005, low=0.0035, high=0.0075, unit="fraction p.a. of undrawn",
    source="Standard non-recourse practice", verified_on=VERIFIED,
    note="Charged on the undrawn construction facility.",
)

ITC_BRIDGE_ADVANCE: Final[dict[str, Benchmark]] = {
    "covered": Benchmark(
        value=0.98, unit="fraction of expected credit", source=NRF_2026,
        verified_on=VERIFIED,
        note="98% advance at SOFR+150 where the transfer is covered/committed.",
    ),
    "uncovered": Benchmark(
        value=0.75, unit="fraction of expected credit", source=NRF_2026,
        verified_on=VERIFIED,
        note="75% advance at SOFR+225 (~67.5% net at a 90c transfer price).",
    ),
}

FEDERAL_TAX_RATE: Final[Benchmark] = Benchmark(
    value=0.21, unit="decimal", source="IRC §11(b), 21% corporate rate",
    verified_on=VERIFIED,
    note="Federal only. State tax is out of scope.",
)


def benchmark_registry() -> dict[str, Benchmark]:
    """Flat name -> Benchmark map, for rendering the /current-law page later."""
    registry: dict[str, Benchmark] = {}
    for (tech, ctype), bench in MIN_DSCR.items():
        registry[f"min_dscr.{tech.value}.{ctype.value}"] = bench
    for phase, bench in BASE_SPREAD_BPS.items():
        registry[f"spread.{phase.value}"] = bench
    for upper, bench in MERCHANT_SPREAD_ADDER_BPS:
        registry[f"merchant_adder.le_{upper:.2f}"] = bench
    registry["merchant_adder.above_range"] = MERCHANT_ADDER_ABOVE_RANGE
    for key, bench in ITC_BRIDGE_ADVANCE.items():
        registry[f"itc_bridge.{key}"] = bench
    registry.update(
        {
            "sofr.placeholder": SOFR_PLACEHOLDER,
            "max_gearing": MAX_GEARING,
            "dsra_months": DSRA_MONTHS,
            "tail_years": TAIL_YEARS,
            "cash_sweep_pct": CASH_SWEEP_PCT,
            "upfront_fee": UPFRONT_FEE,
            "commitment_fee": COMMITMENT_FEE,
            "tax_rate.federal": FEDERAL_TAX_RATE,
        }
    )
    return registry
