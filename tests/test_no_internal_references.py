"""Guard: no shipping file may cite a document that is not in this repository,
and no shipping file may carry internal-deliberation voice.

Why this test exists
--------------------
Structura was built against a private build specification and a set of internal
phase documents. None of those files are published. For a while the code, the
docstrings and several strings rendered on the live site cited them anyway -
``SPEC §6.4``, ``PHASE1.md``, ``CALIBRATION.md`` - which left a reader following
a citation to a document that does not exist. The same drafting left behind
prose written *to a builder* rather than *for a reader*: instructions about what
to lead the product with, arguments for the project's own positioning, and
narration of the build process.

Both are credibility defects rather than functional ones, so nothing else in the
suite catches them, and both reappear easily the next time someone drafts a
docstring from a working note. This test is the permanent guard.

What it checks
--------------
Every shipping file - ``engine/``, ``export/``, ``lib_api/``, ``api/``, ``src/``
and the root ``*.md`` files - is scanned line by line for:

* references to the private build specification (``SPEC §…``, ``SPEC.md``,
  "per the spec", "the spec says");
* references to internal documents absent from the repository
  (``PHASE1.md``-``PHASE4.md``, ``CALIBRATION.md``, ``API_CONTRACT.md``);
* a small blocklist of deliberation phrases.

Cross-references to files that *do* ship - ``README.md``, ``LIMITS.md``,
``LIMITS_STRUCTURES.md``, ``UNVERIFIED.md``, ``DEPLOY.md`` and the package
READMEs - are fine and are not checked.

``tests/`` is excluded, because this file necessarily contains every pattern it
forbids. That exclusion is for test fixtures only; it is not a licence to move
offending prose into a test module.

If this test fails, fix the prose - do not add a pattern exemption. Where the
offending sentence carries a real fact, keep the fact and cite the real external
authority (Norton Rose Fulbright, *Cost of Capital: 2026 Outlook*; IRS Notice
2026-15; I.R.C. §48E/§45Y/§6418; Crux; the ATB; Treas. Reg. §1.704-1(b)). Where
it is internal bookkeeping, state the limitation directly and point at
``LIMITS.md``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Directories whose entire contents ship and are therefore scanned.
SCANNED_DIRS: tuple[str, ...] = ("engine", "export", "lib_api", "api", "src")

#: File extensions worth scanning. Binary and generated assets are skipped.
SCANNED_SUFFIXES: frozenset[str] = frozenset(
    {".py", ".js", ".jsx", ".ts", ".tsx", ".md", ".css", ".json"}
)

#: Path fragments that are gitignored, generated, or vendored.
EXCLUDED_PARTS: frozenset[str] = frozenset(
    {
        ".git",
        ".next",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        ".vercel",
        "__pycache__",
        "node_modules",
        "out",
        "dist",
        "build",
        "tests",
    }
)

#: ``(compiled pattern, human explanation)``. Every pattern is case-insensitive.
FORBIDDEN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bSPEC\b\s*(?:\.md)?\s*§", re.IGNORECASE),
        "cites the private build specification by section",
    ),
    (
        re.compile(r"\bSPEC\.md\b", re.IGNORECASE),
        "cites the private build specification by filename",
    ),
    (
        re.compile(r"\bper the spec\b", re.IGNORECASE),
        "cites the private build specification",
    ),
    (
        re.compile(r"\bthe spec (?:says|calls|names|requires|makes)\b", re.IGNORECASE),
        "cites the private build specification",
    ),
    (
        re.compile(r"\bPHASE[1-4]\.md\b", re.IGNORECASE),
        "references an internal phase document that is not in this repository",
    ),
    (
        re.compile(r"\bCALIBRATION\.md\b", re.IGNORECASE),
        "references an internal document that is not in this repository",
    ),
    (
        re.compile(r"\bAPI_CONTRACT\.md\b", re.IGNORECASE),
        "references an internal document that is not in this repository",
    ),
    (
        re.compile(r"\bthe whole claim\b", re.IGNORECASE),
        "internal-deliberation voice",
    ),
    (
        re.compile(r"\bthat is the moat\b", re.IGNORECASE),
        "internal-deliberation voice",
    ),
    (
        re.compile(r"\blead the product with\b", re.IGNORECASE),
        "instruction addressed to a builder, not documentation",
    ),
    (
        re.compile(r"\banyone evaluating\b", re.IGNORECASE),
        "rhetorical framing addressed at the reader",
    ),
    (
        re.compile(r"\bthe fastest way to lose\b", re.IGNORECASE),
        "internal-deliberation voice",
    ),
)


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts)


def shipping_files() -> list[Path]:
    """Every file that ships in the public repository, sorted for stable ids."""
    found: list[Path] = []

    for directory in SCANNED_DIRS:
        base = REPO_ROOT / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or _is_excluded(path.relative_to(REPO_ROOT)):
                continue
            if path.suffix in SCANNED_SUFFIXES:
                found.append(path)

    found.extend(p for p in REPO_ROOT.glob("*.md") if p.is_file())
    return sorted(found)


_FILES = shipping_files()


def test_the_guard_actually_scans_something() -> None:
    """A misconfigured walk that finds no files would pass vacuously."""
    assert len(_FILES) > 40, (
        f"only {len(_FILES)} shipping files found under {REPO_ROOT}; the walk is "
        "probably misconfigured and this guard would pass vacuously"
    )


@pytest.mark.parametrize(
    "path", _FILES, ids=[str(p.relative_to(REPO_ROOT)) for p in _FILES]
)
def test_no_internal_references_or_deliberation_voice(path: Path) -> None:
    relative = path.relative_to(REPO_ROOT)
    text = path.read_text(encoding="utf-8", errors="replace")

    offences: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern, reason in FORBIDDEN_PATTERNS:
            match = pattern.search(line)
            if match is None:
                continue
            offences.append(
                f"  {relative}:{lineno}: {reason}\n"
                f"      matched: {match.group(0)!r}\n"
                f"      line:    {line.strip()[:160]}"
            )

    assert not offences, (
        f"{len(offences)} internal reference(s) or deliberation phrase(s) in "
        f"{relative}:\n" + "\n".join(offences) + "\n\n"
        "Fix the prose rather than the pattern list. Keep the fact, cite the "
        "real external authority, or state the limitation directly and point "
        "at LIMITS.md. See this module's docstring."
    )
