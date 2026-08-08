# Phase 1 — Engine spine

Scope: SPEC.md §6.1 only. Debt sizing, DSCR sculpting, coverage ratios,
reserves, the construction-funding circularity and the cash waterfall.
**No UI, no Excel export, no tax structures, no partnership mechanics.**

Reproduce with `make test` (or `.venv/bin/pytest -q`). **1,082 tests pass.**

---

## What is done

**`engine/models.py`** — frozen dataclasses for every input and output:
`ProjectInputs`, `DebtTerms`, `CashflowResult`, `DebtResult`, `ConstraintTest`,
`SizingResult`, `ConstructionResult`, `WaterfallResult`, `ReturnsResult`.
Validation at construction; derived properties (min DSCR, weighted average
life, merchant share) rather than duplicated fields.

**`engine/defaults.py`** — the SPEC §2.7 market benchmarks as a typed library.
Every entry is a `Benchmark` with `value`, published `low`/`high`, `unit`,
`source` and `verified_on`. Covers minimum DSCR by technology and revenue-risk
profile (solar 1.25–1.30x, wind 1.35–1.40x, storage 1.15–1.20x, data centre
1.15x / 1.05x hyperscaler; merchant P50 solar 1.75x, wind 1.80x, storage 2.0x),
construction and permanent spreads, the merchant-exposure adders, ITC bridge
advance rates, gearing, DSRA, tail, fees. `benchmark_registry()` produces the
flat map the Phase 5 `/current-law` page will render. Every numeric tolerance
in the engine also lives here — there are no magic numbers in any other module.

**`engine/cashflow.py`** — revenue (contracted + merchant, with escalation,
degradation and contract expiry) → opex → EBITDA → cash tax → CFADS. Annual or
semi-annual via `periods_per_year`. NOL carryforward. `assert_cfads_identity`
checks revenue − opex − tax = CFADS.

**`engine/debt.py`** — the core.
- **Sculpting** to a constant or time-varying DSCR target: `DS_t = C_t/d_t`,
  `D = PV(DS)` at the debt rate. Closed form; no iteration.
- **Level payment** and **fixed principal** alternatives, both closed form.
- **Grace periods**, interest-only, with the quantum capped at the
  interest-only coverage limit and the post-grace profile scaled pro rata.
- **Automatic interest-only holiday** where a pure PV sculpt would require
  negative amortisation (see *Findings* below).
- **DSCR, LLCR, PLCR** — headline and full series.
- **DSRA sizing** — months-based, forward-looking (market standard) and
  backward-looking, correct across period lengths.
- **`size_facility()`** runs all six credit tests — DSCR, gearing, tenor, tail,
  LLCR, PLCR — and reports **which one binds**, with the slack on the others.

**`engine/circularity.py`** — the IDC ↔ debt size ↔ fees ↔ DSRA fixed point,
solved with `scipy.optimize.brentq` on an explicit two-level schedule
(documented in the module docstring and `engine/README.md`). Deterministic;
tolerance exposed as a parameter; a third fixed-point loop handles the
CFADS ↔ interest ↔ cash-tax circularity under `TaxTreatment.FULL` and raises
rather than returning an unconverged answer.

**`engine/waterfall.py`** — CFADS → interest → scheduled principal → DSRA →
MRA → cash sweep → lock-up → subordinated → distributions. Sweeps prepay in
inverse order of maturity. **Cash conservation is asserted every period inside
`run_waterfall` itself**, not only in tests.

**`engine/metrics.py`** — periodic IRR, XIRR (`pyxirr`), NPV, payback,
effective all-in cost of debt including fees, after-tax cost of debt, WACC,
and pre-/post-tax equity IRR.

**`engine/README.md`** — module map, the sculpting formulas written out with
the proof that the PV identity forces exact amortisation, why LLCR uses the
debt rate and PLCR the project-life horizon, the circularity iteration
schedule, and the waterfall priority.

### Test suite

- **Golden cases**, hand-computed in 40-digit `Decimal` arithmetic *outside*
  the engine and asserted to the cent:
  - flat CFADS sculpt → `DS = CFADS/DSCR` every period,
    `D = 8,000,000 × 7.360087051414697 = 58,880,696.41`
  - level payment → `56,616,054.24`, cross-checked against the mortgage
    payment formula
  - fixed principal → `50,000,000.00` exactly
  - time-varying target (1.20x → 1.50x) → `56,087,853.32`
  - LLCR / PLCR on a three-period model with every PV written out
    (LLCR 2.0000, PLCR 3.7595307917888563)
  - circularity: interest recomputed month by month from the published draw
    schedule reproduces the reported IDC to the cent, and
    `TPC = capex + fee + commitment fee + IDC + DSRA` reconciles
- **Property tests** across 6 CFADS shapes × 4 rates × 4 targets × 3 styles ×
  3 grace periods (~870 combinations): debt service never exceeds
  `CFADS/target`; DSCR never dips below target; the facility amortises to
  exactly zero; principal sums to the debt drawn; the waterfall conserves cash;
  the gearing cap is never breached; exactly one constraint binds.
- **Binding-constraint tests** — a constructed scenario for each of DSCR,
  gearing, tail, LLCR and PLCR binding, asserting the reporter names the right
  one, plus the DSCR-preferring tie-break.
- **Determinism** — two runs produce bit-identical debt size, IDC and TPC.

### SPEC §9 Phase 1 gate

`make gate` verifies the blocking finding: `openpyxl` writes
`iterate="1" iterateCount="100" iterateDelta="0.0001" fullCalcOnLoad="1"` into
`xl/workbook.xml`. **Confirmed passing** in this environment (openpyxl 3.1.5,
Python 3.14). The "lender-grade Excel" claim is not at risk.

---

## Findings that changed the design

**1. A pure PV sculpt can imply negative amortisation.** Against a steeply
ramping CFADS profile at a high rate (e.g. 3% p.a. growth at a 9.5% coupon),
`DS_1 < r·D` — principal goes backwards. The arithmetic is fine with it; no term
facility is. The engine now lengthens the interest-only holiday one period at a
time until every period amortises non-negatively (`effective_grace_periods`),
capping the quantum at the interest-only coverage limit. This costs debt
capacity, which is the correct economic answer. Found by the property sweep, not
by inspection.

**2. Level payment does not always beat fixed principal.** Against a *declining*
CFADS profile a declining service schedule tracks the cash better, so fixed
principal raises more debt. Only sculpting's dominance over both is universal.
Both directions are now asserted so the "obvious" ordering is not reintroduced.

---

## Deliberately deferred

| Deferred to | Item |
|---|---|
| Phase 2 (`engine/tax/`) | §48E/§45Y eligibility and phase-down, FEOC / MACR pass-fail, domestic content adder, begin-construction fork and the *Oregon Environmental Council* vacatur toggle, §70512(h). MACRS 5/15, SL and bonus depreciation. |
| Phase 2 | §704(b) capital accounts, DRO and DRO caps, outside basis, suspended losses, minimum gain chargeback, 50% ITC basis reduction. |
| Phase 3 | The five-structure selector: partnership flip, T-flip, preferred equity, direct transfer, sale-leaseback. Back-leverage sizing (the waterfall exposes the `subordinated_service` hook but does not size a tranche). |
| Phase 3 | Multiple senior tranches and refinancing. Phase 1 sizes a single senior facility. |
| Phase 4 | Excel export with live formulas, and the assertion that the Python and Excel solutions agree to a documented tolerance. |
| Phase 5 | ATB data ingestion, P50/P90/P99 scenario runner, merchant-share and rate-shock grids. The inputs exist (`production_p90`, `production_p99`, `ProductionCase`); the runner does not. |
| Phase 6 | The narrator. |

---

## Simplifications made (these feed `LIMITS.md`)

**Cashflow**
1. **No seasonality.** With `periods_per_year = 2` an annual quantity splits
   into equal halves. Real solar and BESS revenue is strongly seasonal; a
   seasonal shape file is a Phase 5 input.
2. **Escalation and degradation compound on an operating-year basis**, applied
   uniformly to every sub-period of a year.
3. **Contracted volume is a share of production**, not a fixed MWh block. A
   fixed-volume PPA with a shortfall/liquidated-damages obligation is not
   modelled.
4. **Project-level tax is federal only, straight-line depreciation, no state
   tax.** MACRS lives in `engine/tax/` in Phase 2 because it is tax-law
   dependent and needs dated citations. The default `TaxTreatment.NONE` treats
   CFADS as pre-tax, which is the convention in most US renewable sizing work
   because tax attributes sit in a structure modelled *above* the project.
5. **No working capital, no capex reserve draw-down, no revenue seasonality
   effect on DSRA sizing.**

**Debt**
6. **Interest convention is nominal-annual-divided-by-periods** (money-market
   style), matching how credit agreements quote a margin over a periodic index.
   Exact day counts (30/360, act/360) are a Phase 4 Excel-parity concern.
7. **Grace period is interest-*paid*, not interest-capitalised.** Capitalising
   PIK interest during operations is not modelled.
8. **A gearing-, LLCR- or tail-constrained facility is sized by scaling the
   whole service profile down pro rata**, so DSCR lands uniformly above target.
   An alternative market practice is to shorten the tenor instead; the engine
   does not choose between them automatically.
9. **DSRA is assumed linear in the facility size** inside the circularity
   solver. This is exact, not an approximation — the service profile is
   homogeneous of degree one in debt — but it is an assumption worth naming.
10. **One senior tranche.** No mezzanine, no tranching by tenor or currency.

**Construction**
11. **Draws land at the start of the month**, interest accrues on the post-draw
    balance. Conservative by roughly half a month of IDC versus a mid-month
    convention.
12. **Debt and equity fund capex on the same S-curve, pro rata.** Real deals
    often run equity-first or use an equity bridge; `ConstructionResult`
    already publishes the monthly equity draw series for Phase 2.
13. **The whole equity contribution is treated as a single outflow at COD** for
    the equity IRR. Equity drawn across construction gives a slightly lower
    true IRR.
14. **The upfront fee is drawn in full at first utilisation** and financed by
    the facility. Ticking/structuring fees split across a syndication timetable
    are not modelled.

**Waterfall**
15. **A distribution lock-up is modelled as a 100% sweep in that period.** A
    real agreement traps the cash in a blocked account and releases it after a
    cure period; the engine's treatment is more conservative and simpler.
16. **The MRA is exogenous** — the caller supplies deposits and releases from a
    maintenance plan. There is no O&M reserve model.
17. **No default/acceleration mechanics.** A shortfall beyond the DSRA is
    reported (`debt_service_shortfall`, `in_default`) and the model keeps
    running; it does not accelerate, restructure or enforce.
18. **Cash sweeps prepay in inverse order of maturity** with no make-whole or
    prepayment penalty.

**General**
19. **Nominal terms throughout.** No inflation index, no real/nominal toggle.
20. **Deterministic single-scenario.** No Monte Carlo, no probability-weighted
    outputs.
21. **SOFR ships as a labelled placeholder**, not a live rate. Structura has no
    rates feed and does not pretend to.

---

## Honest positioning (SPEC.md §4.3)

Nothing in this phase is mathematically novel. Debt sculpting, LLCR/PLCR and
the IDC circularity are decades-old practice, and Edward Bodmer gives away
spreadsheet implementations of all of it for free. What Phase 1 contributes is
**packaging, reproducibility and auditability**: a tested, typed, versioned,
MIT-licensed implementation where every default carries a citation and a date,
every golden case has a hand-computed answer, and cash conservation is asserted
rather than assumed. That claim is defensible. A claim of novel math would not
be.
