"""The citation registry - the moat, as a first-class artifact.

SPEC.md §4.1: *"Current law is the moat. Every tax rule carries a citation and a
'verified on' date in code. A /current-law page renders them."*

This module is therefore not documentation. It is data. Every rule implemented
anywhere in ``engine/tax`` registers a :class:`Citation` here, and every result
object returned by the package carries the ids of the citations that produced
it. ``get_all_citations()`` is the render feed for the ``/current-law`` page and
``citations_for(result)`` is the render feed for a per-deal audit trail.

Three invariants are asserted by ``tests/test_tax_citations.py``:

1. every citation has a non-empty authority, plain-English summary, source and
   ``verified_on`` date;
2. every citation id referenced by a rule module actually resolves;
3. every citation whose confidence is not ``VERIFIED`` appears in
   ``UNVERIFIED.md``.

When the law changes, edit this module *first*, then the constant, then the
rule. See ``README.md`` for the update runbook.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping

from engine.tax.constants import LAW_VERIFIED_ON
from engine.tax.enums import Confidence

__all__ = [
    "Citation",
    "CITATIONS",
    "get_citation",
    "get_all_citations",
    "citations_for_ids",
    "unverified_citations",
]


@dataclass(frozen=True, slots=True)
class Citation:
    """One rule of law, with its authority and the date we checked it.

    Attributes
    ----------
    id
        Stable slug. Referenced from rule modules and from result objects, so
        renaming one is a breaking change - add a new id instead.
    authority
        The statute, notice, regulation or case. Cite it the way a tax lawyer
        would write it in a memo.
    title
        Short human label for the rule, e.g. "Wind/solar begin-construction
        cliff".
    plain_english
        What the rule actually does, in one or two sentences, for a reader who
        does not have the Code open.
    source
        Where the statement was verified: a document, a page, a publication.
    verified_on
        The date the statement was checked. Rendered next to the rule.
    confidence
        See :class:`engine.tax.enums.Confidence`. Anything other than
        ``VERIFIED`` is surfaced to the user with a caveat.
    module
        Which rule module implements it, for grouping on the render page.
    note
        Optional caveat - what is uncertain, what is simplified, what is
        pending (e.g. an expected appeal).
    """

    id: str
    authority: str
    title: str
    plain_english: str
    source: str
    verified_on: date
    confidence: Confidence
    module: str
    note: str = ""


def _c(
    id: str,
    authority: str,
    title: str,
    plain_english: str,
    module: str,
    *,
    source: str = "SPEC.md §2 (Structura verified rulebook, checked live 2026-08-06)",
    verified_on: date = LAW_VERIFIED_ON,
    confidence: Confidence = Confidence.VERIFIED,
    note: str = "",
) -> Citation:
    return Citation(
        id=id,
        authority=authority,
        title=title,
        plain_english=plain_english,
        source=source,
        verified_on=verified_on,
        confidence=confidence,
        module=module,
        note=note,
    )


_ALL: tuple[Citation, ...] = (
    # -- Eligibility ------------------------------------------------------
    _c(
        "obbba-bifurcation",
        "One Big Beautiful Bill Act, P.L. 119-21 (enacted 2025-07-04)",
        "OBBBA bifurcated §48E/§45Y rather than repealing them",
        "OBBBA left the clean electricity investment credit (§48E) and "
        "production credit (§45Y) in force, but split the technologies: wind "
        "and solar face an accelerated begin-construction cliff while storage, "
        "geothermal, nuclear and hydro keep the original runway.",
        "eligibility",
    ),
    _c(
        "wind-solar-boc-cliff",
        "OBBBA P.L. 119-21 (2025-07-04), amending I.R.C. §§45Y, 48E",
        "Wind/solar begin-construction cliff - 2026-07-04",
        "A wind or solar facility must have begun construction on or before "
        "2026-07-04 to claim §48E/§45Y on the ordinary timetable. Projects that "
        "did so keep the standard four-year continuity window.",
        "eligibility",
    ),
    _c(
        "wind-solar-pis-backstop",
        "OBBBA P.L. 119-21 (2025-07-04), amending I.R.C. §§45Y, 48E",
        "Wind/solar placed-in-service backstop - 2027-12-31",
        "A wind or solar facility that missed the 2026-07-04 begin-construction "
        "deadline can still claim the credit only if it is placed in service on "
        "or before 2027-12-31. Miss both tests and the credit is zero - not "
        "reduced, zero.",
        "eligibility",
    ),
    _c(
        "non-wind-solar-runway",
        "I.R.C. §48E(e) as amended by OBBBA P.L. 119-21",
        "Storage/geothermal/nuclear/hydro runway and phase-down",
        "These technologies were untouched by the accelerated cliff. Full §48E "
        "for construction begun through 2033, then 75% for 2034, 50% for 2035 "
        "and zero from 2036.",
        "eligibility",
    ),
    _c(
        "base-and-pwa-rate",
        "I.R.C. §48E(a)(2), §48E(d)(3); §45Y(a)(2), §45Y(g)(9)",
        "6% base rate, 30% with prevailing wage and apprenticeship",
        "The ITC energy percentage is 6%, multiplied by five to 30% where the "
        "prevailing wage and apprenticeship (PWA) requirements are met. The PTC "
        "works the same way: a 0.3 c/kWh base amount, times five with PWA, then "
        "inflation adjusted.",
        "eligibility",
    ),
    _c(
        "ptc-credit-period",
        "I.R.C. §45Y(a)(1)",
        "§45Y ten-year credit period",
        "The production credit runs for the ten-year period beginning on the "
        "date the facility is placed in service.",
        "eligibility",
    ),
    _c(
        "ptc-inflation-adjustment",
        "I.R.C. §45Y(c)",
        "§45Y annual inflation adjustment (unverified factors)",
        "The 0.3 c/kWh base amount is adjusted annually for inflation and "
        "rounded to the nearest 0.05 cent. The IRS announces the factor each "
        "year.",
        "eligibility",
        confidence=Confidence.PLACEHOLDER,
        source="Statutory mechanism is black-letter; the annual factors were "
        "not sourced in this build.",
        note="Only the 2022 base year (factor 1.0) ships. Supply the published "
        "factor for the applicable year before quoting a PTC rate.",
    ),
    _c(
        "phase-down-application",
        "I.R.C. §48E(e)",
        "Whether the phase-down haircuts the bonus amounts too",
        "The non-wind/solar phase-out is expressed as a percentage of the "
        "credit determined under §48E(a). Whether the domestic content and "
        "energy community bonuses ride the same haircut is modelled as a "
        "switch, defaulting to applying it to the whole credit.",
        "eligibility",
        confidence=Confidence.PROVISIONAL,
        source="Interpretation; not confirmed against guidance.",
        note="Toggle with PhaseDownApplication.BASE_ONLY to model the "
        "alternative reading.",
    ),
    # -- Adders -----------------------------------------------------------
    _c(
        "domestic-content-threshold",
        "I.R.C. §48E(a)(3)(B), §45Y(g)(11); Notice 2025-08",
        "Domestic content threshold escalates to 50% in 2026",
        "The domestic cost ratio must meet an escalating applicable percentage: "
        "40% pre-2025, 45% in 2025, 50% in 2026 and 55% thereafter. A project "
        "at 49% in 2026 gets nothing; at 50% it gets the full adder.",
        "adders",
    ),
    _c(
        "domestic-content-adder-amount",
        "I.R.C. §48(a)(12) drafting carried into §48E; §45Y(g)(11)",
        "Domestic content bonus: 2 points base, 10 points with PWA",
        "The ITC bonus is 2 percentage points, multiplied by five to 10 "
        "percentage points where PWA is satisfied. For the PTC it is a 10% "
        "increase in the credit amount.",
        "adders",
    ),
    _c(
        "notice-2025-08-safe-harbor",
        "IRS Notice 2025-08 (January 2025)",
        "Elective safe-harbor assigned cost percentages",
        "Rather than build up actual manufacturer costs, a taxpayer may elect "
        "to use IRS-published assigned cost percentages per technology and "
        "component to compute the domestic cost ratio.",
        "adders",
        confidence=Confidence.PLACEHOLDER,
        source="Existence and purpose of the notice are from SPEC §2.4; the "
        "per-component percentage tables were not sourced in this build.",
        note="Ship the real tables into "
        "constants.PLACEHOLDER_NOTICE_2025_08_SAFE_HARBOR_PCT before enabling "
        "the safe-harbor election in production.",
    ),
    _c(
        "energy-community-adder",
        "I.R.C. §48E(a)(3)(A), §45(b)(11)(B)",
        "Energy community bonus: 2 points base, 10 points with PWA",
        "The same 2/10 percentage-point structure applies to a facility in an "
        "energy community - broadly a brownfield site, a statistical area with "
        "fossil-fuel employment or unemployment tests, or a census tract with a "
        "closed coal mine or retired coal-fired generating unit.",
        "adders",
        confidence=Confidence.PROVISIONAL,
        source="Adder amount from SPEC §2.4; the qualification tests are "
        "summarised from the statutory categories.",
        note="Structura does NOT run the census-tract / brownfield / "
        "coal-closure test. The caller asserts qualification and the category. "
        "Declared simplification - see UNVERIFIED.md.",
    ),
    # -- FEOC -------------------------------------------------------------
    _c(
        "feoc-effective-date",
        "OBBBA §70512",
        "FEOC restrictions effective 2026-01-01",
        "Foreign entity of concern restrictions bite from 1 January 2026. They "
        "are a pass/fail gate on credit eligibility, not a rate adjustment.",
        "feoc",
    ),
    _c(
        "notice-2026-15-macr",
        "IRS Notice 2026-15 (released 2026-02-12)",
        "Material Assistance Cost Ratio - interim methodology",
        "Notice 2026-15 is the interim guidance defining how to compute the "
        "MACR: the share of total direct costs NOT attributable to a prohibited "
        "foreign entity. It provides interim safe harbors, permits reliance on "
        "supplier certifications, and supplies DOE-derived default cost tables. "
        "Broader prohibited-foreign-entity status guidance was deferred.",
        "feoc",
    ),
    _c(
        "macr-thresholds",
        "OBBBA §70512 statutory MACR tables",
        "MACR thresholds are technology- and year-specific",
        "The minimum MACR escalates by year and differs by technology - for "
        "example solar eligible components sold in calendar 2026 must reach at "
        "least 50%.",
        "feoc",
        confidence=Confidence.PLACEHOLDER,
        source="Only the solar-CY2026 50% cell is carried by the verified "
        "rulebook (SPEC §2.3). All other cells are placeholders.",
        note="Replace constants.PROVISIONAL_MACR_THRESHOLDS with the statutory "
        "table before production use. Every lookup reports "
        "`threshold_is_placeholder`.",
    ),
    _c(
        "macr-failure-is-disqualifying",
        "OBBBA §70512",
        "A MACR failure kills the credit",
        "Falling below the applicable MACR threshold is not a warning or a "
        "haircut. The credit is denied.",
        "feoc",
    ),
    _c(
        "section-70512h-transfer-ban",
        "OBBBA §70512(h); I.R.C. §7701(a)(51)(B)",
        "No transfer of §45Q/45X/45Y/45Z/48E credits to a specified foreign entity",
        "A §6418 transfer of any of these five credits to a specified foreign "
        "entity is prohibited, effective for taxable years beginning after "
        "2025-07-04 - first tested 2026-01-01 for a calendar-year taxpayer.",
        "transfer",
    ),
    # -- Begin construction ----------------------------------------------
    _c(
        "five-percent-safe-harbor",
        "IRS begin-construction guidance (Notice 2013-29 line, carried forward)",
        "5% cost safe harbor",
        "Construction begins when the taxpayer pays or incurs at least 5% of "
        "the total cost of the facility, provided continuous efforts thereafter.",
        "begin_construction",
    ),
    _c(
        "physical-work-test",
        "IRS begin-construction guidance (Notice 2013-29 line, carried forward)",
        "Physical Work Test",
        "Construction alternatively begins when physical work of a significant "
        "nature starts, on site or at a manufacturer under a binding written "
        "contract. It is a facts-and-circumstances test with no cost threshold.",
        "begin_construction",
    ),
    _c(
        "continuity-safe-harbor",
        "IRS begin-construction guidance (Notice 2013-29 line, carried forward)",
        "Four-year continuity safe harbor",
        "Continuity is deemed satisfied if the facility is placed in service by "
        "the end of the fourth calendar year after the calendar year in which "
        "construction began.",
        "begin_construction",
    ),
    _c(
        "notice-2025-42",
        "IRS Notice 2025-42 (August 2025)",
        "5% safe harbor eliminated for wind/solar above 1.5 MW",
        "Notice 2025-42 removed the 5% cost safe harbor for wind and solar "
        "facilities with nameplate capacity above 1.5 MW, leaving the Physical "
        "Work Test as the only route to establish begin construction.",
        "begin_construction",
    ),
    _c(
        "oregon-environmental-council-vacatur",
        "*Oregon Environmental Council v. IRS*, No. 25-4400 (CKK) (D.D.C. 2026-06-06)",
        "Notice 2025-42 VACATED IN FULL - 5% safe harbor restored",
        "On 2026-06-06 the U.S. District Court for the District of Columbia "
        "vacated Notice 2025-42 in full as arbitrary and capricious under the "
        "Administrative Procedure Act and remanded. As of the verification date "
        "the 5% safe harbor is restored for wind and solar of any size.",
        "begin_construction",
        note="A government appeal and/or stay is expected. The court "
        "acknowledged the appellate timeline runs past 2026-07-04. Model the "
        "other outcome with Notice202542Status.REINSTATED_ON_APPEAL.",
    ),
    _c(
        "notice-2025-42-applicability-date",
        "IRS Notice 2025-42 (August 2025)",
        "Prospective applicability date of Notice 2025-42",
        "The notice applied to facilities beginning construction after a stated "
        "2025 cut-off rather than retroactively.",
        "begin_construction",
        confidence=Confidence.PLACEHOLDER,
        source="Existence of a prospective cut-off is standard IRS practice; "
        "the exact date was not sourced in this build.",
        note="constants.NOTICE_2025_42_APPLIES_TO_BOC_AFTER is a placeholder "
        "(2025-09-02). Confirm before relying on a late-2025 BOC date.",
    ),
    # -- Depreciation -----------------------------------------------------
    _c(
        "itc-basis-reduction",
        "I.R.C. §50(c)(3)",
        "50% ITC basis reduction",
        "Where an investment credit is claimed, the depreciable basis of the "
        "property is reduced by 50% of the credit. Depreciable basis = eligible "
        "cost less half the ITC.",
        "depreciation",
    ),
    _c(
        "macrs-recovery-periods",
        "I.R.C. §168; IRS Pub. 946 Table A-1",
        "MACRS 5-year and 15-year GDS tables",
        "Qualified energy property is generally 5-year MACRS (200% declining "
        "balance, half-year convention); certain other assets are 15-year "
        "(150% declining balance).",
        "depreciation",
    ),
    _c(
        "bonus-depreciation",
        "I.R.C. §168(k) as amended by OBBBA",
        "Bonus depreciation",
        "OBBBA restored 100% bonus expensing for qualified property acquired "
        "after 2025-01-19. Bonus is taken on the reduced (post-ITC) basis, and "
        "the remaining basis then runs the ordinary recovery table.",
        "depreciation",
        confidence=Confidence.PROVISIONAL,
        source="Rate widely reported; the acquisition-date mechanics were not "
        "confirmed against statutory text in this build.",
        note="The rate is a caller-supplied input everywhere; 1.00 is only a "
        "default.",
    ),
    _c(
        "straight-line-conventions",
        "I.R.C. §168(b)(3), §168(d)",
        "Straight-line elections and averaging conventions",
        "A taxpayer may elect straight line over 5, 15, 20 or 39 years. The "
        "half-year convention applies to personal property; nonresidential real "
        "property (39-year) uses the mid-month convention.",
        "depreciation",
        confidence=Confidence.PROVISIONAL,
        source="Statutory; the engine applies half-year uniformly.",
        note="Declared simplification: Structura applies the half-year "
        "convention to all straight-line lives including 39-year, and does not "
        "implement the mid-quarter convention.",
    ),
    # -- Transfer / direct pay -------------------------------------------
    _c(
        "section-6418-alive",
        "I.R.C. §6418",
        "§6418 transferability survived OBBBA intact",
        "Draft bills proposed a sunset; the enacted OBBBA preserved §6418 "
        "whole. Transfer is a one-time election, for cash only, with the cash "
        "neither taxable to the transferor nor deductible by the transferee.",
        "transfer",
    ),
    _c(
        "section-6417-direct-pay",
        "I.R.C. §6417",
        "§6417 elective payment (direct pay) intact",
        "Applicable entities - tax-exempt organisations, state and local "
        "governments, Indian tribal governments, Alaska Native corporations, "
        "the TVA and rural electric co-operatives - may elect a cash payment in "
        "lieu of the credit. Taxable entities may elect it only for §45Q, §45V "
        "and §45X.",
        "transfer",
        confidence=Confidence.PROVISIONAL,
        source="Survival of §6417 is from SPEC §2.2; the applicable-entity list "
        "is the statutory enumeration.",
    ),
    _c(
        "excessive-credit-transfer-penalty",
        "I.R.C. §6418(g)(2)",
        "20% excessive credit transfer penalty",
        "If a transferred credit is later disallowed, the transferee's tax is "
        "increased by the excessive amount plus a 20% penalty - which is why "
        "indemnities and credit insurance are priced into every transfer.",
        "transfer",
        confidence=Confidence.PROVISIONAL,
    ),
    _c(
        "transfer-market-2025",
        "Crux 2025 transferability market data, quoted in SPEC §2.2",
        "Transfer market $32bn (2024) -> $42bn (2025), +48%",
        "Total credit monetisation reached $63bn in 2025. Of ITC gross value, "
        "partnerships took 57%, direct transfer 28% and preferred equity 15%. "
        "For PTCs, more than 90% went by direct transfer.",
        "transfer",
        note="Market context for defaults and narration only. Never used as an "
        "arithmetic input to a deal.",
    ),
    _c(
        "itc-transfer-pricing-default",
        "Norton Rose Fulbright, *Cost of Capital: 2026 Outlook* (2026-01-29)",
        "Default ITC clearing price ~90c",
        "The ITC bridge market prices an uncovered 75% advance at roughly 67.5% "
        "net, implying a 90c clearing price on the underlying credit.",
        "transfer",
        source="SPEC §2.7 market benchmarks.",
    ),
)

CITATIONS: Mapping[str, Citation] = {c.id: c for c in _ALL}


def get_citation(citation_id: str) -> Citation:
    """Return one citation by id.

    Raises
    ------
    KeyError
        If the id is unknown. Rule modules reference ids as literals, so an
        unknown id is a bug caught by ``tests/test_tax_citations.py``.
    """
    return CITATIONS[citation_id]


def get_all_citations() -> tuple[Citation, ...]:
    """Every rule this package implements, ordered for the /current-law page.

    Grouped by module, then by declaration order within a module, which is
    roughly the order a practitioner reasons through a deal: eligibility ->
    adders -> FEOC -> begin construction -> depreciation -> transfer.
    """
    order = (
        "eligibility",
        "adders",
        "feoc",
        "begin_construction",
        "depreciation",
        "transfer",
    )
    return tuple(sorted(_ALL, key=lambda c: (order.index(c.module), _ALL.index(c))))


def citations_for_ids(ids: Iterable[str]) -> tuple[Citation, ...]:
    """Resolve the citation ids carried on a result object, de-duplicated."""
    seen: dict[str, Citation] = {}
    for cid in ids:
        if cid not in seen:
            seen[cid] = get_citation(cid)
    return tuple(seen.values())


def unverified_citations() -> tuple[Citation, ...]:
    """Every rule that is provisional or a placeholder.

    The ``/current-law`` page renders these in a separate, visually distinct
    block. Honest gaps are a feature (SPEC §4.3); silent approximation is a
    credibility failure.
    """
    return tuple(c for c in get_all_citations() if c.confidence is not Confidence.VERIFIED)
