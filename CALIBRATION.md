# CALIBRATION — why the demo produced impossible numbers, and what changed

**Written 2026-08-06. Phases 1–4 complete, 1,664 tests passing at the time this
work started; 1,821 passing at the end.**

This file is the diagnosis, the fix and the evidence. It exists because
Structura reached a state where **every mechanic was verified and the headline
was still not believable** — which is the worst possible failure mode for a tool
whose entire value proposition is credibility with practitioners (SPEC §4.3,
§11: *"credibility risk from overclaiming — the single largest risk"*).

---

## 0. The observed failure

A 100 MW / $200m storage deal — $5m opex, 400,000 MWh at $70/MWh, 25-year
contract and life, `FlipConfig(target_after_tax_irr=0.07,
investor_commitment=$40m)`, `PreferredConfig(commitment=$40m)`, 15-year
sale-leaseback, `bonus_rate=0` — through `compare_structures`:

| # | structure | sponsor IRR | eff. cost of capital | 3rd-party capital |
|---|---|---:|---:|---:|
| 1 | t_flip | **163.66%** | 6.11% | **$255.3m** |
| 2 | partnership_flip | **74.66%** | 5.84% | $202.5m |
| 3 | direct_transfer | **62.97%** | 6.30% | **$215.3m** |
| 4 | sale_leaseback | 48.58% | 9.80% | $200.0m |
| 5 | preferred_equity | 22.59% | 11.82% | $202.5m |

`sponsor_equity_required = $14.17m` on $200m of capex, plus a §704(b) capital
account below its floor for **25 consecutive periods** (worst breach
−$12,140,148).

Three things were wrong and they have **three different causes**. Separating
them is the point of §1.

---

## 1. Diagnosis — instrumented sources and uses

The Phase 1 funding solve produced, for that deal:

| use | amount |
|---|---:|
| capex | $200,000,000 |
| interest during construction | $7,352,544 |
| upfront fee | $2,031,532 |
| commitment fee | $579,568 |
| DSRA (funded at COD) | $6,733,100 |
| **total funding requirement** | **$216,696,743** |

against senior debt of $162,522,557 (75.0% gearing, **gearing-bound**, achieved
minimum DSCR 1.708x) and equity at COD of $54,174,186. Modelled ITC:
$60,000,000. Year-1 EBITDA: $23,000,000.

### 1.1 Sources exceeded uses — **an engine defect, not bad inputs**

`third_party_capital_raised` and `total_capital_raised` were assembled by hand
in each structure module, and two of them added **§6418 transfer net proceeds**
to the construction stack:

* `flip.py`: `debt_at_cod + commitment + transfer_net_proceeds`
* `transfer.py`: `debt_at_cod + transfer.net_proceeds`

The T-flip therefore reported $255.3m and the direct transfer $215.3m, while the
sponsor's equity contribution was **not reduced by a cent**. Totals came out at
$269.5m against a $216.7m requirement — an excess of $52.8m, exactly the net
transfer proceeds.

**This is a genuine defect, not a demo-input problem.** A §6418 credit does not
exist until the property is placed in service, so its sale settles *after* COD
and cannot have funded construction. It is a **reimbursement of committed
capital**, and it is distributed, not drawn. Funding construction against an
expected credit requires an **ITC bridge loan** (SPEC §2.7: 98% advance at
SOFR+150 if covered, 75% at SOFR+225 if not), which is debt and which Structura
does not model. The same reasoning applies to the sale-leaseback purchase price,
which repays the senior facility and returns construction equity on a completed
asset.

Nothing about the *cashflows* was wrong — the sponsor really does receive those
proceeds in the settlement year, and every IRR and NPV was computed on a correct
series. What was wrong was a **reported metric that had never been constrained**.
Fixed in §2.1; regression-tested by
`tests/test_calibration.py::test_the_transfer_proceeds_used_to_be_counted_as_construction_capital`.

### 1.2 Sponsor equity was de minimis — **bad demo inputs, with a structural cause**

Sponsor equity of $14.17m came out as `equity_at_cod − tax_equity_commitment`
= $54.17m − $40m. That is only 6.5% of the funding requirement, and an IRR
computed on it is a statement about the denominator.

The structural cause is worth stating plainly because it is the single most
useful thing this exercise produced:

> **An ITC-eligible project cannot simultaneously carry maximum DSCR-sized
> senior debt and monetise its credit. A 30% §48E credit is not a return; it is
> a *source*, and it displaces equity.**

Stack the customary 75% gearing cap on top of a 30% ITC and the arithmetic gives
105% of cost before the sponsor writes a cheque. The demo did exactly that, and
the residual sponsor equity was whatever happened to be left over. In the real
market the DSCR headroom is taken as **back-leverage at the sponsor holdco**,
which `LIMITS_STRUCTURES.md` already declares unmodelled — so a Structura
reference deal has to set the senior gearing cap so the stack closes at 100%.
That is what `engine/reference_deals.py` does, and it is asserted by
`tests/test_reference_deals.py::test_an_itc_deal_is_geared_below_the_ordinary_cap_and_says_why`.

Revenue was a second, independent input problem: **$28m of revenue on $200m of
capex (14%) is not a storage deal.** 400,000 MWh/year from a 100 MW battery is
4,000 full-load hours — roughly 2.7 cycles a day — and a contracted BESS is paid
a capacity toll in $/kW-month, not a $/MWh energy price.

### 1.3 The 25-period capital-account breach — **a config artefact of the declared missing QIO**

Not an allocation bug. The DRO-cap mechanic in
`partnership._allocate_loss_with_dro_caps` caps every *allocation* at
`−(DRO cap + minimum gain share)`, and
`assert_capital_account_integrity` raises if an allocation ever gets past the
floor — it never fired. Every breach the engine can produce is therefore
**distribution-driven**, and that is asserted directly
(`tests/test_calibration.py::test_an_allocation_can_never_cause_a_breach`).

The specific trigger in the demo was the T-flip. `TFlipConfig` defaults
`proceeds_to_partnership=True`, so $52.8m of transfer proceeds were paid into
the partnership and distributed on the pre-flip cash ratio — 99% to the
tax-equity partner. **§6418(b) excludes transfer proceeds from gross income**, so
there is no matching book allocation to offset the distribution: the capital
account falls by the full amount and stays below its floor for the rest of the
deal. Treas. Reg. §1.704-1(b)(2)(ii)(d) would cure it with a **qualified income
offset**, which `LIMITS_STRUCTURES.md` §1.5 already declares unimplemented.

So: category **(a) config artefact** compounded by **(b) the declared missing
QIO**, and *not* (c) an allocation bug. What was genuinely wrong was the
**reporting** — a single sentence at the end of a warning list for a 25-period,
$12m structural deficit. Fixed in §2.4.

---

## 2. What changed

Scope was held to `engine/structures/**`, the new `engine/reference_deals.py`,
the two new test files, and the two selector tests noted in §2.5. **No file in
`engine/tax/**`, `export/**` or the Phase 1 core was touched** — no defect was
found in any of them.

### 2.1 A funding-constraint invariant — `SourcesAndUses`

New type in `engine/structures/models.py`, built by every structure:

```
uses   = capex + IDC + fees + funded reserves          (= Phase 1 total project cost)
sources = senior debt
        + third-party equity contributed at close      (tax equity / preferred)
        + credit proceeds applied at COD               (always 0 today — see below)
        + sponsor equity
post-COD monetisation                                   (reported, never a source)
```

* `balances` — sources equal uses within
  `max($1, 1e-6 × uses)`.
* `oversubscribed` — third-party capital alone exceeds the requirement. This is
  the commercially real failure (an over-sized commitment) and it now raises a
  **BLOCKING** `funding_oversubscribed` risk instead of silently flooring
  sponsor equity at zero.
* `post_cod_monetisation` + `post_cod_monetisation_note` — §6418 proceeds and
  sale-leaseback prices, with the reason they are excluded stated in the object
  rather than in a comment.
* `credit_proceeds_at_cod` exists and is always zero. It is stated explicitly so
  that adding an ITC bridge later has somewhere to land.

`third_party_capital_raised` now means third-party **construction** capital;
`total_capital_raised` equals the construction sources. `StructureComparison`
gained `sources_and_uses_table()` and a `funding_failures` list.

**Property test across all five structures**
(`tests/test_calibration.py`), run over seven configurations — the original
demo, a $1m commitment, a $300m over-subscribed commitment, 80% and 30% gearing
variants, and all three reference deals:

* sources ≤ uses always, or `oversubscribed` with a BLOCKING risk;
* uses reconcile to the Phase 1 funding solve and to their own components;
* `credit_proceeds_at_cod == 0` in every structure;
* post-COD monetisation is excluded from every source total, carries a note, and
  would have broken the identity had it been included.

### 2.2 A reference deal library — `engine/reference_deals.py`

Three calibrated deals, each with per-assumption provenance
(`Assumption(name, value, unit, source, verified_on, is_placeholder, note)`) and
a stated `ExpectedOutcome` band that `tests/test_reference_deals.py` asserts:

| deal | what it demonstrates |
|---|---|
| `storage_bess_contracted` | 100 MW / 400 MWh BESS on a 15-year toll, PIS 2027. Storage keeps full §48E to 2033 (SPEC §2.1), so it is forward pipeline — SPEC §6.4 says lead with it. |
| `solar_safe_harboured` | 150 MWac PV that began construction 2026-03-01, inside the 2026-07-04 cliff, PIS 2028 within the four-year continuity window. |
| `data_center_powered_shell` | 48 MW shell on a 15-year hyperscaler lease at NRF's 1.15x DSCR and SOFR+337.5bps. **No §48E attaches to a building**, so the credit gate correctly disqualifies the transfer and the T-flip. |

Provenance discipline is unchanged from the rest of the engine: **the DSCR
floors and debt spreads trace to NRF 2026 via `engine.defaults`**; capex, offtake
pricing, opex and every tax-equity / preferred / lease price are
`is_placeholder=True`, are listed by `placeholder_assumptions()`, and surface as
warnings. SPEC §5.1 is explicit that no free source of PPA prices exists, so a
deal claiming a sourced revenue line would be a lie — and a test asserts every
deal carries at least one placeholder.

Two calibration decisions are worth surfacing because they are results, not
tuning:

1. **Fixed-date flips, not yield-based.** A yield-based flip on a 30% ITC deal
   solves to well inside year one — the credit alone repays the investor — and
   `run_flip` correctly raises a BLOCKING `flip_inside_recapture_period` risk
   under §50(a)(1). The market answer to that is a date, not a yield, so the
   reference deals flip on a fixed date in operating year 6. SPEC §6.2 lists
   both forms.
2. **T-flip proceeds settle at the holdco** (`proceeds_to_partnership=False`),
   and the T-flip's tax-equity investor takes **no share of the credit** — so
   under §50(c)(5) it bears no share of the §50(c)(3) basis reduction, and it
   writes a much smaller cheque because it is buying depreciation and cash only.
   Both follow from §1.3.

### 2.3 Headline-metric robustness in the selector

`irr_meaningfulness()` in `engine/structures/models.py` returns
`(is_meaningful, reason)` against four tests, in the order a reviewer applies
them:

| test | threshold | constant |
|---|---|---|
| no rate exists (no net sponsor investment) | — | — |
| de minimis equity base | sponsor equity < 10% of the funding requirement | `DE_MINIMIS_SPONSOR_EQUITY_SHARE` |
| immediate payback | ≤ 1.0 years | `DE_MINIMIS_SPONSOR_PAYBACK_YEARS` |
| implausible for project finance | > 40% | `IMPLAUSIBLE_SPONSOR_IRR` |

These are **Structura's own reporting guards, not market data**, and they live in
`engine/structures/defaults.py` alongside every other constant so the rule is
auditable in one place. The 8–15% band they are calibrated against is stated in
the constant's own docstring.

Consequences:

* `StructureResult` gained `sponsor_irr_is_meaningful` and
  `sponsor_irr_not_meaningful_reason`.
* `_sort_key` grew a tier: feasible-with-meaningful-IRR, then
  feasible-ranked-on-NPV, then infeasible. This generalises the pre-existing
  "IRR undefined → rank on NPV" rule rather than replacing it.
* `WhyThisWins.primary_metric` switches to `sponsor_npv` when the winner's rate
  is not meaningful, and the **leading caveat** states the reason and the
  effective cost of capital.
* `StructureComparison.headline` is a single line that never quotes a
  meaningless rate as a return.
* `table()` gained `sponsor_after_tax_irr_display`, which is `None` when the
  rate is not meaningful — so a UI that prints that column **cannot** lead with
  an absurd number — plus the flag, the reason, `post_cod_monetisation`,
  `funding_requirement` and `sources_balance`.
* `effective_cost_of_capital` is unchanged and remains the cross-check: it is in
  `table()`, in `WhyThisWins.drivers`, and in the headline string. A test
  asserts all three for every configuration.

### 2.4 The capital-account breach, promoted out of the warning list

New `CapitalAccountBreach` record on `PartnershipResult`, carrying the partner,
**every period and year**, the worst breach and the period it occurred in, and
the cause. It becomes a structured `RiskFlag` on the structure
(`capital_account_below_floor`) — **CAUTION** for a single period, **BLOCKING**
for a sustained deficit — and is collected on
`StructureComparison.capital_account_breaches` keyed by structure. The original
warning string is retained so nothing disappears from where a reader already
looks.

**No allocation logic was changed**, because none was wrong. The reference deals
carry a tax-equity deficit restoration obligation large enough to keep every
capital account above its floor in every period, and
`test_no_reference_deal_carries_a_capital_account_breach` asserts zero breaches
across all three.

### 2.5 Two existing selector tests were updated — called out deliberately

`tests/test_structures_selector.py` built its fixture from the same
mis-calibrated demo — 75% gearing alongside a 30% ITC — so its ranking
assertions were asserting the artefact. Its helpers now derive from
`reference_deal("storage_bess_contracted")`, and
`test_the_ranking_is_sorted_by_sponsor_after_tax_irr_descending` now filters to
structures whose IRR is meaningful and additionally asserts that every
NPV-ranked structure sits behind every IRR-ranked one. **This is an intentional
change to a test that encoded the behaviour this work exists to correct**, and
it is the only such change.

---

## 3. Before and after

### 3.1 The original demo inputs, unchanged, through the fixed engine

Total funding requirement **$216,696,743**.

| # | structure | IRR | meaningful | eff. CoC | sponsor NPV | sponsor equity | 3rd-party capital | **total capital** | post-COD |
|---|---|---:|:---:|---:|---:|---:|---:|---:|---:|
| 1 | direct_transfer | 62.97% | **no** | 6.30% | $96.7m | $54.2m | $162.5m | **$216.7m** | $52.8m |
| 2 | t_flip | 163.66% | **no** | 6.11% | $95.4m | $14.2m | $202.5m | **$216.7m** | $52.8m |
| 3 | partnership_flip | 74.66% | **no** | 5.84% | $77.8m | $14.2m | $202.5m | **$216.7m** | — |
| 4 | sale_leaseback | 48.58% | **no** | 9.80% | $75.3m | $16.7m | $162.5m | **$216.7m** | $200.0m |
| 5 | preferred_equity | 22.59% | **no** | 11.82% | $44.2m | $14.2m | $202.5m | **$216.7m** | — |

Headline: *"Direct transfer (§6418): sponsor NPV $96,677,580 at 10.0%, effective
cost of capital 6.30%, sponsor equity $54,174,186. **Sponsor IRR is NOT
MEANINGFUL here** — immediate payback: the sponsor recovers its entire net
investment in 0.81 years…"*

Every total now equals the funding requirement exactly (was $269.5m for the
t_flip and the transfer). Every rate is refused as a headline, with a reason.
The 25-period T-flip capital-account breach still reproduces on these inputs —
correctly, because it is a real consequence of paying §6418 proceeds into the
partnership — and now arrives as a structured BLOCKING record.

### 3.2 Reference deal — `storage_bess_contracted`

100 MW / 400 MWh, capex $140m, funding requirement **$147,046,397**, senior debt
$66.2m (45.0%), **achieved minimum DSCR 2.09x against the 1.15–1.20x NRF floor**,
ITC $42.0m.

| # | structure | sponsor IRR | meaningful | eff. CoC | sponsor NPV | sponsor equity | 3rd-party | **total** | post-COD |
|---|---|---:|:---:|---:|---:|---:|---:|---:|---:|
| 1 | partnership_flip | **14.85%** | yes | 8.03% | $12.2m | $27.9m | $119.2m | **$147.0m** | — |
| 2 | t_flip | **14.01%** | yes | 7.04% | $12.2m | $65.9m | $81.2m | **$147.0m** | $37.0m |
| 3 | direct_transfer | **11.36%** | yes | 6.84% | $4.8m | $80.9m | $66.2m | **$147.0m** | $37.0m |
| 4 | preferred_equity | 3.31% | yes | 13.69% | −$15.3m | $32.4m | $114.7m | **$147.0m** | — |
| 5 | sale_leaseback | 41.32% | **no** | 9.80% | $19.4m | $7.0m | $66.2m | **$147.0m** | $140.0m |

Zero capital-account breaches. Zero funding failures.

The two structures that do *not* land in the 8–15% band are the informative
ones. Preferred equity at 3.31% is expensive here because the investor takes the
whole credit *and* a 9% coupon *and* full redemption — Crux puts preferred at
only 15% of ITC gross value, and this is why. The sale-leaseback is effectively
100% financing, so its 41.32% is computed over $7.0m of residual equity and is
correctly refused as a headline.

### 3.3 The other two reference deals

`solar_safe_harboured` — funding requirement $191.0m, debt 55.0%, minimum DSCR
1.45x against a 1.25–1.30x floor, ITC $54.0m:
t_flip **11.72%** (winner), partnership_flip **10.10%**, direct_transfer
**8.24%**, preferred_equity 0.74%, sale_leaseback 18.90% (not meaningful). All
five totals $191.0m. Zero breaches.

`data_center_powered_shell` — funding requirement $537.0m, debt 75.0%, minimum
DSCR 1.33x against the 1.15x floor, **no credit**:
partnership_flip **15.10%** (winner), preferred_equity **11.94%**,
sale_leaseback **9.86%**; direct_transfer and t_flip **infeasible**, each naming
the rule. All three feasible totals $537.0m. Zero breaches.

---

## 4. What was *not* changed, and why

* **No allocation, capital-account, outside-basis or minimum-gain logic.** The
  §704(b) engine was right. The breach was distribution-driven and declared.
* **No `engine/tax/**`, no `export/**`, no Phase 1 core.** No defect was found
  in any of them. The funding solve, the sculpt and the waterfall all reconcile.
* **The de minimis and implausibility thresholds are not market data.** They are
  reporting guards, are labelled as such in `defaults.py`, and are adjustable in
  one place. They are not used to change any computed number — only to decide
  what may be *led with*.
* **No input was tuned to hide a defect.** §1 separates the defect (§1.1) from
  the inputs (§1.2) from the declared simplification (§1.3), and the defect was
  fixed before any input was touched. The before/after in §3.1 runs the original
  inputs through the fixed engine precisely so the two effects can be seen
  apart.

---

## 5. Test results

`.venv/bin/pytest -q` — **1,821 passed** (1,664 before this work; +157).

New: `tests/test_calibration.py` (87 tests — the funding invariant as a property
across all five structures over seven configurations, the meaningfulness guards,
and the capital-account breach reporting) and `tests/test_reference_deals.py`
(70 tests — bands, DSCR floors, sources/uses, provenance, the credit gate).

---

## 6. Open items

1. **No ITC bridge loan.** SPEC §2.7 carries the advance rates (98% at SOFR+150
   covered; 75% at SOFR+225 uncovered). Until it is modelled,
   `credit_proceeds_at_cod` stays zero and transfer proceeds arrive undiscounted
   in the settlement year. This is the one place where the funding constraint is
   *conservative* rather than exact.
2. **No qualified income offset.** Declared in `LIMITS_STRUCTURES.md` §1.5. The
   reference deals avoid triggering the deficit with a capped DRO; a deal that
   distributes more aggressively will still report a breach, and should.
3. **No holdco back-leverage.** It is what a real sponsor uses to take the DSCR
   headroom the ITC gearing cap leaves behind. Its absence is why the reference
   deals come out gearing-bound with coverage well above the market floor.
4. **Capex and offtake pricing are placeholders.** The ATB parquet (SPEC §5.1,
   verified live) is the intended anchor for capex and capacity factors; PPA
   pricing has no free source at all.
