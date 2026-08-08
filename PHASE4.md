# Phase 4 — Lender-grade Excel export

Scope: SPEC.md §6.5 only. `openpyxl`, iterative calculation, live formulas,
named ranges, banker formatting, and the assertion that the workbook and the
Python engine agree. **No tax sheet, no structure comparison** — those are
Phases 2 and 3 and are explicitly deferred below.

Reproduce with `.venv/bin/pytest tests/test_export_*.py -q`.
**350 export tests pass. 1,591 tests pass across the whole repository.**

---

## Why this phase matters

SPEC.md §3.2 names three things SAM cannot do for these structures. This is one
of them: SAM's "Send to Excel with Equations" is Windows-only, available for
Residential / Commercial / Single Owner **only** (explicitly not partnership
flip or sale-leaseback), and is documented to *approximate* SAM's own
calculations. Structura emits a cross-platform `.xlsx` in which the debt
quantum itself is a formula.

SPEC.md §4.2 is the standard the phase has to clear: *"The Excel export carries
live formulas, not pasted values, or the 'lender-grade' claim is false."*

---

## What is done

### `export/` — the package

| Module | What it is |
|---|---|
| `export/api.py` | `build_workbook(project, terms, engine_result, path) -> Path`. The single public entry point. Runs the engine itself if the caller does not pass a result. |
| `export/workbook.py` | `WorkbookBuilder`: calculation properties, cell/row/name helpers, the cross-sheet reference registry and the **sheet registry**. |
| `export/styles.py` | The blue-input / black-formula / green-link / amber-solver convention, number formats, borders, widths. |
| `export/model.py` | `ModelBundle` — the frozen container every sheet builder receives, plus the enum→integer codes Excel needs. |
| `export/sheets/` | One module per worksheet, each self-registering. |

### The eight sheets

| Tab | Contents |
|---|---|
| **Summary** | One page: the deal, the headline result, the **binding constraint**, sponsor economics, sources & uses, an eight-row credit-test table with live PASS/FAIL, four model-integrity checks, the disclaimer. Every figure is a link. |
| **Inputs** | Every driver as a named, blue, editable cell — capacity, capex, construction period, production, degradation, contracted and merchant price and escalation, offtake term, opex, tax rate and treatment, depreciation life, target DSCR, tenor, rate, fees, amortisation style, grace, gearing cap, tail, DSRA cover, sweep, covenant, lock-up, LLCR/PLCR floors, discount rate. Plus a derived unit-conversion block and the single amber solver-derived cell. |
| **Construction** | Month-by-month drawdown, IDC, commitment fee, upfront fee, the **circular** debt-funded-capex cell that closes the loop, total funding requirement, sources & uses. |
| **Operations** | Production → contracted/merchant split with escalation and degradation → revenue → opex → EBITDA → depreciation → NOL → cash tax → **CFADS**, with the CFADS identity asserted on the sheet. |
| **Debt** | Facility shape (tenor, tail clamp, grace, annuity factor); the sculpting build-up; **all three amortisation styles sized side by side**; the five sizing tests and which one binds; the amortisation schedule; DSCR, DSRA target, LLCR and PLCR series; the coverage summary. |
| **Waterfall** | CFADS → senior interest → senior principal → DSRA (drawn up to cure, topped back down) → MRA → cash sweep (inverse order of maturity) → lock-up → subordinated → distributions, with a per-period cash-conservation check. |
| **Returns** | Period-0 equity cashflow, the lender's cashflow, and **Excel's own `IRR` / `XIRR` / `NPV`** plus MOIC, payback, all-in cost of debt, after-tax cost of debt and WACC. |
| **Notes** | How to use it, the two circularities and why they are deliberate, solver-derived versus formula-derived, ten modelling conventions, what the workbook deliberately does not do, source attribution, the MIT licence, the disclaimer. |

### The SPEC §9 gate

`xl/workbook.xml` carries
`calcId="191029" fullCalcOnLoad="1" iterate="1" iterateCount="100" iterateDelta="0.0001"`.
Asserted in `test_export_workbook.py`. A companion test asserts the *premise*
of the `fullCalcOnLoad` requirement — that no formula cell carries a cached
`<v>` — so the requirement cannot silently become stale.

---

## Formula-derived versus solver-derived

**Formula-derived — everything except one cell.** The debt quantum, all five
sizing tests, the sculpted service profile under any of the three amortisation
styles, the interest/principal split, the closing balance, DSCR, LLCR, PLCR,
the DSRA target, IDC, both fees, total project cost, gearing, the equity
cheque, the entire waterfall and every return metric are live Excel formulas
reading the Inputs sheet.

That includes **both circularities**:

* **Funding.** `TPC = capex + fees + IDC + DSRA` and `D = MIN(D_DSCR, gearing ×
  TPC)`. Closed by one cell — debt-funded capex is the facility net of its own
  fees and capitalised interest — and resolved by Excel's iterative
  calculation. `engine/circularity.py` solves the identical fixed point with
  Brent's method; the tests assert they land on the same point.
* **Tax.** Under tax treatment 3, interest is deductible, so cash tax depends
  on the debt schedule which depends on CFADS which depends on cash tax. Also
  live, also iterative.

**Solver-derived — one cell: the applied grace period** (Inputs §10, amber
fill, documented on Notes). A pure PV sculpt can imply debt service below the
interest accruing in the early periods when CFADS ramps steeply at a high rate.
The engine lengthens the interest-only holiday one period at a time until every
period amortises non-negatively. That is a *search*, not an expression, so
Excel cannot re-derive it. It is carried across as a flagged input; everything
downstream of it is live.

`test_export_workbook.py::test_only_one_solver_derived_cell_exists_and_it_is_flagged`
counts the amber cells and fails if a second one ever appears.

---

## Verification

### The formula evaluator

Excel is not available in this environment, so `tests/test_export_evaluator.py`
implements a **minimal Excel evaluator**: a tokeniser, a recursive-descent
parser for the emitted grammar, defined-name and cross-sheet reference
resolution, and a Gauss-Seidel calculation loop that iterates the whole formula
graph to a fixed point — exactly what Excel does with `iterate="1"`. It
supports `IF`, `AND`, `OR`, `MIN`, `MAX`, `SUM`, `SUMPRODUCT`, `ROUND`, `INT`,
`ABS`, `NPV`, `IRR`, `XIRR`, `CHOOSE`, `INDEX`, `COUNTIF` and `EDATE`, and
raises on anything else rather than guessing. It has 26 tests of its own,
including one that checks it resolves a circular pair the way Excel does.

The evaluator is *pessimistic* relative to Excel: it sweeps every cell in
column-major order rather than following a dependency chain, so its iteration
count is an upper bound. The default deal settles in **29 passes** against
Excel's budget of 100; the slowest of the twelve test cases is well inside it,
and that is asserted.

### Agreement with the engine

`tests/test_export_agreement.py` runs **twelve deal shapes** — gearing-bound,
DSCR-bound, level payment, fixed principal, a two-year grace period,
semi-annual periods, a merchant tail, tail-bound, LLCR-bound, a 50% cash sweep,
full project-level tax, and a time-varying DSCR target — and for each asserts
that the evaluated workbook reproduces the engine on:

* debt quantum and the binding-constraint label;
* IDC, both fees, initial DSRA, total project cost, debt and equity at COD,
  gearing;
* revenue, opex, EBITDA, cash tax and CFADS, period by period;
* opening balance, interest, debt service, principal and closing balance,
  period by period;
* DSCR, minimum DSCR, LLCR, PLCR, weighted average life, DSRA targets;
* distributions, DSRA closing balance and senior closing balance from the
  waterfall;
* equity cashflows, equity IRR, NPV, MOIC, payback, effective and after-tax
  cost of debt, and WACC.

Money is compared at a **relative 1e-7**, ratios and rates at an **absolute
1e-9**. Both are floating-point noise floors, not modelling tolerances: the two
paths differ only in association order.

There is also an *engine-independent* test that re-derives the schedule from
the workbook's own numbers — `interest = rate × opening`,
`principal = debt service − interest`, `closing = opening − principal` — checks
the chain terminates at zero and that principal sums to the facility drawn.
That is the identity a credit officer checks by hand.

### The golden recalculation test

SPEC §6.5 asks for "change the DSCR input cell and every dependent figure
recalculates correctly". Three tests do exactly that against the formula graph:
overwrite `Target_DSCR`, `Interest_Rate` or `Amort_Style_Code` in the loaded
workbook, recalculate, and assert the debt quantum, IDC, the equity cheque and
the sponsor IRR all move to the answer the engine gives for the changed input.

### Hygiene

`tests/test_export_hygiene.py` asserts no engine output appears as a hard-coded
number anywhere (the "answer key" test), bounds which cells may legitimately
hold static numbers at all, checks for email addresses, filesystem paths,
identifier-shaped strings and account-length digit runs, checks the workbook
metadata carries no author identity, and checks that the disclaimer appears
verbatim on both Summary and Notes.

---

## Extension points for Phases 2 and 3

Sheets register themselves:

```python
register_sheet("Tax", build_tax, display_order=55, build_order=35)
```

`display_order` is the tab position, `build_order` is when the builder runs.
Existing sheets are spaced ten apart and **two gaps are reserved**:

| Slot | Sheet | Phase |
|---|---|---|
| `display_order=55` | **Tax** — §48E/§45Y eligibility and phase-down, FEOC / material assistance cost ratio, domestic content adder, begin-construction fork, MACRS and bonus depreciation, the 50% ITC basis reduction | 2 |
| `display_order=75` | **Structures** — partnership flip, T-flip, preferred equity, §6418 transfer, sale-leaseback, and the ranked cost-of-capital comparison; §704(b) capital accounts, DRO, outside basis | 3 |

`test_export_workbook.py::test_registry_leaves_room_for_the_deferred_phase_2_and_3_sheets`
fails if either gap is ever closed, and
`test_a_new_sheet_can_be_registered_and_appears_in_the_output` exercises the
extension point end to end.

A new sheet reaches existing values two ways, and should prefer the second:

* `wb.ref("ops.cfads", t)` / `wb.span("debt.principal", t, n)` — the row
  registry, for period-by-period rows. Requires a `build_order` *after* the
  sheet that writes the row.
* `Senior_Debt`, `Total_Project_Cost`, `CFADS_Series`, … — defined names.
  Excel resolves these at calculation time, so there is **no build ordering
  constraint at all**. 116 names are defined; `SheetWriter.formula_row(...,
  series_name=...)` names a whole row in one line.

A Tax sheet will want `build_order` around 35: after Operations, so it can read
the CFADS and depreciation rows, and before Waterfall, so the waterfall can
take a tax line from it.

---

## Deliberately deferred

| Deferred to | Item |
|---|---|
| Phase 2 | The Tax sheet. Nothing tax-law-dependent is in this workbook; the Notes sheet says so explicitly and lists what is missing. |
| Phase 3 | The Structures sheet and the five-structure comparison. Back-leverage: the waterfall exposes a subordinated-debt-service **input row** but no junior tranche is sized. |
| Phase 3 | Multiple senior tranches, refinancing. One facility. |
| Phase 5 | Scenario grids (P50/P90/P99, merchant share, rate shocks). Change the case and re-export. |
| Phase 5 | Charts. The workbook is numbers only; DSCR and balance charts are a UI-phase item. |
| Whoever owns the build files | `pyproject.toml` still lists `packages = ["engine"]` and keeps `openpyxl` in the `excel` extra. Add `"export"` to `packages` and promote `openpyxl>=3.1` to a runtime dependency. A `make export` target would be a reasonable addition to the Makefile. Both files were off-limits to this phase. |

---

## Known divergences from the engine, and why

None of these affects any of the twelve tested cases; all are declared here and
on the Notes sheet.

1. **Materiality floors on display ratios.** The waterfall's DSCR row and its
   covenant and lock-up flags are gated on debt service above **$1**, and the
   LLCR/PLCR series on a balance above **$1**. The engine uses `> 0`. Without
   the floor, a period holding a cent of floating-point residue after final
   maturity prints a ratio in the billions, which looks like a defect and also
   stops the iteration converging. A cent of debt service is not a debt
   service.
2. **Grid width is fixed at generation.** Rows extend over the project life and
   construction period as they stood when the file was written. *Shortening*
   either is handled live by the masking formulas — the model recalculates
   correctly. *Lengthening* beyond the built grid needs a re-export.
3. **A zero-month construction period** puts the whole draw in month 1 with
   interest suppressed, which reproduces the engine's instantaneous-construction
   branch exactly, but the grid still shows one column.
4. **The DSRA formula reaches forward a fixed number of periods**, sized from
   the engine's `DSRA_Months` at generation time. Increasing DSRA cover beyond
   that in Excel would under-reserve; decreasing it is exact.
5. **Pre-tax equity IRR is not on the sheet.** The engine only produces it when
   the caller supplies a companion tax-free waterfall run, which
   `engine.run_model` does not do. Reporting a guess would be worse than
   omitting it.
6. **Excel's `IRR` needs a sign change.** Where the engine returns `None` for a
   series that never crosses zero, the workbook prints
   `"not within project life"` rather than a number. Asserted as agreement, not
   as a mismatch.

---

## Honest positioning

Nothing in this workbook is mathematically novel — debt sculpting, LLCR/PLCR
and the IDC circularity are decades-old practice, and Edward Bodmer gives away
spreadsheet implementations of all of it. What Phase 4 contributes is that the
spreadsheet is **generated, versioned, tested and reproducible**: the same
inputs produce the same file, the formula graph is asserted against an
independent Python implementation across twelve deal shapes, and every check
row on the sheet is also a test in CI. The Notes sheet says this in the
workbook itself, because overclaiming to a practitioner audience is the fastest
way to lose it (SPEC §11).
