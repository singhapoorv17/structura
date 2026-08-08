"""The citation registry is the moat, so it is tested like one.

SPEC.md §4.1 requires every tax rule to carry a citation and a verified-on date,
rendered by a `/current-law` page. SPEC §10.4 requires every rule in §2 to have
a test *and* a citation. These tests enforce that mechanically:

* every citation is complete (authority, plain English, source, date);
* every citation id referenced by a rule module resolves;
* every rule result carries citations;
* every uncertain rule is disclosed in ``UNVERIFIED.md``.

The last one is the important one. It makes it impossible to add a guessed
threshold without also declaring it.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from engine.tax import (
    BeginConstructionMethod,
    Confidence,
    ForeignEntityFlags,
    LAW_VERIFIED_ON,
    TaxProject,
    Technology,
    citations_for_ids,
    compute_tax,
    get_all_citations,
    get_citation,
    unverified_citations,
)

TAX_PACKAGE = Path(__file__).resolve().parents[1] / "engine" / "tax"
UNVERIFIED_MD = TAX_PACKAGE / "UNVERIFIED.md"
README_MD = TAX_PACKAGE / "README.md"


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------


def test_registry_is_not_empty() -> None:
    assert len(get_all_citations()) >= 25


@pytest.mark.parametrize("citation", get_all_citations(), ids=lambda c: c.id)
def test_every_citation_is_complete(citation: object) -> None:
    assert citation.id  # type: ignore[attr-defined]
    assert citation.authority  # type: ignore[attr-defined]
    assert citation.title  # type: ignore[attr-defined]
    assert len(citation.plain_english) > 40, "a one-word summary is not an explanation"  # type: ignore[attr-defined]
    assert citation.source  # type: ignore[attr-defined]
    assert isinstance(citation.verified_on, date)  # type: ignore[attr-defined]
    assert citation.module  # type: ignore[attr-defined]


def test_citation_ids_are_unique() -> None:
    ids = [c.id for c in get_all_citations()]
    assert len(ids) == len(set(ids))


def test_every_rule_is_verified_on_the_stated_date() -> None:
    assert LAW_VERIFIED_ON == date(2026, 8, 6)
    assert all(c.verified_on == LAW_VERIFIED_ON for c in get_all_citations())


def test_unknown_citation_id_raises() -> None:
    with pytest.raises(KeyError):
        get_citation("no-such-rule")


# ---------------------------------------------------------------------------
# Every id referenced anywhere in the package must resolve
# ---------------------------------------------------------------------------


def _referenced_ids() -> set[str]:
    """Scrape ``citation_ids=(...)`` literals out of the rule modules.

    A cheap but effective guard: a typo in a citation id would otherwise fail
    only at render time on the /current-law page.
    """
    known = {c.id for c in get_all_citations()}
    found: set[str] = set()
    for path in TAX_PACKAGE.glob("*.py"):
        if path.name == "citations.py":
            continue
        for literal in re.findall(r'"([a-z0-9]+(?:-[a-z0-9]+)+)"', path.read_text()):
            if literal in known or literal.count("-") >= 2:
                found.add(literal)
    return found


def test_every_referenced_citation_id_resolves() -> None:
    unknown = {cid for cid in _referenced_ids() if cid not in {c.id for c in get_all_citations()}}
    assert not unknown, f"unknown citation ids referenced: {sorted(unknown)}"


def test_every_registered_citation_is_actually_used_by_a_rule() -> None:
    """No decorative citations. The registry describes the code, not a wish."""
    orphaned = {c.id for c in get_all_citations()} - _referenced_ids()
    assert not orphaned, f"citations registered but never cited: {sorted(orphaned)}"


# ---------------------------------------------------------------------------
# Results carry their authority
# ---------------------------------------------------------------------------


def test_a_full_run_carries_citations_from_every_module() -> None:
    project = TaxProject(
        technology=Technology.SOLAR,
        capacity_mw=100.0,
        capex=100_000_000.0,
        placed_in_service_date=date(2029, 6, 30),
        begin_construction_date=date(2026, 7, 1),
        begin_construction_method=BeginConstructionMethod.FIVE_PERCENT_SAFE_HARBOR,
        cost_incurred_pct_at_boc=0.06,
        is_pwa_compliant=True,
        domestic_content_pct=0.60,
        foreign_entity_flags=ForeignEntityFlags(
            received_material_assistance_from_pfe=False
        ),
    )
    result = compute_tax(project)
    modules = {c.module for c in citations_for_ids(result.citation_ids)}

    assert {
        "eligibility",
        "adders",
        "feoc",
        "begin_construction",
        "depreciation",
        "transfer",
    } <= modules


def test_citations_for_ids_deduplicates() -> None:
    resolved = citations_for_ids(
        ["base-and-pwa-rate", "base-and-pwa-rate", "itc-basis-reduction"]
    )
    assert len(resolved) == 2


# ---------------------------------------------------------------------------
# Honest gaps are mandatory, not optional
# ---------------------------------------------------------------------------


def test_unverified_md_exists_and_declares_its_verification_date() -> None:
    text = UNVERIFIED_MD.read_text()
    assert "2026-08-06" in text


def test_every_uncertain_rule_is_disclosed_in_unverified_md() -> None:
    """You cannot ship a guessed threshold without declaring it."""
    text = UNVERIFIED_MD.read_text()
    missing = [c.id for c in unverified_citations() if c.id not in text]

    assert not missing, f"undisclosed uncertain rules: {missing}"


def test_placeholders_and_provisionals_carry_a_note() -> None:
    for citation in unverified_citations():
        if citation.confidence is Confidence.PLACEHOLDER:
            assert citation.note, f"{citation.id} is a placeholder with no note"


def test_readme_documents_the_law_update_runbook() -> None:
    text = README_MD.read_text().lower()
    assert "when the law changes" in text
    assert "citations.py" in text
