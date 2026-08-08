"""Bonus credit amounts: domestic content and energy community.

Both adders share a structure that trips people up, so it is stated plainly:

* **On the ITC** the bonus is expressed in **percentage points added to the
  energy percentage**: 2 points at the base rate, or **10 points where PWA is
  satisfied**. The same 5x multiplier that lifts 6% to 30% lifts 2 points to 10.
  SPEC §2.4 quotes the 10-point figure, which presumes PWA compliance; this
  module models both.
* **On the PTC** the bonus is a **10% increase in the credit amount** -
  multiplicative, not additive.

**Domestic content (SPEC §2.4).** The domestic cost ratio must **meet or
exceed** an escalating applicable percentage:

===========  ===========
Year         Threshold
===========  ===========
pre-2025     40%
2025         45%
**2026**     **50%**
2027+        55%
===========  ===========

The test is a cliff, not a slope. A 2026 project at 49% receives nothing; at 50%
it receives the full adder. ``tests/test_tax_adders.py`` pins that boundary.

**Notice 2025-08 (January 2025)** offers an elective safe harbor: instead of
obtaining manufacturers' actual direct cost data (which manufacturers are
famously unwilling to give), the taxpayer may use IRS-published **assigned cost
percentages** per technology and component. Structura implements the election
path but ships **no real percentages** - the tables were not sourced in this
build, so electing the safe harbor without supplying them raises rather than
guesses. See ``UNVERIFIED.md``.

**Energy community — declared simplification.** The statutory test has three
independent limbs: (i) a **brownfield** site; (ii) a **metropolitan/non-
metropolitan statistical area** meeting a fossil-fuel employment or tax-revenue
test *and* an unemployment test; (iii) a **census tract** (or adjoining tract) in
which a coal mine closed after 1999 or a coal-fired generating unit was retired
after 2009. Running those tests requires the annual IRS/DOE appendices and a
geospatial join, neither of which is in scope for Phase 2.

**Structura therefore does not determine energy community status. The caller
asserts it** via ``TaxProject.energy_community`` and names the category in
``energy_community_category``; the engine records the assertion in the audit
trail and marks the adder ``Confidence.PROVISIONAL``. This is a declared
simplification, not a silent approximation.
"""

from __future__ import annotations

from engine.tax.constants import (
    ADDER_BASE_PERCENTAGE_POINTS,
    ADDER_PWA_PERCENTAGE_POINTS,
    DOMESTIC_CONTENT_THRESHOLDS,
    PLACEHOLDER_NOTICE_2025_08_SAFE_HARBOR_PCT,
    PTC_ADDER_MULTIPLIER,
)
from engine.tax.models import (
    AdderResult,
    AdderType,
    Confidence,
    CreditType,
    TaxProject,
)

__all__ = [
    "domestic_content_threshold",
    "domestic_content_adder",
    "energy_community_adder",
    "evaluate_adders",
]

_VALID_ENERGY_COMMUNITY_CATEGORIES = (
    "brownfield",
    "statistical_area",
    "coal_closure",
)


def domestic_content_threshold(year: int) -> float:
    """Applicable percentage the domestic cost ratio must meet or exceed.

    Years before the first tabulated year use the first value (40%); years after
    the last use the last (55%).
    """
    years = sorted(DOMESTIC_CONTENT_THRESHOLDS)
    if year <= years[0]:
        return DOMESTIC_CONTENT_THRESHOLDS[years[0]]
    if year >= years[-1]:
        return DOMESTIC_CONTENT_THRESHOLDS[years[-1]]
    key = max(y for y in years if y <= year)
    return DOMESTIC_CONTENT_THRESHOLDS[key]


def _adder_points(is_pwa_compliant: bool) -> float:
    """Percentage points a bonus adds to the ITC rate."""
    return (
        ADDER_PWA_PERCENTAGE_POINTS
        if is_pwa_compliant
        else ADDER_BASE_PERCENTAGE_POINTS
    )


def domestic_content_adder(project: TaxProject) -> AdderResult:
    """Domestic content bonus, granted or denied, at the applicable threshold.

    The applicable year is the placed-in-service year, which is when the ITC is
    determined.
    """
    year = project.placed_in_service_date.year
    threshold = domestic_content_threshold(year)
    achieved = project.domestic_content_pct
    citation_ids = ("domestic-content-threshold", "domestic-content-adder-amount")
    confidence = Confidence.VERIFIED

    if project.domestic_content_safe_harbor_elected:
        safe_harbor = PLACEHOLDER_NOTICE_2025_08_SAFE_HARBOR_PCT[project.technology]
        if safe_harbor <= 0.0:
            raise NotImplementedError(
                "The Notice 2025-08 elective safe-harbor assigned cost "
                "percentages are not shipped with this build (see "
                "UNVERIFIED.md). Supply domestic_content_pct from an actual "
                "cost build-up, or load the real tables into "
                "constants.PLACEHOLDER_NOTICE_2025_08_SAFE_HARBOR_PCT."
            )
        achieved = safe_harbor  # pragma: no cover - unreachable until tables ship
        citation_ids = citation_ids + ("notice-2025-08-safe-harbor",)
        confidence = Confidence.PLACEHOLDER

    granted = achieved >= threshold
    points = _adder_points(project.is_pwa_compliant) if granted else 0.0

    if granted:
        reason = (
            f"Domestic cost ratio of {achieved:.1%} meets the {threshold:.0%} "
            f"applicable percentage for a facility placed in service in {year}. "
            f"Adds {points * 100:.0f} percentage points to the ITC rate"
            + ("" if project.is_pwa_compliant else " (base rate - PWA not met)")
            + "."
        )
    else:
        reason = (
            f"Domestic cost ratio of {achieved:.1%} falls short of the "
            f"{threshold:.0%} applicable percentage for {year}. The test is a "
            f"cliff: no partial adder is available."
        )

    return AdderResult(
        adder=AdderType.DOMESTIC_CONTENT,
        granted=granted,
        itc_percentage_points=points if project.credit_type is CreditType.ITC else 0.0,
        ptc_multiplier=(
            PTC_ADDER_MULTIPLIER
            if granted and project.credit_type is CreditType.PTC
            else 0.0
        ),
        threshold=threshold,
        achieved=achieved,
        reason=reason,
        confidence=confidence,
        citation_ids=citation_ids,
    )


def energy_community_adder(project: TaxProject) -> AdderResult:
    """Energy community bonus, on the caller's assertion.

    See the module docstring: Structura does **not** run the brownfield /
    statistical-area / coal-closure tests. The adder is granted on an asserted
    qualification and marked provisional so the UI can flag it.
    """
    citation_ids = ("energy-community-adder",)
    granted = project.energy_community
    points = _adder_points(project.is_pwa_compliant) if granted else 0.0

    category = project.energy_community_category or "unspecified"
    if granted and category not in _VALID_ENERGY_COMMUNITY_CATEGORIES:
        note = (
            f" Category asserted as '{category}', which is not one of "
            f"{_VALID_ENERGY_COMMUNITY_CATEGORIES}; record the correct limb for "
            f"diligence."
        )
    else:
        note = ""

    if granted:
        reason = (
            f"Energy community status ASSERTED by the modeller (category: "
            f"{category}). Structura does not run the census-tract, brownfield "
            f"or coal-closure tests - this is a declared simplification. Adds "
            f"{points * 100:.0f} percentage points to the ITC rate"
            + ("" if project.is_pwa_compliant else " (base rate - PWA not met)")
            + "." + note
        )
    else:
        reason = "Energy community status not asserted."

    return AdderResult(
        adder=AdderType.ENERGY_COMMUNITY,
        granted=granted,
        itc_percentage_points=points if project.credit_type is CreditType.ITC else 0.0,
        ptc_multiplier=(
            PTC_ADDER_MULTIPLIER
            if granted and project.credit_type is CreditType.PTC
            else 0.0
        ),
        threshold=None,
        achieved=None,
        reason=reason,
        confidence=Confidence.PROVISIONAL,
        citation_ids=citation_ids,
    )


def evaluate_adders(project: TaxProject) -> tuple[AdderResult, ...]:
    """Both bonus amounts, in the order they are stacked on the base rate."""
    return (domestic_content_adder(project), energy_community_adder(project))
