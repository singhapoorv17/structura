# Structura

A project-finance structuring engine for energy assets. Enter a project and it returns the sized debt, the full cash waterfall, and a comparison of five capital structures under current US tax law — with an Excel model containing live formulas rather than pasted values.

**[structura-pf.vercel.app](https://structura-pf.vercel.app)** · [Current law](https://structura-pf.vercel.app/current-law) · [Limitations](LIMITS.md)

---

## What it does

One project, sculpted once to a target DSCR, run through the five structures used in the 2026 US market:

| Structure | Implementation |
|---|---|
| Partnership flip (yield-based and fixed-date) | §704(b) capital accounts, DRO caps, outside basis, §704(d) suspended losses |
| T-flip (flip + §6418 transfer) | Flip mechanics with credits transferred rather than retained |
| Preferred equity partnership | Preferred return, redemption, waterfall priority |
| Direct transfer (§6418) | Discount pricing, post-COD settlement |
| Sale-leaseback | True-lease tests, residual, lessor yield solve |

Example — 100 MW / 400 MWh contracted BESS, $140M capex:

| # | Structure | Sponsor IRR | Effective cost of capital | Sponsor equity |
|---|---|---:|---:|---:|
| 1 | Partnership flip | 14.85% | 8.03% | $27.9M |
| 2 | T-flip | 14.01% | 7.04% | $65.9M |
| 3 | Direct transfer | 11.36% | 6.84% | $80.9M |
| 4 | Preferred equity | 3.31% | 13.69% | $32.4M |
| 5 | Sale-leaseback | not meaningful | 9.80% | $7.0M |

Sale-leaseback returns a 41% IRR on a $7.0M equity base. An IRR computed on an equity base below 10% of the funding requirement is reported as not meaningful and the structure is ranked on NPV instead.

---

## Tax treatment

Rules are implemented with citations and a verification date, and rendered at `/current-law`.

- **§48E / §45Y under OBBBA (P.L. 119-21).** Wind and solar require begin-construction on or before 2026-07-04; otherwise the facility must be placed in service by 2027-12-31. Storage, geothermal, nuclear and hydro retain §48E on a begin-construction basis through 2033, then 75% (2034), 50% (2035), zero from 2036.
- **§6418 transferability and §6417 direct pay** remain available. §70512(h) prohibits transfer of §45Q/45X/45Y/45Z/48E credits to a specified foreign entity.
- **FEOC / Material Assistance Cost Ratio**, effective 2026-01-01 under IRS Notice 2026-15, as a pass/fail gate on eligibility.
- **Domestic content adder** at the 2026 threshold of 50%.
- **Begin-construction method** is modelled both ways. Notice 2025-42 removed the 5% cost safe harbor for wind and solar above 1.5 MW; the U.S. District Court for D.C. vacated that notice on 2026-06-06 in *Oregon Environmental Council v. IRS*, No. 25-4400 (CKK), and an appeal is expected. Eligibility can be evaluated under either outcome.

---

## Comparison with existing tools

**SAM** (National Laboratory of the Rockies, BSD-3) models partnership flips — leveraged and all-equity — sale-leaseback, and DSCR-based debt sizing, which is its default sizing mode. It does not maintain §704(b) capital accounts, deficit restoration obligations, outside basis or suspended losses; its flip is a fixed pre-flip/post-flip percentage split with an IRR-triggered flip date. Its release notes contain no reference to OBBBA, FEOC or §6418 transferability. Its "Send to Excel with Equations" export is Windows-only and is not available for the partnership flip or sale-leaseback models.

**Ed Bodmer** publishes a large library of free Excel models covering debt sculpting, DSRA, circularity, and partnership flip mechanics including capital accounts and DROs. The underlying methods overlap substantially with what is implemented here. Those models carry no version control, no test suite, and no updates for the 2025–26 tax changes.

Structura is a web tool with a test suite and dated citations. The modelling techniques are not novel; the packaging and the currency of the tax treatment are what differ.

---

## Architecture

```
        inputs / reference deal
                  │
    ┌─────────────▼─────────────┐
    │  engine/                  │  DSCR sculpting · sizing tests (LLCR/PLCR/
    │                           │  gearing/tail) · DSRA · IDC circularity ·
    └─────────────┬─────────────┘  cash waterfall · returns
                  │
    ┌─────────────▼─────────────┐
    │  engine/tax/              │  §48E/§45Y eligibility · FEOC/MACR ·
    │                           │  adders · MACRS + basis reduction ·
    └─────────────┬─────────────┘  §6418 transfer · begin-construction method
                  │
    ┌─────────────▼─────────────┐
    │  engine/structures/       │  §704(b) ledger · five structures ·
    │                           │  flip solve (brentq) · ranked comparison
    └─────────────┬─────────────┘
                  │
       ┌──────────┴──────────┐
       ▼                     ▼
  Next.js UI            export/  →  .xlsx with live formulas
```

Python is required for the Excel export: `openpyxl` is the only library among those evaluated that writes `iterate="1"` into the workbook. Debt sculpting is genuinely circular (IDC ↔ debt size ↔ fees ↔ DSRA), so without iterative calculation the exported model opens with circular-reference warnings.

---

## Verification

1,941 tests.

- The workbook's formulas are checked against the Python engine by a formula evaluator in the test suite (tokeniser, recursive-descent parser, Gauss-Seidel iteration), across 12 deal shapes, to 1e-7 on money. Three tests overwrite an input, recalculate, and compare against a fresh engine run.
- One cell in the workbook is solver-derived rather than a formula — the applied grace period, which is a search. It is highlighted and documented on the Notes sheet, and a test fails if a second one appears.
- A property test asserts that sources do not exceed uses across all five structures.
- A round-trip test asserts that the inputs published by `/api/reference-deals` reproduce each reference deal exactly.

```bash
make test     # full suite
make gate     # confirms openpyxl writes iterate="1"
make demo     # runs the three reference deals
```

---

## Reference deals

| Deal | Winner | Sponsor IRR | Minimum DSCR (benchmark) |
|---|---|---:|---|
| 100 MW BESS, contracted toll | Partnership flip | 14.85% | 2.09x (1.15–1.20x) |
| 150 MWac solar, safe-harboured | T-flip | 11.72% | 1.45x (1.30x) |
| 48 MW data-centre powered shell | Partnership flip | 15.10% | 1.33x (1.15x) |

On the data-centre deal the direct transfer and T-flip are returned as infeasible: no §48E credit attaches to a powered shell.

---

## Licence and sources

MIT for the code. This is an illustrative modelling tool and not tax, legal, accounting or investment advice.

Market benchmarks are drawn from Norton Rose Fulbright, *Cost of Capital: 2026 Outlook* (2026-01-29) and Crux credit-monetisation data. Cost defaults draw on the ATB 2024 v4.0.0 dataset (CC-BY 4.0, DOI [10.25984/2377191](https://doi.org/10.25984/2377191)), published by the National Laboratory of the Rockies — renamed from the National Renewable Energy Laboratory in December 2025, so older `nrel.gov` links no longer resolve.

Built by [Apoorv Singh](https://github.com/singhapoorv17).
