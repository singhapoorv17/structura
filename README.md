# Structura

**A $5,995 spreadsheet, an open-source engine, and the 2026 tax code — free.**

Structura is a project-finance structuring engine for energy deals. Put in a project; get back the sized debt, the full cash waterfall, and a side-by-side comparison of every capital structure available under **August 2026 law** — plus a lender-grade Excel model with **live formulas** you can send to a credit committee.

It is not "a partnership flip model." Post-OBBBA, pure flips are roughly 30% of the market and shrinking; hybrids, transfers and preferred equity dominate. Structura is a **structure selector** built on a debt-sculpting spine.

🔗 **[Live demo → structura-pf.vercel.app](https://structura-pf.vercel.app)** · 📖 **[Current law](https://structura-pf.vercel.app/current-law)** · ⚠️ **[What this does not claim](LIMITS.md)**

---

## What it does

Given a project, Structura runs the **same deal through five live 2026 structures** and ranks them on sponsor after-tax IRR and effective cost of capital:

| | Structure | Modelled with |
|---|---|---|
| 1 | **Partnership flip** (yield-based and fixed-date) | Real §704(b) capital accounts, DRO caps, outside basis, §704(d) suspended losses |
| 2 | **T-flip / hybrid** (flip + §6418 transfer) | The near-universal current structure |
| 3 | **Preferred equity partnership** | Preferred return, redemption, waterfall priority |
| 4 | **Direct transfer** (§6418) | Discount pricing, post-COD settlement timing |
| 5 | **Sale-leaseback** | True-lease tests, residual, lessor yield solve |

Worked example — a 100 MW / 400 MWh contracted BESS, $140M capex:

| # | Structure | Sponsor IRR | Eff. cost of capital | Sponsor equity |
|---|---|---:|---:|---:|
| 1 | Partnership flip | **14.85%** | 8.03% | $27.9M |
| 2 | T-flip | 14.01% | 7.04% | $65.9M |
| 3 | Direct transfer | 11.36% | 6.84% | $80.9M |
| 4 | Preferred equity | 3.31% | 13.69% | $32.4M |
| 5 | Sale-leaseback | *not meaningful* | 9.80% | $7.0M |

That last row is the point: sale-leaseback shows a 41% headline IRR on a $7M equity base. Structura **refuses to rank on a meaningless rate** and demotes it, showing NPV instead. A naive tool would have called it the winner.

---

## Why it exists

The knowledge in this repo is transmitted by folklore and expensive spreadsheets. As of August 2026:

- A single partnership-flip Excel model sells for **$5,995** (Woodlawn Associates).
- Pivotal180 charges **$900 self-paced / $3,200 live** for renewable PF modelling, and the same again for tax equity; Forvis Mazars charges **$3,200–$4,800/seat**.
- There is **no credible free browser-based project-finance debt-sizing and sculpting tool** in existence. Searches surface real-estate DSCR loan-qualification calculators — a different thing entirely.

Meanwhile the law moved and the tools did not. See below.

---

## The current-law engine (the part that is actually differentiated)

Every rule carries a citation and a `verified_on` date, rendered at `/current-law`.

- **§48E/§45Y bifurcation (OBBBA, P.L. 119-21).** Wind and solar had to **begin construction on or before 2026-07-04**; missing it means placed-in-service by **2027-12-31** or nothing. **Storage, geothermal, nuclear and hydro keep full §48E through 2033**, then 75%/50%/0%.
- **§6418 transferability is alive** (not repealed), §6417 direct pay intact, with the new **§70512(h)** prohibition on transfers to a specified foreign entity.
- **FEOC / Material Assistance Cost Ratio** (effective 2026-01-01, IRS Notice 2026-15) as a **pass/fail gate on eligibility**, not a footnote.
- **Domestic content** at the 2026 **50%** threshold.
- ⚖️ **The begin-construction litigation, as a toggle.** Notice 2025-42 killed the 5% safe harbor; the D.C. district court **vacated it on 2026-06-06** (*Oregon Environmental Council v. IRS*, No. 25-4400 (CKK)), restoring the safe harbor, with an appeal expected. Structura models **both outcomes** as a scenario switch, because a project's eligibility genuinely depends on how that appeal lands.

---

## Methods and honesty

**How this differs from NREL/NLR's SAM.** SAM is the real incumbent and it is good. Being straight about it:

| | SAM | Structura |
|---|---|---|
| Partnership flip | ✅ Ships leveraged + all-equity | ✅ |
| DSCR debt sizing | ✅ Default mode | ✅ |
| §704(b) capital accounts, DRO, outside basis | ❌ **None** — a stylised pre/post-flip % split | ✅ Full ledger, rebuilt every solve iteration |
| 2025–26 tax law (OBBBA, FEOC, transferability) | ❌ **Zero mentions in any version** | ✅ The core of the product |
| Live-formula Excel for flip structures | ❌ Windows-only, and excludes flip + sale-leaseback | ✅ 2,487 live formula cells |
| Structure comparison | ❌ One model at a time | ✅ Five, side by side |

**How this differs from Ed Bodmer's models.** Bodmer gives away, free and ungated, hundreds of Excel models covering sculpting, DSRA, circularity, and a full A–Z tax equity track. Anyone evaluating Structura should ask why not just use those. The honest answer: **the math is not the differentiator — packaging, currency, reproducibility and auditability are.** Bodmer has no version control, no tests, no licence clarity, and no OBBBA/FEOC updates. Structura has 1,821 tests and a dated citation registry. That is the whole claim.

**What this is not.** Not tax, legal, accounting or investment advice. Illustrative modelling only. See [`LIMITS.md`](LIMITS.md), [`engine/tax/UNVERIFIED.md`](engine/tax/UNVERIFIED.md) and [`engine/structures/LIMITS_STRUCTURES.md`](engine/structures/LIMITS_STRUCTURES.md) — every simplification and every unsourced assumption is declared, and unsourced values surface as warnings in the tool itself rather than hiding in a footnote.

**Known gaps, stated plainly:** the MACR threshold table is sourced only for solar/CY2026 — other cells are structural placeholders that flag themselves. §45Y inflation factors raise rather than guess. The ITC bridge loan is not modelled, which makes the funding constraint conservative rather than exact.

---

## How it works

```
        inputs / reference deal
                  │
    ┌─────────────▼─────────────┐
    │  engine/  (Phase 1)       │  DSCR sculpting · sizing tests (LLCR/PLCR/
    │  the spine                │  gearing/tail) · DSRA · IDC circularity ·
    └─────────────┬─────────────┘  cash waterfall · returns
                  │
    ┌─────────────▼─────────────┐
    │  engine/tax/              │  §48E/§45Y eligibility · FEOC/MACR gate ·
    │  current-law engine       │  adders · MACRS + basis reduction ·
    └─────────────┬─────────────┘  §6418 transfer · litigation toggle
                  │
    ┌─────────────▼─────────────┐
    │  engine/structures/       │  §704(b) ledger · 5 structures ·
    │  the selector             │  brentq flip solve · ranked comparison
    └─────────────┬─────────────┘
                  │
       ┌──────────┴──────────┐
       ▼                     ▼
  Next.js UI            export/  →  .xlsx with LIVE formulas
  (Vercel)                         (openpyxl, iterate=1)
```

**Why Python, not TypeScript:** `openpyxl` is the only library that can write `iterate="1"` into a workbook. Lender-grade sculpting has genuine circularity (IDC ↔ debt size ↔ fees ↔ DSRA), so without iterative calculation the exported model opens with circular-reference warnings — which would make "lender-grade" a false claim. This was verified empirically against the emitted XML before a line of product code was written.

---

## Verification

**1,821 tests.** Beyond unit coverage, three things are worth knowing:

- **The Excel is proven, not asserted.** The test suite includes a purpose-built Excel formula evaluator (tokeniser, recursive-descent parser, Gauss-Seidel iteration — what Excel does with `iterate=1`) that runs 12 deal shapes and matches the workbook against the Python engine at **1e-7** on money. Three tests overwrite an input, recalculate, and assert the re-sized answer equals a fresh engine run.
- **Exactly one cell in the workbook is solver-derived** (the applied grace period, which is a search rather than an expression). It is amber-flagged and documented, and a test fails if a second ever appears.
- **Sources cannot exceed uses.** A property test across all five structures enforces it. This caught a real defect: §6418 transfer proceeds were being counted as construction funding, when a credit does not exist until the property is placed in service.

```bash
make test     # full suite
make gate     # confirms openpyxl writes iterate="1"
make demo     # runs the three reference deals
```

---

## Reference deals

Three calibrated deals with per-assumption provenance, each landing in a defensible band:

| Deal | Winner | Sponsor IRR | Min DSCR (vs benchmark) |
|---|---|---:|---|
| 100 MW BESS, contracted toll | Partnership flip | 14.85% | 2.09x vs 1.15–1.20x floor |
| 150 MWac solar, safe-harboured | T-flip | 11.72% | 1.45x vs 1.30x floor |
| 48 MW data-centre powered shell | Partnership flip | 15.10% | 1.33x vs 1.15x floor |

On the data-centre deal, direct transfer and T-flip are correctly returned **infeasible** — no §48E credit attaches to a building.

---

## Licence and attribution

MIT for the code. Market benchmarks are cited to Norton Rose Fulbright's *Cost of Capital: 2026 Outlook* (2026-01-29) and Crux monetisation data. Cost defaults draw on the **ATB 2024 v4.0.0** dataset (CC-BY 4.0, DOI [10.25984/2377191](https://doi.org/10.25984/2377191)) — note the National Renewable Energy Laboratory was renamed the **National Laboratory of the Rockies** in December 2025, so legacy `nrel.gov` links no longer resolve.

Built by [Apoorv Singh](https://github.com/singhapoorv17) — who structured $2.5B+ in project finance, tax equity and M&A before writing this down.
