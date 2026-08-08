# `engine/structures` — the five live 2026 structures, and the selector

The structure selector and the partnership-tax layer underneath it. Pure
Python. Imports `engine` (the sculpting spine) and `engine.tax` (the
current-law engine); duplicates neither.

---

## Market context

Norton Rose Fulbright's *Cost of Capital: 2026 Outlook* (2026-01-29) records
five live structures and reports that traditional tax equity — where the
investor retains the credits — was **~30% of the market in 2024 and a smaller
percentage in 2025**, with *"most current deals employ hybrid or preferred
equity structures."* Novogradac reports T-flips on **"pretty much every single
transaction."** Crux puts 2025 ITC gross value at **partnerships 57% / direct
transfer 28% / preferred equity 15%**, and PTCs at **more than 90% direct
transfer**.

This package models all five against the same project economics, and
implements the partnership-tax layer that comparison depends on. The
mathematics is standard; what this implementation adds is that it is versioned,
tested, current with OBBBA and FEOC, and carries a written limits file — see
`LIMITS_STRUCTURES.md`.

---

## Module map

| Module | Responsibility |
|---|---|
| `defaults.py` | Every market heuristic and tolerance. Anything unsourced is a `PLACEHOLDER_` `Benchmark` carrying its own note. **No magic numbers elsewhere.** |
| `partnership.py` | §704(b) capital accounts, DRO caps and reallocation, outside basis, §704(d) suspended losses, minimum gain chargeback, §50(c)(3). |
| `models.py` | Configs, `StructureContext`, `ProjectEconomics`, `StructureResult`, risk flags, cash-timing and cost-of-capital helpers. |
| `flip.py` | Partnership flip: yield-based (solved with `scipy.optimize.brentq`) and fixed-date. |
| `tflip.py` | T-flip / hybrid: a flip with a §6418 transfer bolted on, plus the flip-point movement it causes. |
| `preferred.py` | Preferred equity partnership: priority return, redemption, then common. |
| `transfer.py` | Direct transfer under §6418. |
| `sale_leaseback.py` | Sale at FMV, rent solved to the lessor's yield, true-lease screen, §50(d)(4) window. |
| `selector.py` | `compare_structures` — the headline feature. |

Dependency direction is strictly one-way:

```
defaults -> partnership -> models -> {flip, preferred, transfer, sale_leaseback}
                                        -> tflip -> selector
```

---

## The capital-account model

A partner in a project partnership has **three** running balances. Practitioners
conflate them at their peril, and a model that keeps only one is not modelling a
partnership.

**1. The §704(b) capital account.** A *book* balance under Treas. Reg.
§1.704-1(b)(2)(iv). Up by contributions and allocated book income; down by
distributions, allocated book loss, and the §1.704-1(b)(2)(iv)(j) adjustment for
the investment-credit basis reduction. It is the yardstick for **economic
effect**: whether the IRS will respect an allocation at all.

**2. Outside basis.** A *tax* balance under §705: contributions, plus the
distributive share of taxable income, plus the §752 share of partnership
liabilities, less distributions, less losses **allowed**. It never goes below
zero, and it is the ceiling on loss deductibility under §704(d).

**3. Partnership minimum gain.** Treas. Reg. §1.704-2(d): the gain the
partnership would realise if it disposed of property subject to a nonrecourse
liability in satisfaction of that liability. A partner's share of it is a
**deemed** deficit restoration obligation under §1.704-2(g)(1) — which is why a
tax-equity investor with no DRO at all can still absorb losses that drive its
capital account deeply negative.

### The order of operations in a period

Chosen to match the order a partnership return is actually prepared:

1. **Contributions** — capital account and outside basis up.
2. **Minimum gain** recomputed. A net *decrease* triggers a **chargeback** of
   gross income (§1.704-2(f)), allocated before anything else, limited to the
   year's income with the excess carried forward.
3. **Credits and the §50(c)(3) basis reduction**, allocated on the credit ratio
   and charged to capital accounts as an item of loss.
4. **Residual book income or loss** on the income/loss ratio — with the DRO cap
   applied to loss.
5. **Distributions** — capital account and outside basis down; anything above
   basis is §731(a)(1) gain.
6. **§752 liability share** re-struck; the change moves outside basis.
7. **§704(d)**: losses allowed only to the extent of basis, the rest suspended.
   Previously suspended losses are freed first, FIFO.

### The DRO cap → reallocation mechanic

Each partner has a floor:

```
floor_i = -(DRO_i + minimum_gain_share_i)
```

A loss allocation that would breach the floor is **capped at exactly the
floor**, and the excess **reallocates to the partners that still have capacity,
pro rata to that remaining capacity**. Each pass of the loop removes at least
one partner from the capacity pool, so it terminates. If capacity runs out
entirely, the residual lands on the partner flagged
`bears_residual_allocations` and a warning is raised — that is a modelling
failure signal, not a tax result.

**This is the mechanic that makes a flip a flip.** When the investor's capital
account hits its floor, its loss allocations stop, its tax benefit stops, and
the flip point moves out. A stylised percentage split cannot represent it, and
that is precisely the gap in SAM.

### The invariant

Asserted **every period, for every partner**, inside `run_partnership` itself —
not in an optional test hook:

```
Σ capital accounts + Σ distributions − Σ contributions + Σ ITC basis reductions
    == cumulative book income/loss allocated
```

Plus: allocations sum to 100% of the item; outside basis never goes negative;
and a **loss** allocation never takes a capital account below its floor. A
capital account that does not reconcile to allocations is not a capital account,
it is a plug.

---

## The five structures, and when each one wins

Every structure returns the same `StructureResult` shape, which is what makes
them comparable.

### 1. Partnership flip — `flip.py`

Sponsor and tax-equity investor form an LLC. Pre-flip the investor takes 99% of
income, loss, credits and cash; post-flip 5%. **Yield-based** flips when the
investor's after-tax IRR reaches a contracted target; **fixed-date** flips on a
stated date.

*Wins when:* the sponsor cannot use depreciation and the deal is large enough to
carry tax-equity documentation cost. A partnership is the only structure here
that moves **both** the credit and the depreciation to someone who can use them.

*The circularity:* the investor's return depends on how long it holds 99% of the
tax items, which is the flip date; the flip date is when the return hits the
target. Solved with `scipy.optimize.brentq` on `[0, project life]`. To give
Brent a continuous function, the flip point may fall inside a year, and that
year's ratios are the weighted blend — at integer flip points this reduces
exactly to a clean boundary. `f(0) ≥ 0` means the target is met with an
immediate flip; `f(n) ≤ 0` means the target is unreachable, and the solve reports
`solved=False` rather than extrapolating a date that does not exist.

*Watch for:* a flip landing inside the five-year §50(a) recapture period. The
engine flags it **blocking**; real flip dates are negotiated past year five for
exactly this reason.

### 2. T-flip / hybrid — `tflip.py`

A flip with a §6418 transfer bolted on. Some or all of the credit is sold for
cash instead of being allocated to the investor.

*Wins when:* almost always, in 2026 — which is why Novogradac sees it on
essentially every transaction. It splits the difference: cash for the credit
today, an investor for the depreciation.

*The interaction to watch, and the reason this is a separate module:* the
investor is now buying depreciation and cash only, so it takes longer to reach
its target and **the flip point moves out**. `run_tflip` computes that movement
against an otherwise-identical pure flip and reports it as
`detail["flip_year_deferred_by"]`.

*The trap:* the **§50(c)(3) basis reduction still applies**. §6418 transfers the
credit, not the basis adjustment. Getting this wrong overstates depreciation by
15% of capex on a 30% ITC deal.

### 3. Preferred equity partnership — `preferred.py`

Priority return on unreturned capital, redemption ahead of the sponsor's common,
and normally the tax attributes too. 15% of 2025 ITC gross value.

*Wins when:* the sponsor wants leverage-like economics without a flip's
documentation, and can live with the priority claim. It is partnership equity,
so it runs on the same capital accounts and the same DRO cap as a flip.

*Watch for:* a preferred still outstanding at the target term. The engine flags
it; a real deal would answer with a coupon step-up, a sweep, or a forced sale,
none of which is modelled — so the reported sponsor return is optimistic.

### 4. Direct transfer (§6418) — `transfer.py`

The credit sold for cents on the dollar. No partner, no capital account, no DRO,
no §704(d). Closes in weeks, not months.

*Wins when:* the sponsor **can** use the depreciation itself. Then a transfer
monetises the one thing it cannot use and keeps everything else. It is also the
default answer for a PTC deal: more than 90% of PTC value moves this way.

*Loses when:* the sponsor cannot use depreciation. Then the deductions are
stranded and a partnership beats it — the engine flags `depreciation_stranded`
and the flip overtakes it on sponsor after-tax IRR. That reversal is asserted in
`tests/test_structures_selector.py`.

*Hard gate:* **§70512(h)** prohibits transfer to a specified foreign entity. A
blocked transfer returns `feasible=False` naming the rule, never a priced deal
with a warning.

### 5. Sale-leaseback — `sale_leaseback.py`

Sell the asset at FMV, lease it back. The lessor is the tax owner and takes the
credit **and** the depreciation; the lessee's only tax item is rent.

*Wins when:* tax equity is scarce or expensive — which is why NRF says it is
making a comeback. It is effectively **100% financing**: the sponsor gets its
whole cost back at closing.

*The 90-day window:* under **§50(d)(4)**, the sale must complete within **three
months** of the original placed-in-service date for the purchaser-lessor to be
treated as having placed the property in service. Outside it the credit is gone
for both parties, and rent rises sharply to compensate. Modelled, and flagged
**blocking**.

*The screen:* **Rev. Proc. 2001-28** — lessor at-risk ≥ 20%, residual ≥ 20% of
cost, lease term ≤ 80% of useful life. Run and reported as pass/fail. These are
advance-ruling guidelines, not substantive law, so the engine reports rather than
concludes.

*Rent is an output.* Level rent is solved with Brent's method so the lessor
earns its target after-tax yield given the credit, the depreciation and the
residual — which is how a lessor actually quotes.

*Watch for:* an undefined sponsor IRR. If the sale returns more than the
construction equity there is no net investment and no rate exists. The engine
says so and the selector ranks on NPV rather than inventing a number.

---

## The selector

```python
comparison = compare_structures(project, debt_terms, tax_inputs, configs)
```

The debt is sized and sculpted **once**, the waterfall runs **once**, the credit
determination is made **once** — in `build_context`. All five structures then
sit on identical project economics. Re-sizing per structure would make the
comparison meaningless.

### What is compared

| Metric | Meaning |
|---|---|
| **Sponsor after-tax IRR** | The primary ranking metric. Cash distributions, plus the tax effect of allocated income or loss, plus usable credits. |
| **Effective cost of capital** | IRR of third-party capital *in* against everything paid or **surrendered** to those providers — debt service, investor distributions, rent, and the tax attributes given away, valued at what the recipient realises. The definition is stated in full in `models.effective_cost_of_capital`, because the number is otherwise arguable. |
| **Cash timing** | First positive year, share received by years 5 and 10, cash-weighted average years, payback. A transfer front-loads; a flip defers past the flip point. Two structures with the same IRR are not the same deal. |
| **Sources and uses** | Senior debt + third-party equity + sponsor equity, reconciled to capex + IDC + fees + funded reserves. **Post-COD monetisation — §6418 transfer proceeds, a sale-leaseback price — is reported in its own column and is never a source**: a credit does not exist until the property is placed in service, so its sale reimburses committed capital rather than funding construction. Sources cannot exceed uses; an over-sized commitment raises a BLOCKING `funding_oversubscribed` risk. |
| **Key risks** | Structured `RiskFlag`s: §50(a) recapture, DRO-cap reallocation, suspended losses, FEOC and transfer-eligibility blocks, true-lease guideline failures, unredeemed preferred. |

### Ranking — deterministic and explainable

No scoring function, no weights, no judgement hidden in a constant:

1. **Sponsor after-tax IRR, descending** — where that rate is *meaningful*.
2. Feasible structures whose IRR is **not meaningful** rank after those whose
   IRR is, ordered by sponsor NPV at the stated discount rate, each carrying the
   reason on `sponsor_irr_not_meaningful_reason`.
3. **Infeasible structures rank last**, alphabetically, each carrying the rule
   or fact that blocked it.

**Why step 2 exists.** IRR is a rate *on an equity base*. A structure that
leaves the sponsor $2m in a $200m project and hands it 5% of the cash reports a
three-figure IRR while earning almost nothing, and it will out-rank a structure
returning a genuine 12%. Real sponsor equity IRRs in contracted US renewables
and storage run roughly **8-15% levered after tax**.
`models.irr_meaningfulness` therefore refuses a rate on four grounds — no net
sponsor investment; sponsor equity below 10% of the funding requirement; the
whole investment returned inside a year; or a rate above 40%. The comparison
then ranks on **sponsor NPV** with the **effective cost of capital** displayed
alongside as the cross-check, `StructureComparison.headline` states which basis
was used, and `table()["sponsor_after_tax_irr_display"]` is `None` so a UI
cannot print the number either. The four thresholds are Structura's own
reporting guards, not market data; they live in `structures/defaults.py`,
change no computed number, and decide only which rate may be shown as the
headline.

Ties — two meaningful IRRs within `RANKING_TOLERANCE` — break through a
published chain, and every break that fires is recorded in
`WhyThisWins.tie_breaks`:

* lower **effective cost of capital**;
* **earlier cash** (lower cash-weighted average years);
* lower **sponsor equity required**;
* finally the structure key, alphabetically, so the result is reproducible.

### The hard credit gate

A project that fails the FEOC / Material Assistance Cost Ratio test has **no
credit at all**. A credit-dependent structure — a direct transfer,
or a T-flip, which is *defined* by its transfer leg — then cannot be ranked
first, or at all. The selector enforces this centrally, independently of the
individual modules, because it is exactly the kind of result that must not
depend on one module remembering to check.

### `why_this_wins`

Structured facts, never prose: winner, primary metric, runner-up, margin, a
`Driver` per comparison metric with both values and the delta, the disqualified
structures with their reasons, the tie-breaks that fired, and caveats — including
every placeholder assumption the winner consumed and any blocking risk on it.
The narrator renders this. It never computes and never overrides.

---

## Quick start

```python
from datetime import date
from engine import DebtTerms, ProjectInputs
from engine.tax import MacrInputs, MacrMethod, TaxProject, TaxScenario
from engine.tax import Technology as TaxTechnology
from engine.structures import SponsorTaxProfile, compare_structures

comparison = compare_structures(
    ProjectInputs(capex=200_000_000.0),
    DebtTerms(target_dscr=1.20),
    TaxProject(
        technology=TaxTechnology.STORAGE,
        capacity_mw=100.0,
        capex=200_000_000.0,
        placed_in_service_date=date(2027, 1, 1),
        begin_construction_date=date(2026, 3, 1),
        physical_work_commenced=True,
        macr_inputs=MacrInputs(
            method=MacrMethod.USER_ASSERTED, asserted_ratio=0.80
        ),
    ),
    tax_scenario=TaxScenario(bonus_rate=1.0),
    sponsor=SponsorTaxProfile(can_use_depreciation=False),
)

print(comparison.headline)          # never leads with a meaningless rate
for row in comparison.table():
    print(row["rank"], row["label"], row["sponsor_after_tax_irr_display"])
for row in comparison.sources_and_uses_table():
    print(row["structure"], row["sources_total"], row["uses_total"])

why = comparison.why_this_wins
print(why.winner.value, "wins on", why.primary_metric)
for caveat in why.caveats:
    print("!", caveat)
for key, breach in comparison.capital_account_breaches:
    print("!", key.value, breach.describe())
```

A calibrated demo set lives in `engine/reference_deals.py` — contracted BESS,
safe-harboured solar, and a data-centre powered shell with no credit at all:

```python
from engine.reference_deals import reference_deal

deal = reference_deal("storage_bess_contracted")
print(deal.placeholder_warning())
print(deal.compare().headline)
```

Every step is available piecewise — `build_context`, `run_flip`, `run_tflip`,
`run_preferred`, `run_transfer`, `run_sale_leaseback`, `run_all_structures` —
and nothing is hidden inside `compare_structures`.

The partnership engine is usable on its own, with no project attached:

```python
from engine.structures import (
    PartnerRole, PartnerTerms, PeriodInputs, SharingRatios, run_partnership,
)
```

---

## Tests

```bash
.venv/bin/pytest tests/test_structures_*.py -q
```

| File | Covers |
|---|---|
| `test_structures_partnership.py` | Golden hand-checked capital accounts, the every-period integrity invariant, DRO cap and reallocation, minimum gain as a deemed DRO, minimum gain chargeback and its carryforward, §704(d) suspension and release, §731(a)(1) gain, determinism. |
| `test_structures_flip.py` | Ratio blending, the yield solve hitting its target exactly, monotonicity, an unreachable target, the fixed-date variant, the golden first three periods, the T-flip's effect on the flip point, recapture flagging. |
| `test_structures_monetisation.py` | Transfer proceeds and timing, the §70512(h) block, the MACR block, preferred cash schedule and redemption, sale-leaseback rent solve, lease/residual reconciliation, the §50(d)(4) window, Rev. Proc. 2001-28 failures. |
| `test_structures_selector.py` | Ranking determinism and order, the credit gate, `why_this_wins` tied to the numbers, the tie-break chain, the constructed dominance case, and the sponsor-tax-capacity reversal. Runs on the calibrated storage reference deal. |
| `test_calibration.py` | The funding-constraint invariant as a **property across all five structures** over seven configurations, the four IRR-meaningfulness guards, and structured capital-account breach reporting. |
| `test_reference_deals.py` | Sponsor-IRR bands, achieved DSCR against the published floor, sources equal uses, per-assumption provenance, and the credit gate on a deal with no credit. |

---

## Not advice

Illustrative modelling tool. **Not tax, legal, accounting or investment
advice.** Read `LIMITS_STRUCTURES.md`, `LIMITS.md` and
`engine/tax/UNVERIFIED.md` before relying on any number produced here.
