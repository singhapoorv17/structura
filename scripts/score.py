"""Acceptance scorer.

Runs the acceptance suite, groups outcomes by gate id, and prints a score per
phase. Exit status is 0 when every gate passes.

Usage:
    python scripts/score.py            # score everything
    python scripts/score.py G1 G2      # score selected phases
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import OrderedDict

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
HISTORY = REPO / ".acceptance-history.json"

PHASES = OrderedDict(
    [
        ("G1", "Provenance"),
        ("G2", "Comps corpus"),
        ("G3", "Intake and premise checks"),
        ("G4", "SPV lease with residual-value guarantee"),
        ("G5", "Recommendation"),
        ("G6", "Comparison"),
        ("G7", "Per-party ledgers"),
        ("G8", "Structure chart"),
        ("G9", "Chat rail"),
        ("G10", "Hygiene"),
    ]
)


class GateCollector:
    """Records the outcome of every test carrying a ``gate`` marker."""

    def __init__(self) -> None:
        self.outcomes: dict[str, bool] = {}

    def pytest_runtest_logreport(self, report):  # noqa: D102
        if report.when != "call":
            # A collection or setup error still fails the gate it belongs to.
            if report.failed and report.when == "setup":
                for gate_id in self._gates(report):
                    self.outcomes[gate_id] = False
            return
        for gate_id in self._gates(report):
            passed = report.passed
            # A gate asserted by several tests passes only if all of them pass.
            self.outcomes[gate_id] = self.outcomes.get(gate_id, True) and passed

    @staticmethod
    def _gates(report) -> list[str]:
        for marker in getattr(report, "gate_ids", []) or []:
            yield marker  # pragma: no cover - populated by the hook below

    # pytest does not carry markers onto the report, so the ids are stamped on
    # in ``pytest_runtest_makereport`` inside the acceptance conftest.


def run(selected: list[str]) -> int:
    collector = GateCollector()
    args = ["-m", "acceptance", "-q", "--no-header", str(REPO / "tests" / "acceptance")]
    pytest.main(args, plugins=[collector])

    phases = [p for p in PHASES if not selected or p in selected]
    total_pass = total_all = 0
    failures: list[str] = []

    print()
    print(f"{'phase':<44}{'gates':>12}")
    print("-" * 56)
    for phase in phases:
        ids = sorted(
            (g for g in collector.outcomes if g.split(".")[0] == phase),
            key=_sort_key,
        )
        if not ids:
            print(f"{phase + ' ' + PHASES[phase]:<44}{'no tests':>12}")
            continue
        passed = sum(1 for g in ids if collector.outcomes[g])
        total_pass += passed
        total_all += len(ids)
        failures += [g for g in ids if not collector.outcomes[g]]
        mark = "OK" if passed == len(ids) else "  "
        print(f"{phase + ' ' + PHASES[phase]:<44}{f'{passed}/{len(ids)}':>9} {mark}")

    print("-" * 56)
    score = (total_pass / total_all) if total_all else 0.0
    print(f"{'SCORE':<44}{f'{total_pass}/{total_all}':>9} {score:.2f}")

    if failures:
        print()
        print("failing gates: " + ", ".join(failures))

    _record(score, total_pass, total_all)
    return 0 if total_all and total_pass == total_all else 1


def _sort_key(gate_id: str) -> tuple[int, int]:
    phase, _, rest = gate_id.partition(".")
    return int(phase[1:]), int(rest or 0)


def _record(score: float, passed: int, total: int) -> None:
    """Append this run to the history so the loop can detect no-progress passes."""
    history = []
    if HISTORY.exists():
        history = json.loads(HISTORY.read_text())
    history.append({"score": score, "passed": passed, "total": total})
    HISTORY.write_text(json.dumps(history, indent=2))

    recent = [h["passed"] for h in history[-3:]]
    if len(recent) == 3 and len(set(recent)) == 1:
        print()
        print("NO PROGRESS: three consecutive runs at the same score. Stop the loop.")


if __name__ == "__main__":
    sys.exit(run([a for a in sys.argv[1:] if a.startswith("G")]))
