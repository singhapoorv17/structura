"""G10 — the rules that hold in every phase, not just the one being built."""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

SKIP_DIRS = {
    ".git",
    ".next",
    ".venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    "tests",
}

TEXT_SUFFIXES = {".py", ".js", ".jsx", ".css", ".md", ".json", ".toml", ".yaml", ".yml"}


def _shipping_files():
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(REPO).parts):
            continue
        yield path


@pytest.mark.gate("G10.1")
def test_internal_reference_guard_passes():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_no_internal_references.py", "-q"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout[-4000:]


@pytest.mark.gate("G10.2")
def test_full_suite_is_green():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout[-4000:]


@pytest.mark.gate("G10.3")
def test_no_article_bodies_are_stored():
    """A stored article body is a legal problem and a quality problem.

    The structural proxy: no string in the comps data may run past the caps in
    the record schema, and no data file may carry a paragraph of prose.
    """
    from comps.corpus import iter_records
    from comps.schema import LENGTH_CAPS

    overlong = []
    for record in iter_records():
        for field, value in record.flat_strings():
            cap = LENGTH_CAPS.get(field, LENGTH_CAPS["_default"])
            if len(value) > cap:
                overlong.append(f"{record.key}.{field}: {len(value)} > {cap}")
    assert not overlong, "\n".join(overlong)


# Neutral verifiable fact only. Each pattern below is a claim about someone
# else's product, or an argument for this one, rather than a description of
# what this code does.
COMPETITOR_FRAMING = [
    r"\bno free tool\b",
    r"\bnobody (?:else )?(?:does|models|builds)\b",
    r"\bprovably cannot\b",
    r"\bcannot produce\b",
    r"\bunlike (?:any )?other\b",
    r"\bthe only (?:tool|product|platform)\b",
    r"\bfirst of its kind\b",
    r"\bbest[- ]in[- ]class\b",
]


@pytest.mark.gate("G10.4")
def test_no_competitor_framing_in_shipping_strings():
    hits = []
    for path in _shipping_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in COMPETITOR_FRAMING:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                line = text.count("\n", 0, match.start()) + 1
                hits.append(f"{path.relative_to(REPO)}:{line}: {match.group(0)!r}")
    assert not hits, "\n".join(hits)


@pytest.mark.gate("G10.5")
def test_restated_facts_are_labelled_as_echoes():
    from comps.corpus import iter_records

    unlabelled = []
    for record in iter_records():
        for field, cell in record.provenanced_cells():
            if cell.provenance.value != "stated":
                continue
            if cell.is_restatement and not cell.echo_of:
                unlabelled.append(f"{record.key}.{field}")
    assert not unlabelled, "restatements without an echo_of pointer: " + ", ".join(
        unlabelled
    )
