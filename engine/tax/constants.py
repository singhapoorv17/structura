"""Statutory dates, rates, thresholds and recovery tables for the tax engine.

**Every number used anywhere in ``engine/tax`` lives here.** No magic numbers
appear in the rule modules; they import from this file. A reviewer who wants to
audit what law this package believes only has to read this one module plus
:mod:`engine.tax.citations`.

Each constant is annotated with:

* the authority (statute, notice or case) it comes from;
* a ``Confidence`` marker, where anything not ``VERIFIED`` is also listed in
  ``engine/tax/UNVERIFIED.md``.

Law verified on **2026-08-06** against the Structura rulebook. Re-verify
before any use; the begin-construction rules are in active litigation and the
FEOC guidance is expressly interim.
"""

from __future__ import annotations

from datetime import date
from typing import Final, Mapping

from engine.tax.enums import CreditSection, Technology

__all__ = [
    "LAW_VERIFIED_ON",
    "OBBBA_ENACTMENT_DATE",
    "WIND_SOLAR_BOC_DEADLINE",
    "WIND_SOLAR_PIS_BACKSTOP",
    "CONTINUITY_SAFE_HARBOR_YEARS",
    "FEOC_EFFECTIVE_DATE",
    "NOTICE_2025_42_ISSUE_DATE",
    "NOTICE_2025_42_VACATUR_DATE",
    "NOTICE_2026_15_RELEASE_DATE",
    "ITC_BASE_RATE",
    "PWA_MULTIPLIER",
    "ITC_PWA_RATE",
    "PTC_BASE_RATE_PER_KWH",
    "PTC_CREDIT_PERIOD_YEARS",
    "ADDER_BASE_PERCENTAGE_POINTS",
    "ADDER_PWA_PERCENTAGE_POINTS",
    "PTC_ADDER_MULTIPLIER",
    "DOMESTIC_CONTENT_THRESHOLDS",
    "NON_WIND_SOLAR_FULL_CREDIT_THROUGH_BOC_YEAR",
    "NON_WIND_SOLAR_PHASE_DOWN",
    "FIVE_PERCENT_SAFE_HARBOR_THRESHOLD",
    "NOTICE_2025_42_CAPACITY_THRESHOLD_MW",
    "NOTICE_2025_42_APPLIES_TO_BOC_AFTER",
    "ITC_BASIS_REDUCTION_FRACTION",
    "MACRS_5_YEAR",
    "MACRS_15_YEAR",
    "STRAIGHT_LINE_LIVES",
    "DEFAULT_BONUS_RATE",
    "SECTION_70512H_PROHIBITED_SECTIONS",
    "SECTION_70512H_EFFECTIVE_FOR_TY_BEGINNING_AFTER",
    "TRANSFERABLE_SECTIONS",
    "DEFAULT_ITC_TRANSFER_PRICE",
    "DEFAULT_PTC_TRANSFER_PRICE",
    "DEFAULT_TRANSFER_TRANSACTION_COST_PCT",
    "EXCESSIVE_CREDIT_TRANSFER_PENALTY_RATE",
    "ITC_MARKET_MIX_2025",
    "PTC_DIRECT_TRANSFER_SHARE_2025",
    "TRANSFER_MARKET_SIZE_USD_BN",
    "PROVISIONAL_MACR_THRESHOLDS",
    "PLACEHOLDER_NOTICE_2025_08_SAFE_HARBOR_PCT",
    "PLACEHOLDER_PTC_INFLATION_ADJUSTMENT",
    "RATE_TOLERANCE",
]

# ---------------------------------------------------------------------------
# Verification stamp
# ---------------------------------------------------------------------------

#: Date on which every VERIFIED rule in this package was checked against
#: primary/secondary sources. Rendered by the /current-law page.
LAW_VERIFIED_ON: Final[date] = date(2026, 8, 6)

#: Absolute tolerance for comparing credit rates (dimensionless fractions).
RATE_TOLERANCE: Final[float] = 1e-12


# ---------------------------------------------------------------------------
# Key statutory dates (Confidence.VERIFIED)
# ---------------------------------------------------------------------------

#: One Big Beautiful Bill Act, P.L. 119-21, enacted 2025-07-04.
OBBBA_ENACTMENT_DATE: Final[date] = date(2025, 7, 4)

#: Wind and solar must have BEGUN CONSTRUCTION on or before this date to keep
#: the standard four-year continuity window. OBBBA §70513.
WIND_SOLAR_BOC_DEADLINE: Final[date] = date(2026, 7, 4)

#: Wind/solar that missed the BOC cliff receive a credit only if PLACED IN
#: SERVICE on or before this date. Miss both and the credit is zero.
WIND_SOLAR_PIS_BACKSTOP: Final[date] = date(2027, 12, 31)

#: Continuity safe harbor: the facility must be placed in service by the end of
#: the fourth calendar year following the calendar year in which construction
#: began (the "four-year continuity window"). Long-standing IRS begin-
#: construction guidance (Notice 2013-29 line, carried forward).
CONTINUITY_SAFE_HARBOR_YEARS: Final[int] = 4

#: FEOC restrictions take effect for property/components and taxable years from
#: this date.
FEOC_EFFECTIVE_DATE: Final[date] = date(2026, 1, 1)

#: IRS Notice 2025-42 - eliminated the 5% cost safe harbor for wind/solar
#: >1.5 MW. Issued August 2025.
NOTICE_2025_42_ISSUE_DATE: Final[date] = date(2025, 8, 1)

#: *Oregon Environmental Council v. IRS*, No. 25-4400 (CKK) (D.D.C.) vacated
#: Notice 2025-42 in full as arbitrary and capricious under the APA and
#: remanded.
NOTICE_2025_42_VACATUR_DATE: Final[date] = date(2026, 6, 6)

#: IRS Notice 2026-15 - interim FEOC / MACR guidance.
NOTICE_2026_15_RELEASE_DATE: Final[date] = date(2026, 2, 12)


# ---------------------------------------------------------------------------
# Credit rates (Confidence.VERIFIED for ITC; see UNVERIFIED.md for
# the PTC inflation adjustment)
# ---------------------------------------------------------------------------

#: §48E base energy percentage before the PWA multiplier.
ITC_BASE_RATE: Final[float] = 0.06

#: The "5x multiplier" for satisfying prevailing wage and apprenticeship.
PWA_MULTIPLIER: Final[float] = 5.0

#: 6% x 5 = 30%. Stated explicitly for readability at call sites.
ITC_PWA_RATE: Final[float] = ITC_BASE_RATE * PWA_MULTIPLIER

#: §45Y(a)(2)(A) statutory base amount, US$ per kWh, in 2022 dollars, before
#: the PWA multiplier and before the annual inflation adjustment.
PTC_BASE_RATE_PER_KWH: Final[float] = 0.003

#: §45Y credit period: 10 years from placed-in-service date.
PTC_CREDIT_PERIOD_YEARS: Final[int] = 10

#: Domestic content / energy community bonus, expressed in ITC percentage
#: points. §48(a)(12)/(14) style drafting carried into §48E: 2 points at the
#: base rate, 10 points where PWA is satisfied (the same 5x multiplier).
#: The 10-point figure presumes PWA compliance.
ADDER_BASE_PERCENTAGE_POINTS: Final[float] = 0.02
ADDER_PWA_PERCENTAGE_POINTS: Final[float] = 0.10

#: For the PTC the bonus is a 10% *increase in the credit amount*, not a
#: percentage-point addition.
PTC_ADDER_MULTIPLIER: Final[float] = 0.10


# ---------------------------------------------------------------------------
# Domestic content (Confidence.VERIFIED)
# ---------------------------------------------------------------------------

#: Applicable-percentage threshold the domestic cost ratio must MEET OR EXCEED,
#: keyed by the applicable year. Anything at or after the last key uses the
#: last value.
DOMESTIC_CONTENT_THRESHOLDS: Final[Mapping[int, float]] = {
    2024: 0.40,  # pre-2025
    2025: 0.45,
    2026: 0.50,
    2027: 0.55,  # 55% thereafter
}


# ---------------------------------------------------------------------------
# Non-wind/solar phase-down (Confidence.VERIFIED)
# ---------------------------------------------------------------------------

#: Storage, geothermal, nuclear and hydro keep the full §48E credit for
#: construction begun through the end of this year.
NON_WIND_SOLAR_FULL_CREDIT_THROUGH_BOC_YEAR: Final[int] = 2033

#: Begin-construction year -> fraction of the otherwise-allowable credit.
NON_WIND_SOLAR_PHASE_DOWN: Final[Mapping[int, float]] = {
    2034: 0.75,
    2035: 0.50,
    2036: 0.00,  # and thereafter
}


# ---------------------------------------------------------------------------
# Begin construction
# ---------------------------------------------------------------------------

#: The 5% cost safe harbor: the taxpayer must have paid or incurred at least
#: 5% of the total cost of the facility. (Confidence.VERIFIED - black letter.)
FIVE_PERCENT_SAFE_HARBOR_THRESHOLD: Final[float] = 0.05

#: Notice 2025-42 removed the 5% safe harbor for wind/solar facilities with
#: nameplate capacity ABOVE this threshold. (Confidence.VERIFIED.)
NOTICE_2025_42_CAPACITY_THRESHOLD_MW: Final[float] = 1.5

#: PLACEHOLDER. Notice 2025-42 applied prospectively to facilities beginning
#: construction after a stated date in 2025. The exact cut-off is not confirmed
#: in this build; see UNVERIFIED.md. Set conservatively to the notice's issue
#: month so the litigation toggle is exercised for all 2026 projects.
NOTICE_2025_42_APPLIES_TO_BOC_AFTER: Final[date] = date(2025, 9, 2)


# ---------------------------------------------------------------------------
# Depreciation - §50(c)(3), §168 (Confidence.VERIFIED)
# ---------------------------------------------------------------------------

#: §50(c)(3): the depreciable basis of energy property is reduced by 50% of the
#: investment credit determined with respect to it.
ITC_BASIS_REDUCTION_FRACTION: Final[float] = 0.50

#: IRS Pub. 946 Table A-1: 5-year GDS, 200% declining balance switching to
#: straight line, half-year convention. Sums to exactly 1.00.
MACRS_5_YEAR: Final[tuple[float, ...]] = (
    0.2000,
    0.3200,
    0.1920,
    0.1152,
    0.1152,
    0.0576,
)

#: IRS Pub. 946 Table A-1: 15-year GDS, 150% declining balance switching to
#: straight line, half-year convention. Sums to exactly 1.00.
MACRS_15_YEAR: Final[tuple[float, ...]] = (
    0.0500,
    0.0950,
    0.0855,
    0.0770,
    0.0693,
    0.0623,
    0.0590,
    0.0590,
    0.0591,
    0.0590,
    0.0591,
    0.0590,
    0.0591,
    0.0590,
    0.0591,
    0.0295,
)

#: Recovery periods available for straight-line election.
STRAIGHT_LINE_LIVES: Final[Mapping[str, int]] = {
    "sl_5": 5,
    "sl_15": 15,
    "sl_20": 20,
    "sl_39": 39,
}

#: §168(k) bonus rate. OBBBA restored 100% bonus expensing for qualified
#: property acquired after 2025-01-19. Confidence.PROVISIONAL - the rate is
#: modelled as a user input everywhere; this is only the default.
DEFAULT_BONUS_RATE: Final[float] = 1.00


# ---------------------------------------------------------------------------
# Transfer / direct pay (Confidence.VERIFIED)
# ---------------------------------------------------------------------------

#: §70512(h) bars transfer of these credits to a specified foreign entity
#: within the meaning of §7701(a)(51)(B).
SECTION_70512H_PROHIBITED_SECTIONS: Final[frozenset[CreditSection]] = frozenset(
    {
        CreditSection.SEC_45Q,
        CreditSection.SEC_45X,
        CreditSection.SEC_45Y,
        CreditSection.SEC_45Z,
        CreditSection.SEC_48E,
    }
)

#: Effective for taxable years beginning after the OBBBA enactment date; first
#: tested 2026-01-01 for a calendar-year taxpayer.
SECTION_70512H_EFFECTIVE_FOR_TY_BEGINNING_AFTER: Final[date] = OBBBA_ENACTMENT_DATE

#: Credits eligible for a §6418 transfer election, as modelled here.
TRANSFERABLE_SECTIONS: Final[frozenset[CreditSection]] = SECTION_70512H_PROHIBITED_SECTIONS

#: Cents on the dollar. Norton Rose Fulbright, *Cost of Capital: 2026 Outlook*
#: prices the ITC bridge at "75% advance (~67.5% net at 90c)", i.e. a 90c ITC
#: clearing price.
DEFAULT_ITC_TRANSFER_PRICE: Final[float] = 0.90

#: PLACEHOLDER. No PTC clearing price is given in the verified rulebook; PTC
#: strips generally price differently from ITCs because they are delivered over
#: ten years. See UNVERIFIED.md.
DEFAULT_PTC_TRANSFER_PRICE: Final[float] = 0.92

#: PLACEHOLDER. Broker fee + insurance + legal, as a fraction of gross credit.
#: See UNVERIFIED.md.
DEFAULT_TRANSFER_TRANSACTION_COST_PCT: Final[float] = 0.02

#: §6418(g)(2) excessive credit transfer penalty: 20% of the excessive amount.
#: Confidence.PROVISIONAL.
EXCESSIVE_CREDIT_TRANSFER_PENALTY_RATE: Final[float] = 0.20

#: Crux market data - share of ITC gross value by route, 2025. Used for
#: context/narration only; never for arithmetic on a deal.
ITC_MARKET_MIX_2025: Final[Mapping[str, float]] = {
    "partnership": 0.57,
    "direct_transfer": 0.28,
    "preferred_equity": 0.15,
}

#: Crux: ">90% direct transfer" for PTCs.
PTC_DIRECT_TRANSFER_SHARE_2025: Final[float] = 0.90

#: Crux: transfer market $32bn (2024) -> $42bn (2025), +48%.
TRANSFER_MARKET_SIZE_USD_BN: Final[Mapping[int, float]] = {2024: 32.0, 2025: 42.0}


# ---------------------------------------------------------------------------
# FEOC / MACR thresholds
# ---------------------------------------------------------------------------
#
# ⚠️  READ THIS BEFORE TRUSTING ANY NUMBER BELOW.
#
# Exactly ONE threshold in this table is carried by the verified rulebook:
# solar eligible components sold in CY2026 must reach a MACR of at least 50%
# Every other cell is a PLACEHOLDER: the *structure* is right (the
# thresholds are technology- and year-specific and escalate over time) but the
# values have not been confirmed against the statutory table in OBBBA §70512 or
# against IRS Notice 2026-15. They are listed in UNVERIFIED.md and every
# consumer of this table is told, per-lookup, whether the value is a
# placeholder.
#
# Structure: {Technology: {applicable_year: threshold_fraction}}. Years beyond
# the last key inherit the last value.
# ---------------------------------------------------------------------------

PROVISIONAL_MACR_THRESHOLDS: Final[Mapping[Technology, Mapping[int, float]]] = {
    Technology.SOLAR: {2026: 0.50, 2027: 0.60, 2028: 0.70, 2029: 0.80, 2030: 0.85},
    Technology.WIND: {2026: 0.50, 2027: 0.60, 2028: 0.70, 2029: 0.80, 2030: 0.85},
    Technology.STORAGE: {2026: 0.55, 2027: 0.60, 2028: 0.65, 2029: 0.70, 2030: 0.75},
    Technology.GEOTHERMAL: {2026: 0.40, 2027: 0.45, 2028: 0.50, 2029: 0.55, 2030: 0.60},
    Technology.NUCLEAR: {2026: 0.40, 2027: 0.45, 2028: 0.50, 2029: 0.55, 2030: 0.60},
    Technology.HYDRO: {2026: 0.40, 2027: 0.45, 2028: 0.50, 2029: 0.55, 2030: 0.60},
}

#: The single cell of the table above that the verified rulebook actually
#: states. Used by :mod:`engine.tax.feoc` to mark everything else as a
#: placeholder without hand-maintaining a second list.
VERIFIED_MACR_CELLS: Final[frozenset[tuple[Technology, int]]] = frozenset(
    {(Technology.SOLAR, 2026)}
)

#: PLACEHOLDER. Notice 2025-08 (Jan 2025) publishes elective safe-harbor
#: *assigned cost percentages* per technology and component, letting a taxpayer
#: certify domestic content without a supplier cost build-up. The real tables
#: are per-component; this is a single stand-in ratio so the code path exists.
#: See UNVERIFIED.md.
PLACEHOLDER_NOTICE_2025_08_SAFE_HARBOR_PCT: Final[Mapping[Technology, float]] = {
    Technology.SOLAR: 0.00,
    Technology.WIND: 0.00,
    Technology.STORAGE: 0.00,
    Technology.GEOTHERMAL: 0.00,
    Technology.NUCLEAR: 0.00,
    Technology.HYDRO: 0.00,
}

#: PLACEHOLDER. §45Y(c) inflation adjustment factor by calendar year, applied
#: to the 0.3 c/kWh base before the 5x PWA multiplier, then rounded to the
#: nearest 0.05 cent. 2022 is the statutory base year (factor 1.0). Later-year
#: factors are announced annually by the IRS and are NOT confirmed here.
PLACEHOLDER_PTC_INFLATION_ADJUSTMENT: Final[Mapping[int, float]] = {2022: 1.0}
