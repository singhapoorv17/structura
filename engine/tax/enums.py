"""Enumerations for the current-law tax engine.

Kept in their own module so that :mod:`engine.tax.constants` (which is keyed by
technology and credit type) and :mod:`engine.tax.models` can both import them
without a cycle.

Vocabulary note for readers coming from outside US energy tax:

PWA
    Prevailing Wage and Apprenticeship. Satisfying the §45Y(g)(9)/§48E(d)(3)
    labour requirements multiplies the credit by five (the "5x multiplier"):
    a 6% ITC becomes 30%, a 0.3 c/kWh PTC becomes 1.5 c/kWh (before inflation
    adjustment).
PIS
    Placed In Service - the date the asset is ready and available for its
    specifically assigned function. Distinct from *begin construction* (BOC).
BOC
    Begin Construction, established either by the 5% cost safe harbor or by the
    Physical Work Test, and preserved by satisfying a continuity requirement.
MACR
    Material Assistance Cost Ratio - the FEOC pass/fail test introduced by
    OBBBA §70512 and given interim methodology by IRS Notice 2026-15.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "Technology",
    "CreditType",
    "CreditSection",
    "EligibilityPath",
    "BeginConstructionMethod",
    "Notice202542Status",
    "DepreciationMethod",
    "AdderType",
    "MacrMethod",
    "PhaseDownApplication",
    "Confidence",
    "ForeignEntityStatus",
]


class Technology(str, Enum):
    """Generation / storage technologies the credit rules discriminate between.

    OBBBA (P.L. 119-21) did not repeal §48E or §45Y; it *bifurcated* them. Wind
    and solar face an accelerated begin-construction cliff; everything else
    keeps the original runway. That split is the single most important fact in
    this package, so it is encoded in the type system rather than in a comment.
    """

    SOLAR = "solar"
    WIND = "wind"
    STORAGE = "storage"
    GEOTHERMAL = "geothermal"
    NUCLEAR = "nuclear"
    HYDRO = "hydro"

    @property
    def is_wind_or_solar(self) -> bool:
        """True for the two technologies subject to the 2026-07-04 BOC cliff."""
        return self in (Technology.WIND, Technology.SOLAR)


class CreditType(str, Enum):
    """Which credit the taxpayer elects."""

    ITC = "itc"  # §48E clean electricity investment credit
    PTC = "ptc"  # §45Y clean electricity production credit


class CreditSection(str, Enum):
    """Code sections whose credits are transferable under §6418.

    §70512(h) prohibits *transfer* of each of these to a specified foreign
    entity within the meaning of §7701(a)(51)(B).
    """

    SEC_45Q = "45Q"
    SEC_45X = "45X"
    SEC_45Y = "45Y"
    SEC_45Z = "45Z"
    SEC_48E = "48E"


class EligibilityPath(str, Enum):
    """Which statutory route (if any) carries the project to a credit."""

    #: Wind/solar that began construction on or before 2026-07-04 and therefore
    #: keeps the four-year continuity window.
    WIND_SOLAR_BEGIN_CONSTRUCTION = "wind_solar_begin_construction"
    #: Wind/solar that missed the BOC cliff but is placed in service on or
    #: before 2027-12-31.
    WIND_SOLAR_PIS_BACKSTOP = "wind_solar_pis_backstop"
    #: Storage / geothermal / nuclear / hydro on the original §48E runway.
    NON_WIND_SOLAR_RUNWAY = "non_wind_solar_runway"
    #: No route available - the credit is zero.
    NONE = "none"


class BeginConstructionMethod(str, Enum):
    """The two ways to establish begin construction."""

    FIVE_PERCENT_SAFE_HARBOR = "five_percent_safe_harbor"
    PHYSICAL_WORK_TEST = "physical_work_test"


class Notice202542Status(str, Enum):
    """The litigation fork.

    IRS Notice 2025-42 removed the 5% cost safe harbor for wind and solar
    facilities above 1.5 MW. The U.S. District Court for the District of
    Columbia vacated it in full on 2026-06-06 (*Oregon Environmental Council v.
    IRS*, No. 25-4400 (CKK)). A government appeal is expected, so the status is
    a modelled scenario input, not a constant.
    """

    #: Current law as of 2026-08-06: notice vacated, 5% safe harbor restored.
    VACATED = "vacated"
    #: Scenario: the D.C. Circuit reverses / stays, notice back in force.
    REINSTATED_ON_APPEAL = "reinstated_on_appeal"


class DepreciationMethod(str, Enum):
    """Cost-recovery methods supported by :mod:`engine.tax.depreciation`."""

    MACRS_5 = "macrs_5"
    MACRS_15 = "macrs_15"
    SL_5 = "sl_5"
    SL_15 = "sl_15"
    SL_20 = "sl_20"
    SL_39 = "sl_39"


class AdderType(str, Enum):
    """Bonus credit amounts stacked on the base rate."""

    DOMESTIC_CONTENT = "domestic_content"
    ENERGY_COMMUNITY = "energy_community"


class MacrMethod(str, Enum):
    """How the Material Assistance Cost Ratio was established."""

    #: Actual cost build-up from supplier certifications (Notice 2026-15).
    SUPPLIER_CERTIFICATION = "supplier_certification"
    #: DOE-derived default cost table safe harbor (Notice 2026-15).
    DEFAULT_COST_TABLE = "default_cost_table"
    #: Interim safe harbor for property acquired under a pre-effective-date
    #: binding written contract.
    INTERIM_SAFE_HARBOR = "interim_safe_harbor"
    #: Ratio supplied directly by the user (modelling shortcut).
    USER_ASSERTED = "user_asserted"


class PhaseDownApplication(str, Enum):
    """Whether the non-wind/solar phase-down percentage bites the whole credit
    or only the base rate.

    The OBBBA §48E(e) phase-out is expressed as a percentage of "the credit
    determined under subsection (a)". Whether the bonus amounts ride the same
    haircut is not settled by guidance we have been able to verify, so it is a
    modelling switch with a documented default. See ``UNVERIFIED.md``.
    """

    ALL_CREDIT = "all_credit"
    BASE_ONLY = "base_only"


class ForeignEntityStatus(str, Enum):
    """FEOC taxonomy under OBBBA §70512 / §7701(a)(51)."""

    NONE = "none"
    #: §7701(a)(51)(B) - the class barred from receiving transferred credits.
    SPECIFIED_FOREIGN_ENTITY = "specified_foreign_entity"
    #: §7701(a)(51)(D) - foreign-influenced entity.
    FOREIGN_INFLUENCED_ENTITY = "foreign_influenced_entity"


class Confidence(str, Enum):
    """How well sourced a rule in this package is.

    The whole point of Structura's tax module is that it is honest about what it
    knows. Every citation and every threshold carries one of these.
    """

    #: Taken directly from the verified rulebook (SPEC.md §2, verified live on
    #: 2026-08-06) or from black-letter statutory text.
    VERIFIED = "verified"
    #: Believed correct and consistent with practice, but not confirmed against
    #: primary text in this build. Displayed with a caveat.
    PROVISIONAL = "provisional"
    #: Structure only. The number is a stand-in so the code runs; it must be
    #: replaced before any real use. Listed in ``UNVERIFIED.md``.
    PLACEHOLDER = "placeholder"
