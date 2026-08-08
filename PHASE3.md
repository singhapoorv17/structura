# Phase 3 — the structure selector (`engine/structures/`)

**Built:** 2026-08-06 · **Calibrated:** 2026-08-06 (see `CALIBRATION.md`) ·
**Law state inherited from `engine/tax`:** 2026-08-06 ·
**Tests:** 230 passing (full repository suite: 1,821)

Phase 3 of SPEC.md §9 delivers **§6.2 — the structure selector** and
**§6.3 — partnership tax rigor**. Together these are the product's single
sharpest differentiator.

---

## The two facts this phase is staked on

**1. The market now agonises over which structure to use.** Norton Rose
Fulbright's *Cost of Capital: 2026 Outlook* (2026-01-29) records five live
structures and reports traditional tax equity — investor retains the credits —
at **~30% of the 2024 market and less in 2025**, with *"most current deals
employ hybrid or preferred equity structures."* Jack Cargas (BofA): *"it feels
like there are now 31 different flavors."* Novogradac sees T-flips on *"pretty
much every single transaction."* No free tool helps anyone choose (SPEC §2.6,
§6.2).

**2. SAM has zero partnership tax.** A grep of SAM 2026.7.3's three finance
modules returns **zero** hits for `capital_account`, `deficit_restoration`,
`outside_basis`, `704(b)` or `suspended_loss` (SPEC §3.2). Its flip is a
stylised percentage split with an IRR-triggered date. `partnership.py` is that
gap.

---

## What was built

```
engine/structures/
├── __init__.py             public API
├── defaults.py             every market heuristic + tolerance; unsourced values are PLACEHOLDERs
├── partnership.py          §704(b) capital accounts, DRO, outside basis, §704(d), minimum gain  ← the moat
├── models.py               configs, StructureContext, ProjectEconomics, StructureResult, risk flags
├── flip.py                 partnership flip — yield-based (brentq) and fixed-date
├── tflip.py                T-flip / hybrid — flip + §6418 transfer, and the flip-point movement
├── preferred.py            preferred equity partnership — return, redemption, priority
├── transfer.py             direct transfer (§6418)
├── sale_leaseback.py       sale at FMV, rent solved to lessor yield, true-lease screen, §50(d)(4)
├── selector.py             compare_structures — the headline feature
├── README.md               what each structure is, when it wins, the capital-account model
└── LIMITS_STRUCTURES.md    every simplification, declared

tests/
├── test_structures_partnership.py   16 tests
├── test_structures_flip.py          21
├── test_structures_monetisation.py  18
└── test_structures_selector.py      18
```

Nothing outside `engine/structures/**` and `tests/test_structures_*.py` was
touched. The Phase 1 spine, `engine/tax/`, `export/`, the `Makefile`,
`pyproject.toml`, `PHASE1.md` and `PHASE2.md` are unmodified.

---

## Partnership tax: full-fidelity vs simplified

### Full fidelity

| Mechanic | Authority |
|---|---|
| §704(b) capital accounts maintained period by period | Treas. Reg. §1.704-1(b)(2)(iv) |
| Alternate test for economic effect — an allocation may not breach the DRO floor | Treas. Reg. §1.704-1(b)(2)(ii)(d) |
| **DRO cap → reallocation** pro rata to remaining capacity, allocations still summing to 100% | same |
| Minimum gain share as a **deemed DRO**, so a no-DRO investor still absorbs loss | Treas. Reg. §1.704-2(g)(1) |
| Outside basis: contributions, income, §752 liability share, distributions, losses allowed | §705 |
| §752 nonrecourse liability share, tiers 1 and 3 | Treas. Reg. §1.752-3(a) |
| Basis limitation on loss deductibility | §704(d) |
| Suspended losses carried indefinitely, freed FIFO as basis is restored | Treas. Reg. §1.704-1(d) |
| §731(a)(1) gain on a distribution exceeding basis | §731(a)(1) |
| 50% ITC basis reduction, charged to capital accounts as an item of loss and to outside basis on the credit ratio — computed by `engine.tax.depreciation`, **not reimplemented** | §50(c)(3), §50(c)(5), Treas. Reg. §1.704-1(b)(2)(iv)(j) |
| Tax items following the book allocation **actually made**, including the reallocated portion | Treas. Reg. §1.704-1(b)(1)(vii) |

The integrity invariant runs **inside** `run_partnership`, every period, for
every partner — not as an optional test hook:

```
Σ capital accounts + Σ distributions − Σ contributions + Σ ITC basis reductions
    == cumulative book income/loss allocated
```

plus: allocations sum to 100% of the item; outside basis never goes negative; a
**loss** allocation never takes a capital account below its floor.

### Simplified — declared in `LIMITS_STRUCTURES.md`

* **Minimum gain chargeback** (§1.704-2(f)) is implemented as a
  **documented simplification**, not silently omitted: minimum gain is pooled
  rather than tracked property by property; a partner's share is built from
  nonrecourse deductions only (not from distributions of nonrecourse proceeds);
  the exceptions and waivers of §1.704-2(f)(2)–(5), the ordering rules of
  §1.704-2(j) and **partner nonrecourse debt minimum gain** (§1.704-2(i)) are
  not modelled. The chargeback itself, its income limit and its carryforward
  are implemented and tested.
* **§704(c)** allocations (traditional / curative / remedial) are **not**
  implemented. Book and tax ledgers are maintained separately and a
  caller-supplied book/tax difference is honoured; no §704(c) layer is computed.
  For cash-funded property this is exact, because §1.704-1(b)(2)(iv)(g)(3) makes
  book depreciation track tax depreciation when book basis equals tax basis.
* **Qualified income offset** is not implemented. The DRO floor prevents the
  deficits an *allocation* could create; a *distribution* that creates one is
  **reported as a warning** naming the partner and the worst breach.
* **§465 at-risk** and **§469 passive activity** limits are not modelled.
* **HLBV**, capital account revaluations, and any liquidating distribution are
  out of scope.
* No **PAYGO**, no **back-leverage**, no sponsor **call option** at the flip, no
  **ITC bridge**, no **§50(a) recapture event** simulated (recapture is flagged,
  never modelled).

---

## The flip solve

**Method: Brent's method (`scipy.optimize.brentq`) on the bracket
`[0, project life]`, at a tolerance of 1e-6 years.**

`f(T) = investor_after_tax_IRR(T) − target`, where `T` is the flip point in
operating years from COD. To give Brent a continuous function, `T` may fall
**inside** a year: the pre-flip weight is `clamp(T − p, 0, 1)` and that year's
sharing ratios are the weighted blend of the pre- and post-flip sets. At integer
`T` this reduces exactly to a clean period boundary.

Each evaluation of `f` rebuilds the **entire §704(b) ledger** — capital
accounts, DRO caps, reallocations, outside basis, suspended losses, minimum
gain — and re-derives the investor's after-tax series from it. It is not a
percentage split.

Boundary behaviour, and it never extrapolates:

* `f(0) ≥ 0` — the target is met even with an immediate flip; the flip point is
  0 and the sponsor should be negotiating a higher target.
* `f(n) ≤ 0` — the target is unreachable inside the modelled life;
  `solved=False`, the flip is pinned at the end of the model, and the result is
  marked infeasible with a **blocking** risk flag.

`solve_flip_point` is deterministic — asserted. Monotonicity (a later flip is
strictly worth more to the investor) is asserted over an eight-point grid, and
`run_flip` additionally counts sign changes in the investor's series and warns
when the IRR is not unique.

Sale-leaseback rent is solved the same way: level rent is the root of
`lessor_after_tax_IRR(rent) − target` on `[0, sale price]`.

---

## Selector behaviour

* One debt sizing, one waterfall, one credit determination — shared by all five
  structures via `build_context`.
* Ranked on **sponsor after-tax IRR** descending; feasible-but-undefined-IRR
  structures next, ordered by NPV; infeasible last, alphabetically.
* Ties (within `RANKING_TOLERANCE`) break through a published chain — cost of
  capital, then earlier cash, then lower sponsor equity, then the structure key
  — and every break that fires is recorded in `WhyThisWins.tie_breaks`.
* **Credit gate:** a zero credit (MACR failure, missed BOC cliff, missed PIS
  backstop) makes every credit-dependent structure infeasible, enforced
  centrally in the selector as well as in the modules.
* `why_this_wins` returns **structured facts** — winner, margin, a `Driver` per
  metric with both values and the delta, disqualifications with reasons,
  tie-breaks, and caveats including every placeholder the winner consumed and
  any blocking risk on it. The narrator renders it and never computes.

### What the model actually says on the shipped storage case

200 MW·h contracted storage, $200m capex, 30% ITC, no bonus, MACRS 5:

| Sponsor tax position | Winner | Why |
|---|---|---|
| Can use depreciation | **Direct transfer** | Sells the one attribute it cannot use, keeps everything else, closes fast. |
| **Cannot** use depreciation | **Partnership flip** | A partnership moves the depreciation to someone who can use it; a transfer strands it. |

That reversal is not a demo script — it is asserted in
`tests/test_structures_selector.py::test_a_sponsor_with_no_tax_capacity_prefers_a_partnership_to_a_transfer`.

---

## Placeholders — market assumptions, not law

Tax-equity and lease pricing is quoted deal by deal. NRF publishes debt pricing
and DSCR; it publishes no tax-equity target yield, no sharing split and no
preferred coupon. Crux publishes market *shares*, not prices. So these ship as
labelled `PLACEHOLDER_` `Benchmark`s, surface as warnings on every result that
consumed one, and are expected to be overridden:

target tax-equity after-tax IRR (6.50%) · tax-equity investment per credit
dollar (1.15) · max derived investor share of equity (80%) · preferred return
(9.00%) · preferred term (10y) · lessor target after-tax IRR (7.00%) ·
sale-leaseback residual (20% — the Rev. Proc. 2001-28 guideline floor, which is
a floor and not a forecast).

Everything disclosed in `engine/tax/UNVERIFIED.md` — notably the **MACR
threshold table** and the **§45Y inflation factors** — flows through unchanged
and is propagated into `StructureComparison.warnings`. That propagation is
itself asserted by a test.

---

## Known integration items for the repo owner

1. **`pyproject.toml` does not list `engine.structures`.** It currently reads
   `packages = ["engine", "engine.tax", "export"]`. Tests run fine because
   `[tool.pytest.ini_options] pythonpath = ["."]` imports from source, but a
   built distribution would omit the package. Add `"engine.structures"` (or
   switch to `find`). Not changed here: `pyproject.toml` is owned by the Phase 1
   workstream.

2. **Citation identifiers are local.** Results carry ids such as
   `reg-1-704-1b2iv-capital-accounts`, `section-704d-basis-limitation`,
   `section-50a-recapture`, `rev-proc-2001-28-true-lease`,
   `section-50d4-sale-leaseback-window` and `rev-proc-2007-65-flip-guidelines`.
   None is yet registered in `engine/tax/citations.py`, which this workstream
   did not modify. Register them before the `/current-law` page (SPEC §7 M4)
   renders them, following the runbook in `engine/tax/README.md`.

---

## Calibration pass — 2026-08-06

Phase 3 shipped with verified *mechanics* and unverified *inputs*, and the
shipped demo case exposed the difference: a 163% sponsor IRR, third-party
capital of $255.3m against a $216.7m funding requirement, and a §704(b) capital
account below its floor for 25 consecutive periods. The full diagnosis, the
fix, the before/after tables and the open items are in **`CALIBRATION.md`**.
The four things that changed inside this package:

1. **A funding-constraint invariant.** `SourcesAndUses` in
   `structures/models.py` reconciles senior debt + third-party equity + sponsor
   equity to the Phase 1 total project cost, per structure. **§6418 transfer
   proceeds and sale-leaseback purchase prices are post-COD monetisation, not
   construction funding** — a credit does not exist until the property is placed
   in service — and adding them to the stack was a genuine defect in
   `flip.py`/`transfer.py`, now fixed and regression-tested. An over-sized
   commitment raises a **BLOCKING** `funding_oversubscribed` risk rather than
   silently flooring sponsor equity at zero.

2. **Headline-metric robustness.** `irr_meaningfulness` refuses a sponsor IRR
   built on a de minimis equity base, an immediate payback, an absent net
   investment, or a rate outside anything project finance produces. Such a
   structure ranks on **sponsor NPV**, behind every structure with a real rate,
   and carries the reason. `StructureComparison.headline` never leads with a
   rate the engine has just declared meaningless, and
   `table()["sponsor_after_tax_irr_display"]` is `None` in that case so a UI
   cannot print one either. `effective_cost_of_capital` is unchanged and remains
   the cross-check, displayed alongside everywhere.

3. **Capital-account breaches promoted out of the warning list.**
   `CapitalAccountBreach` carries every period, every year, the worst breach and
   its cause; it becomes a `capital_account_below_floor` risk flag (BLOCKING
   when sustained) and is collected on
   `StructureComparison.capital_account_breaches`. **No allocation logic
   changed** — the DRO-cap mechanic and the integrity assertion make an
   allocation-driven breach impossible, so every breach the engine can report is
   distribution-driven, which is the declared missing qualified income offset.

4. **A calibrated reference deal library**, `engine/reference_deals.py`:
   contracted BESS, safe-harboured solar, and a data-centre powered shell with
   no credit at all. Each carries per-assumption provenance, states the band it
   is calibrated to, and is fenced by `tests/test_reference_deals.py`.

The single most useful finding: **an ITC-eligible project cannot simultaneously
carry maximum DSCR-sized senior debt and monetise its credit.** A 30% §48E
credit is a *source*, not a return, and it displaces equity — 75% gearing plus a
30% ITC is 105% of cost before the sponsor contributes anything, which is
exactly how the demo produced a 6.5% equity base and a three-figure IRR.

---

## Verification

```
$ .venv/bin/pytest tests/test_structures_*.py tests/test_calibration.py \
      tests/test_reference_deals.py
........................................................................ [ 99%]
.                                                                        [100%]
230 passed

$ .venv/bin/pytest
........................................................................ [ 98%]
.....................                                                    [100%]
1821 passed in 10.50s
```

The five-structure comparison for the storage reference deal, funding
requirement $147,046,397, minimum DSCR 2.09x against the 1.15-1.20x NRF floor:

| # | structure | sponsor IRR | meaningful | eff. CoC | sponsor equity | total capital |
|---|---|---:|:---:|---:|---:|---:|
| 1 | partnership_flip | 14.85% | yes | 8.03% | $27.9m | $147.0m |
| 2 | t_flip | 14.01% | yes | 7.04% | $65.9m | $147.0m |
| 3 | direct_transfer | 11.36% | yes | 6.84% | $80.9m | $147.0m |
| 4 | preferred_equity | 3.31% | yes | 13.69% | $32.4m | $147.0m |
| 5 | sale_leaseback | 41.32% | **no** | 9.80% | $7.0m | $147.0m |

---

## Not advice

Illustrative modelling tool. **Not tax, legal, accounting or investment advice**
(SPEC §4.4). Public sources only; no real transaction's assumptions and no
employer data appear anywhere in this package (SPEC §4.5).
