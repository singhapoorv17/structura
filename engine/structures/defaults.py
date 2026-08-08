"""Structure-level defaults, market heuristics and numerical tolerances.

Design rule inherited from :mod:`engine.defaults`: **no magic numbers anywhere
else in this package.** Every market assumption below is either (a) carried by
SPEC.md §2 and therefore verified, or (b) a clearly-labelled ``PLACEHOLDER_``
market heuristic disclosed in ``LIMITS_STRUCTURES.md``.

Tax-equity pricing in particular is *not* public data. Norton Rose Fulbright's
*Cost of Capital: 2026 Outlook* (SPEC §2.7) publishes debt pricing and DSCR by
technology; it does not publish a tax-equity target yield, a pre-flip cash
sharing ratio or a preferred coupon. Those are quoted deal by deal and Structura
refuses to pretend otherwise: they ship as placeholders that the caller is
expected to override, and every result object that consumed one carries a
warning saying so.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from engine.defaults import Benchmark

__all__ = [
    "STRUCTURES_VERIFIED_ON",
    # tolerances
    "CAPITAL_ACCOUNT_TOLERANCE",
    "ALLOCATION_TOLERANCE",
    "IRR_SOLVE_TOLERANCE",
    "FLIP_SOLVE_TOLERANCE",
    "FLIP_SOLVE_MAX_ITER",
    "RANKING_TOLERANCE",
    "REALLOCATION_MAX_PASSES",
    "FUNDING_TOLERANCE",
    "FUNDING_RELATIVE_TOLERANCE",
    "DE_MINIMIS_SPONSOR_EQUITY_SHARE",
    "DE_MINIMIS_SPONSOR_PAYBACK_YEARS",
    "IMPLAUSIBLE_SPONSOR_IRR",
    # statutory
    "ITC_RECAPTURE_PERIOD_YEARS",
    "ITC_RECAPTURE_VESTING_PER_YEAR",
    "ITC_BASIS_REDUCTION_FRACTION",
    # market heuristics (placeholders)
    "PLACEHOLDER_TE_TARGET_AFTER_TAX_IRR",
    "PLACEHOLDER_TE_INVESTMENT_PER_CREDIT_DOLLAR",
    "PLACEHOLDER_PRE_FLIP_TE_ALLOCATION_SHARE",
    "PLACEHOLDER_POST_FLIP_TE_ALLOCATION_SHARE",
    "PRE_FLIP_TE_CASH_SHARE",
    "POST_FLIP_TE_CASH_SHARE",
    "PLACEHOLDER_MAX_INVESTOR_SHARE_OF_EQUITY",
    "PLACEHOLDER_PREFERRED_RETURN",
    "PLACEHOLDER_PREFERRED_TARGET_TERM_YEARS",
    "PLACEHOLDER_LESSOR_TARGET_AFTER_TAX_IRR",
    "PLACEHOLDER_SALE_LEASEBACK_RESIDUAL_PCT",
    # true-lease guidelines
    "TRUE_LEASE_MIN_LESSOR_AT_RISK_PCT",
    "TRUE_LEASE_MIN_RESIDUAL_PCT",
    "TRUE_LEASE_MAX_TERM_PCT_OF_USEFUL_LIFE",
    "SALE_LEASEBACK_ITC_WINDOW_MONTHS",
    "structure_benchmark_registry",
]

STRUCTURES_VERIFIED_ON: Final[date] = date(2026, 8, 6)

_PLACEHOLDER_SOURCE: Final[str] = (
    "PLACEHOLDER - no public source. Tax-equity and lease pricing is quoted "
    "deal by deal and is not published by NRF, Crux or the IRS. Override it."
)

# ---------------------------------------------------------------------------
# Numerical tolerances
# ---------------------------------------------------------------------------

#: Absolute currency tolerance for capital-account and outside-basis identities.
#: Capital accounts run in the same 1e8-1e9 dollar range as the debt spine, so
#: 1e-6 is floating-point noise, exactly as in :mod:`engine.defaults`.
CAPITAL_ACCOUNT_TOLERANCE: Final[float] = 1e-6

#: Absolute tolerance on "sharing ratios sum to 1.0".
ALLOCATION_TOLERANCE: Final[float] = 1e-9

#: Absolute tolerance on a solved IRR.
IRR_SOLVE_TOLERANCE: Final[float] = 1e-8

#: Absolute tolerance, in *periods*, on the solved flip point. 1e-6 of a year is
#: ~30 seconds: far finer than the annual convention the model runs on.
FLIP_SOLVE_TOLERANCE: Final[float] = 1e-6

#: Hard iteration cap for the flip-point root find. Brent needs ~40 on a
#: 25-period bracket at 1e-6; 200 leaves generous headroom and still terminates.
FLIP_SOLVE_MAX_ITER: Final[int] = 200

#: Two sponsor IRRs closer than this are treated as a tie by the selector and
#: sent to the documented tie-break chain rather than ordered on noise.
RANKING_TOLERANCE: Final[float] = 1e-9

#: Maximum passes of the DRO-cap reallocation loop. Each pass either exhausts
#: the excess or removes at least one partner from the capacity pool, so the
#: loop terminates in at most ``len(partners)`` passes; +1 is a safety margin.
REALLOCATION_MAX_PASSES: Final[int] = 8

#: Absolute currency tolerance on the sources-and-uses identity. Construction
#: funding runs in the 1e8-1e9 range, so $1 is ~1e-9 relative: tight enough to
#: catch a real imbalance and loose enough to survive the fixed-point residual
#: the Phase 1 circularity solve leaves behind.
FUNDING_TOLERANCE: Final[float] = 1.0

#: Relative tolerance on the same identity, applied as
#: ``max(FUNDING_TOLERANCE, FUNDING_RELATIVE_TOLERANCE x uses)``. 1e-6 of a
#: $1bn funding requirement is $1,000 - below the rounding a credit committee
#: would ever see, and above the residual of an iterative solve.
FUNDING_RELATIVE_TOLERANCE: Final[float] = 1e-6


# ---------------------------------------------------------------------------
# Robustness guards on the headline metric
# ---------------------------------------------------------------------------
# An IRR is a rate of return *on an equity base*. Shrink the base far enough and
# the rate stops describing the deal and starts describing the base: a sponsor
# that leaves $2m in a $200m project and takes 5% of the cash reports a
# three-figure IRR while earning almost nothing. Project-finance sponsor equity
# in contracted US renewables and storage runs roughly 20-35% of total funding;
# below a tenth of the stack the levered rate is an artefact, not a return.
# These are Structura's own reporting guards, not market data - they are stated
# here so the rule is auditable and adjustable in one place rather than hidden
# in the selector.

#: Sponsor equity below this share of the total funding requirement makes the
#: reported sponsor IRR non-meaningful; the selector ranks such a structure on
#: sponsor NPV instead and says so.
DE_MINIMIS_SPONSOR_EQUITY_SHARE: Final[float] = 0.10

#: A sponsor whose entire net investment returns inside this many years is in
#: the same position: the annualised rate is dominated by the model's annual
#: period convention rather than by the economics.
DE_MINIMIS_SPONSOR_PAYBACK_YEARS: Final[float] = 1.0

#: A sponsor after-tax IRR above this is reported but never led with. Real
#: sponsor equity IRRs in contracted US renewables and storage are ~8-15%
#: levered after tax; anything above 40% in a *project finance* structure is a
#: denominator artefact or a double-counted benefit and is flagged as such.
IMPLAUSIBLE_SPONSOR_IRR: Final[float] = 0.40


# ---------------------------------------------------------------------------
# Statutory constants
# ---------------------------------------------------------------------------

#: §50(a)(1) investment-credit recapture period. The credit vests 20% for each
#: full year the property remains in qualified use; disposing of the property
#: (or of a partnership interest by more than one third) inside five years
#: recaptures the unvested portion.
ITC_RECAPTURE_PERIOD_YEARS: Final[int] = 5

#: §50(a)(1)(B) vesting rate: one fifth per full year.
ITC_RECAPTURE_VESTING_PER_YEAR: Final[float] = 1.0 / ITC_RECAPTURE_PERIOD_YEARS

#: §50(c)(3): the investment credit reduces depreciable basis by half the
#: credit. Mirrors ``engine.tax.constants.ITC_BASIS_REDUCTION_FRACTION``; it is
#: restated (not re-derived) here so that partnership capital-account code can
#: cite it without importing the whole tax package for one float.
ITC_BASIS_REDUCTION_FRACTION: Final[float] = 0.5


# ---------------------------------------------------------------------------
# Market heuristics - ALL PLACEHOLDERS
# ---------------------------------------------------------------------------

PLACEHOLDER_TE_TARGET_AFTER_TAX_IRR: Final[Benchmark] = Benchmark(
    value=0.0650,
    unit="after-tax IRR p.a.",
    source=_PLACEHOLDER_SOURCE,
    verified_on=STRUCTURES_VERIFIED_ON,
    low=0.0550,
    high=0.0800,
    note="Target yield at which a yield-based flip flips. The single most "
    "important input to a flip model and the one no public source gives.",
)

PLACEHOLDER_TE_INVESTMENT_PER_CREDIT_DOLLAR: Final[Benchmark] = Benchmark(
    value=1.15,
    unit="US$ invested per US$1 of ITC",
    source=_PLACEHOLDER_SOURCE,
    verified_on=STRUCTURES_VERIFIED_ON,
    low=1.00,
    high=1.35,
    note="Used only to derive a tax-equity commitment when the caller does not "
    "state one. A tax-equity investor pays above the face of the credit "
    "because it also receives accelerated depreciation and pre-flip cash.",
)

PLACEHOLDER_PRE_FLIP_TE_ALLOCATION_SHARE: Final[Benchmark] = Benchmark(
    value=0.99,
    unit="share of income, loss and credits",
    source="SPEC.md §6.2 states the classic 99/1 -> 5/95 flip; the ratio itself "
    "is standard market structure, the fit to any given deal is not.",
    verified_on=STRUCTURES_VERIFIED_ON,
    note="Pre-flip sharing ratio for the tax-equity partner.",
)

PLACEHOLDER_POST_FLIP_TE_ALLOCATION_SHARE: Final[Benchmark] = Benchmark(
    value=0.05,
    unit="share of income, loss and credits",
    source="SPEC.md §6.2 (99/1 -> 5/95).",
    verified_on=STRUCTURES_VERIFIED_ON,
    note="Post-flip sharing ratio for the tax-equity partner.",
)

PRE_FLIP_TE_CASH_SHARE: Final[Benchmark] = Benchmark(
    value=0.99,
    unit="share of distributable cash",
    source="SPEC.md §6.2 applies the 99/1 -> 5/95 flip to 'income, loss, "
    "credits and cash'.",
    verified_on=STRUCTURES_VERIFIED_ON,
    low=0.0,
    high=1.0,
    note="Cash is a SEPARATE ratio in the model because it is separate in "
    "every real LLC agreement - wind PTC deals in particular run a much "
    "lower pre-flip cash share. The default follows SPEC §6.2 rather than "
    "inventing a split. Note the consequence: a low pre-flip cash share "
    "with a high income share makes the investor's pre-flip after-tax flow "
    "negative, which breaks the single-root property the yield solve "
    "relies on. The flip solver detects and reports that.",
)

POST_FLIP_TE_CASH_SHARE: Final[Benchmark] = Benchmark(
    value=0.05,
    unit="share of distributable cash",
    source="SPEC.md §6.2 (99/1 -> 5/95).",
    verified_on=STRUCTURES_VERIFIED_ON,
    note="Post-flip the cash ratio converges on the income ratio.",
)

PLACEHOLDER_MAX_INVESTOR_SHARE_OF_EQUITY: Final[Benchmark] = Benchmark(
    value=0.80,
    unit="fraction of project equity",
    source=_PLACEHOLDER_SOURCE,
    verified_on=STRUCTURES_VERIFIED_ON,
    low=0.50,
    high=0.95,
    note="Cap on the DERIVED investor commitment, so a sponsor always retains "
    "equity in the deal. On a 30% ITC project with full bonus the tax "
    "attributes can be worth more than the whole equity cheque, and an "
    "uncapped derivation would fund 100% of the equity from the investor - "
    "which no lender or investor would accept, and which makes the "
    "sponsor's IRR undefined. Ignored entirely when the caller states a "
    "commitment.",
)

PLACEHOLDER_PREFERRED_RETURN: Final[Benchmark] = Benchmark(
    value=0.09,
    unit="preferred return p.a. on unreturned capital",
    source=_PLACEHOLDER_SOURCE,
    verified_on=STRUCTURES_VERIFIED_ON,
    low=0.07,
    high=0.12,
    note="Preferred equity took 15% of ITC gross value in 2025 (Crux, SPEC "
    "§2.2); the coupon is not published.",
)

PLACEHOLDER_PREFERRED_TARGET_TERM_YEARS: Final[Benchmark] = Benchmark(
    value=10.0,
    unit="years to full redemption",
    source=_PLACEHOLDER_SOURCE,
    verified_on=STRUCTURES_VERIFIED_ON,
    note="Redemption horizon targeted by the preferred sweep.",
)

PLACEHOLDER_LESSOR_TARGET_AFTER_TAX_IRR: Final[Benchmark] = Benchmark(
    value=0.0700,
    unit="after-tax IRR p.a.",
    source=_PLACEHOLDER_SOURCE,
    verified_on=STRUCTURES_VERIFIED_ON,
    low=0.0600,
    high=0.0900,
    note="Lease rent is solved to this yield. Sale-leaseback is reported by "
    "NRF (SPEC §2.6) as making a comeback; its pricing is not published.",
)

PLACEHOLDER_SALE_LEASEBACK_RESIDUAL_PCT: Final[Benchmark] = Benchmark(
    value=0.20,
    unit="fraction of original sale price",
    source=_PLACEHOLDER_SOURCE,
    verified_on=STRUCTURES_VERIFIED_ON,
    note="Assumed fair market value of the asset at lease expiry, which is "
    "also the strike of a fair-market-value purchase option. Set at the "
    "Rev. Proc. 2001-28 guideline minimum, which is a floor, not a forecast.",
)


# ---------------------------------------------------------------------------
# True-lease guidelines (Rev. Proc. 2001-28)
# ---------------------------------------------------------------------------
# These are the IRS *advance ruling* guidelines for leveraged leases. They are
# not substantive law - a lease that fails one is not automatically a financing
# - but they are the screen every tax counsel applies first, so Structura runs
# them and reports pass/fail rather than asserting a conclusion.

#: Lessor must have an unconditional at-risk investment of at least 20% of cost
#: throughout the lease term.
TRUE_LEASE_MIN_LESSOR_AT_RISK_PCT: Final[float] = 0.20

#: The asset must have a residual value of at least 20% of original cost at the
#: end of the lease term, without regard to inflation.
TRUE_LEASE_MIN_RESIDUAL_PCT: Final[float] = 0.20

#: The lessee must not be able to use the asset for more than 80% of its
#: estimated useful life, i.e. a remaining life of at least 20% must survive.
TRUE_LEASE_MAX_TERM_PCT_OF_USEFUL_LIFE: Final[float] = 0.80

#: §50(d)(4) / former §48(b): a sale-and-leaseback completed within three months
#: of the original placed-in-service date lets the purchaser-lessor be treated
#: as having placed the property in service, preserving the investment credit.
SALE_LEASEBACK_ITC_WINDOW_MONTHS: Final[int] = 3


def structure_benchmark_registry() -> dict[str, Benchmark]:
    """Flat name -> Benchmark map, for the ``/current-law`` page and tests."""
    return {
        "te.target_after_tax_irr": PLACEHOLDER_TE_TARGET_AFTER_TAX_IRR,
        "te.investment_per_credit_dollar": (
            PLACEHOLDER_TE_INVESTMENT_PER_CREDIT_DOLLAR
        ),
        "flip.pre_flip_te_allocation": PLACEHOLDER_PRE_FLIP_TE_ALLOCATION_SHARE,
        "flip.post_flip_te_allocation": PLACEHOLDER_POST_FLIP_TE_ALLOCATION_SHARE,
        "flip.pre_flip_te_cash": PRE_FLIP_TE_CASH_SHARE,
        "flip.post_flip_te_cash": POST_FLIP_TE_CASH_SHARE,
        "flip.max_investor_share_of_equity": (
            PLACEHOLDER_MAX_INVESTOR_SHARE_OF_EQUITY
        ),
        "preferred.return": PLACEHOLDER_PREFERRED_RETURN,
        "preferred.term_years": PLACEHOLDER_PREFERRED_TARGET_TERM_YEARS,
        "sale_leaseback.lessor_target_irr": PLACEHOLDER_LESSOR_TARGET_AFTER_TAX_IRR,
        "sale_leaseback.residual_pct": PLACEHOLDER_SALE_LEASEBACK_RESIDUAL_PCT,
    }
