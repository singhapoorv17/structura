# LIMITS — what `engine/structures` simplifies, and what it does not know

**Built 2026-08-06. Law state inherited from `engine/tax`, verified 2026-08-06.**

The rule followed in this package is **implement the structure, declare the
simplification, never invent tax precision**. This file is the list of
simplifications.

The companion file is `engine/tax/UNVERIFIED.md`. Everything disclosed there —
most importantly the **MACR threshold table** and the **§45Y inflation
factors** — flows straight through this package and is *not* restated item by
item below. `engine.structures.selector` propagates those warnings into
`StructureComparison.warnings`, and `tests/test_structures_selector.py::
test_the_unverified_macr_threshold_is_propagated_not_papered_over` asserts it.

---

## 1. Partnership tax — what is full-fidelity and what is not

### Implemented in full

| Mechanic | Authority | Where |
|---|---|---|
| §704(b) capital account maintenance: contributions, allocations, distributions | Treas. Reg. §1.704-1(b)(2)(iv) | `partnership.run_partnership` |
| Alternate test for economic effect: allocation may not breach the DRO floor | Treas. Reg. §1.704-1(b)(2)(ii)(d) | `_allocate_loss_with_dro_caps` |
| DRO cap → **reallocation pro rata to remaining capacity**, allocations still summing to 100% | same | same |
| Minimum gain as a **deemed DRO**, so a no-DRO investor can still absorb loss | Treas. Reg. §1.704-2(g)(1) | floor = `-(dro_cap + minimum_gain_share)` |
| Outside basis: contributions, income, liability share, distributions, losses allowed | §705 | `run_partnership` step 7 |
| §752 nonrecourse liability share, tiers 1 and 3 | Treas. Reg. §1.752-3(a)(1), (a)(3) | same |
| Basis limitation on loss deductibility, with an indefinite carryforward | §704(d) | same |
| Suspended losses freed FIFO as basis is restored | Treas. Reg. §1.704-1(d) | same |
| §731(a)(1) gain on a distribution exceeding basis | §731(a)(1) | `excess_distribution_gain` |
| 50% ITC basis reduction, charged to capital accounts as an item of loss and to outside basis on the credit ratio | §50(c)(3), §50(c)(5), Treas. Reg. §1.704-1(b)(2)(iv)(j) | `PeriodInputs.itc_basis_reduction` |
| Tax items following the book allocation actually made, including the reallocated portion | Treas. Reg. §1.704-1(b)(1)(vii) | `run_partnership` |

The **integrity invariant** — Σ capital accounts + Σ distributions − Σ
contributions + Σ ITC basis reductions == cumulative allocations — is asserted
**every period, for every partner**, inside `run_partnership` itself. It is not
an optional test hook.

### Simplified, and declared

1. **Minimum gain is pooled, not tracked property by property.**
   Partnership minimum gain is computed as
   `max(0, nonrecourse liability − §704(b) book basis)` on a single pooled
   asset. Treas. Reg. §1.704-2(d) computes it property by property. For a
   single-asset project company these coincide; for a portfolio they do not.

2. **A partner's minimum-gain share is built from nonrecourse deductions only.**
   Treas. Reg. §1.704-2(g) builds the share from nonrecourse deductions *and*
   from distributions of nonrecourse liability proceeds. The second component is
   not separately identified. Where a project distributes refinancing proceeds,
   the modelled share is understated.

3. **Minimum gain chargeback is simplified.** A net decrease in minimum gain
   triggers a chargeback of
   gross income allocated in proportion to each partner's tracked minimum-gain
   share, limited to the year's book income with the excess carried forward
   (Treas. Reg. §1.704-2(f)(3)). **Not implemented:** the exceptions and waivers
   in §1.704-2(f)(2)–(5), the ordering rules of §1.704-2(j), and the separate
   **partner nonrecourse debt minimum gain** regime of §1.704-2(i).

4. **§704(c) is not implemented.** Book and tax ledgers are maintained
   separately and a caller-supplied book/tax difference is honoured, but no
   forward or reverse §704(c) layer is computed and neither the traditional,
   curative nor remedial method is available. In the ordinary case this is
   harmless: for cash-funded property with book basis equal to tax basis,
   Treas. Reg. §1.704-1(b)(2)(iv)(g)(3) makes book depreciation track tax
   depreciation exactly, which is why `ProjectEconomics.book_depreciation`
   defaults to `tax_depreciation`. It matters where a partner contributes
   appreciated property or a development fee is capitalised.

5. **Qualified income offset is not implemented.** The DRO-cap floor prevents
   the deficits an allocation could create, but a **distribution** can still
   drive a capital account below its floor. Treas. Reg. §1.704-1(b)(2)(ii)(d)
   would cure that with a QIO. Structura instead **reports** it, as a
   *structured* result rather than a sentence: `PartnershipResult` carries a
   `CapitalAccountBreach` per affected partner with every period, every year,
   the worst breach and its period, which becomes a `capital_account_below_floor`
   risk flag (CAUTION for one period, **BLOCKING** for a sustained deficit) and
   is collected on `StructureComparison.capital_account_breaches`.

   **The commonest trigger is worth naming, because it is a modelling result.**
   §6418(b) excludes transfer proceeds from gross income. Paying them into the
   partnership (`TFlipConfig.proceeds_to_partnership=True`) therefore distributes
   cash with **no matching book allocation**, so the recipient's capital account
   falls by the full amount and stays below its floor. That is why the reference
   deals sell at the holdco — which is also market practice.

6. **§465 at-risk and §469 passive activity limitations are not modelled.**
   Only the §704(d) basis limitation restricts a loss. For a corporate
   tax-equity investor this is usually the binding limit anyway; for an
   individual it is not.

7. **§731(a)(1) gain is a tax item only.** It is computed and reported but is
   not fed back into the §704(b) capital account, because it is not a book item.

8. **Capital account revaluations ("book-ups") are not modelled.** Treas. Reg.
   §1.704-1(b)(2)(iv)(f) permits a revaluation on entry of a new partner; the
   engine has no event for it.

9. **HLBV** (hypothetical liquidation at book value) reporting is **not**
   implemented. The ledger contains everything
   an HLBV calculation needs — capital accounts, DRO, minimum gain — but no
   liquidation waterfall is run.

10. **No liquidating distribution.** The model ends at the last operating year
    without a hypothetical sale, so a residual positive capital account is left
    standing and a residual deficit is never restored. Terminal-value and exit
    modelling is out of scope.

---

## 2. Structure-level simplifications

### Partnership flip (`flip.py`)

* The flip is modelled as a **change in sharing ratios**, not as a purchase of
  the investor's residual interest. Real flips frequently carry a **sponsor
  call option** at the flip; no option is modelled and no exercise price is
  paid.
* **PAYGO** — contingent investor contributions tied to production, standard in
  wind PTC deals — is not implemented. The investor funds once, at closing.
* **Back-leverage** at the sponsor holdco is not modelled. This is the most
  consequential omission in the package, and it drives how the reference deals
  are calibrated: a 30% §48E credit is a **source**, not a return,
  so an ITC deal cannot also carry maximum DSCR-sized senior debt without the
  stack exceeding 100% of cost. Real sponsors take the resulting DSCR headroom
  as holdco back-leverage. Structura instead expects the caller to set a senior
  gearing cap that closes the stack at 100%, which is what
  `engine/reference_deals.py` does — so the reference deals come out
  **gearing-bound with coverage well above the market floor**, and say so.
* The yield-based solve assumes the investor's after-tax series has a **single
  sign change**, which is what makes its IRR unique. A pre-flip cash share too
  low to cover the tax on the investor's income share breaks that; `run_flip`
  counts the sign changes and warns, but does not refuse.
* The flip point is allowed to fall **inside** a year, with that year's ratios
  blended. This is a modelling device to make the root find continuous; a real
  LLC agreement flips on a date.
* Investor **capital account deficits caused by distributions** are reported,
  not cured (see §1.5 above).

### T-flip (`tflip.py`)

* The transfer is priced on a **slice** of the credit by scaling the face value
  handed to `engine.tax.model_transfer`. Real partial transfers may price
  differently from a whole-credit sale; no size discount or premium is applied.
* Transfer proceeds default to landing **inside the partnership**, on the basis
  that the §6418 election is made by the entity that owns the facility. Set
  `proceeds_to_partnership=False` for a holdco-level sale.
* The reported `flip_year_deferred_by` compares against an otherwise-identical
  pure flip with the **same investor commitment**. In practice an investor
  buying only depreciation would also write a smaller cheque, which would offset
  part of the deferral.
* No **ITC bridge loan** is modelled, though the market advance rates are
  published (98% covered at SOFR+150; 75% uncovered at SOFR+225; NRF 2026).
  Transfer proceeds
  arrive in the settlement year, undiscounted and unbridged. This is why
  `SourcesAndUses.credit_proceeds_at_cod` is always zero: **a §6418 credit does
  not exist until the property is placed in service, so its sale cannot fund
  construction.** Proceeds are reported as `post_cod_monetisation` — a
  reimbursement of committed capital — and are excluded from every source
  total. That exclusion is regression-tested in `tests/test_calibration.py`.

### Preferred equity (`preferred.py`)

* Modelled as a **partnership interest**, not as an instrument that might be
  recharacterised as debt for tax purposes. That characterisation is a
  facts-and-circumstances question Structura does not attempt.
* No **coupon step-up**, no **cash sweep** on a missed redemption, and no
  **forced sale** remedy. A preferred still outstanding at the target term or at
  the end of the model is flagged as a risk, and the reported sponsor return is
  correspondingly optimistic.
* The preferred's income and credit sharing ratio is a **stated input**, not
  derived from the priority of its cash.

### Direct transfer (`transfer.py`)

* Transaction costs are a **single percentage of face**, not a modelled
  broker / credit-insurance / legal stack. The default is a placeholder
  inherited from `engine/tax` — see `UNVERIFIED.md`.
* The §6418(g)(2) **20% excessive credit transfer penalty** is used as narrative
  justification for a non-zero cost, and is never computed into a cashflow.
* **Recapture is flagged, never modelled.** No §50(a) recapture event is
  simulated in any structure.
* PTC transfers are priced with the same single-price mechanic as an ITC even
  though a PTC strip delivers over ten years and prices differently. The PTC
  default price is itself a placeholder (`engine/tax/UNVERIFIED.md`).

### Sale-leaseback (`sale_leaseback.py`)

* The senior facility is assumed **repaid out of the sale proceeds at closing**.
  No lessee-level back-leverage is modelled.
* **Rent is level.** Stepped and seasonal rents are not supported, and the §467
  rental-agreement rules that can force accrual on a stepped lease are not
  implemented.
* The **purchase option is assumed exercised** at the assumed residual. No
  option-value analysis is performed, and no test is run for whether the strike
  is a bargain (the fact pattern that recharacterises a lease as a financing).
* **Rev. Proc. 2001-28** is applied as a pass/fail *screen* and reported as
  such. It sets advance-ruling guidelines, not substantive law; a lease failing
  one is not automatically a financing. The lessor's at-risk test is modelled
  crudely as "the lessor paid cash for the whole asset", since no lessor-level
  leverage is modelled.
* The **§50(d)(4) three-month window** is applied to the stated
  `months_after_placed_in_service`. The consequence modelled outside the window
  is total loss of the credit to both parties; the ITC pass-through election
  mechanics under former §48(d) are not modelled.
* Where the sale returns more than the sponsor's construction equity, the
  sponsor has no net investment and its IRR is **undefined**. That is reported
  honestly (`sponsor_after_tax_irr=None`, a warning, and an `INFO` risk flag)
  and the selector ranks such a structure on NPV rather than inventing a rate.

---

## 3. Selector simplifications

* **One debt sizing for all five structures.** The debt is sculpted once, in
  `build_context`, and every structure sits on it. In reality a lender prices
  and sizes differently against a flip than against a sale-leaseback. Re-sizing
  per structure would, however, make the comparison meaningless, so the
  simplification is deliberate.
* **Effective cost of capital** is a defined quantity, not a market convention:
  the IRR of third-party capital in against everything paid or surrendered to
  those providers, with tax attributes valued at what the **recipient**
  realises. The definition is stated in full in
  `models.effective_cost_of_capital`. A different but equally defensible
  definition would value the attributes at what the *sponsor* gives up, and
  would rank differently for a sponsor with no tax appetite.
* **Ranking is on sponsor after-tax IRR** — **but only where that rate is
  meaningful.** IRR is a rate *on an equity base*; shrink the base far
  enough and the rate describes the base rather than the deal.
  `models.irr_meaningfulness` refuses a rate on four grounds — no net sponsor
  investment, sponsor equity below `DE_MINIMIS_SPONSOR_EQUITY_SHARE` (10%) of
  the funding requirement, payback inside `DE_MINIMIS_SPONSOR_PAYBACK_YEARS`
  (1.0), or a rate above `IMPLAUSIBLE_SPONSOR_IRR` (40%) against a market range
  of roughly 8-15% levered after tax. Such a structure is ranked on **sponsor
  NPV**, behind every structure with a real rate, carries the reason on
  `sponsor_irr_not_meaningful_reason`, and has its rate suppressed from
  `table()["sponsor_after_tax_irr_display"]`.

  **These four thresholds are Structura's own reporting guards, not market
  data.** They live in `engine/structures/defaults.py` with every other
  constant, they change no computed number, and they decide only which rate is
  shown as the headline. `effective_cost_of_capital` is unaffected and remains the
  cross-check, displayed alongside in `table()`, in `WhyThisWins.drivers` and in
  `StructureComparison.headline`.

* **Sources cannot exceed uses.** Every structure returns a `SourcesAndUses`
  statement reconciling senior debt + third-party equity + sponsor equity to
  total project cost. An over-sized commitment does not silently floor
  sponsor equity at zero: it raises a **BLOCKING** `funding_oversubscribed` risk
  naming the excess. Asserted as a property across all five structures over
  seven configurations in `tests/test_calibration.py`.
* **No scenario sweep.** `compare_structures` runs one scenario. P50/P90/P99,
  the begin-construction litigation fork and the FEOC-fail case are not swept;
  the plumbing exists — pass a different `TaxScenario` or reuse a
  `StructureContext`.
* **Annual periods.** Sub-annual model periods are summed into tax years by
  `models._annualise`, and a trailing part-year is treated as a whole year.
  Partnership tax is annual, so this is correct for the tax ledger, but it loses
  intra-year cash timing.
* **No state tax** anywhere. Federal only.

---

## 4. Market assumptions that are placeholders, not data

Tax-equity and lease pricing is quoted deal by deal. Norton Rose Fulbright,
*Cost of Capital: 2026 Outlook*, publishes debt pricing and DSCR by technology;
it publishes no tax-equity target yield, no pre-flip sharing split and no
preferred coupon. Crux publishes market *shares*, not prices. So the following ship as
labelled placeholders in `engine/structures/defaults.py`, are surfaced as
warnings on every result that consumed one, and are expected to be overridden:

| Constant | Value | Status |
|---|---|---|
| `PLACEHOLDER_TE_TARGET_AFTER_TAX_IRR` | 6.50% | **PLACEHOLDER.** The single most important input to a yield-based flip. |
| `PLACEHOLDER_TE_INVESTMENT_PER_CREDIT_DOLLAR` | 1.15 | **PLACEHOLDER.** Used only to derive a commitment when none is stated. |
| `PLACEHOLDER_MAX_INVESTOR_SHARE_OF_EQUITY` | 0.80 | **PLACEHOLDER.** Cap on the derived commitment so the sponsor retains equity. Ignored when a commitment is stated. |
| `PLACEHOLDER_PREFERRED_RETURN` | 9.00% | **PLACEHOLDER.** |
| `PLACEHOLDER_PREFERRED_TARGET_TERM_YEARS` | 10 | **PLACEHOLDER.** |
| `PLACEHOLDER_LESSOR_TARGET_AFTER_TAX_IRR` | 7.00% | **PLACEHOLDER.** |
| `PLACEHOLDER_SALE_LEASEBACK_RESIDUAL_PCT` | 20% | **PLACEHOLDER**, set at the Rev. Proc. 2001-28 guideline floor. A floor is not a forecast. |
| `PLACEHOLDER_PRE_FLIP_TE_ALLOCATION_SHARE` / `..._POST_...` | 99% / 5% | The classic 99/1 → 5/95 flip; the fit to any given deal is not sourced. |
| `PRE_FLIP_TE_CASH_SHARE` / `POST_FLIP_TE_CASH_SHARE` | 99% / 5% | The classic flip applied to cash as well. Real deals — wind PTC especially — run a much lower pre-flip cash share. |

`engine/reference_deals.py` adds a second, deal-scoped layer of the same
discipline: capex per kW, offtake pricing, operating cost and every tax-equity /
preferred / lease commitment ship as `Assumption(is_placeholder=True)` with
their reason, are listed by `ReferenceDeal.placeholder_assumptions()`, and reach
`StructureComparison.warnings`. **No free source of PPA prices exists**, so no
reference deal carries a sourced revenue line; a test asserts every deal
carries at least one placeholder.

The statutory constants (`ITC_RECAPTURE_PERIOD_YEARS`,
`ITC_RECAPTURE_VESTING_PER_YEAR`, `ITC_BASIS_REDUCTION_FRACTION`,
`SALE_LEASEBACK_ITC_WINDOW_MONTHS`, the three Rev. Proc. 2001-28 guidelines) are
black-letter and are **not** placeholders.

---

## 5. Citation identifiers

Result objects in this package carry `citation_ids` such as
`reg-1-704-1b2iv-capital-accounts`, `section-704d-basis-limitation`,
`section-50a-recapture`, `rev-proc-2001-28-true-lease`,
`section-50d4-sale-leaseback-window` and `rev-proc-2007-65-flip-guidelines`.

**These are local identifiers.** They are not yet registered in
`engine/tax/citations.py`. Before the `/current-law` page renders them, add a
`Citation` for each with its `authority`, `plain_english`, `source`,
`verified_on` and `confidence`, following the runbook in
`engine/tax/README.md` § "When the law changes".

---

## 6. Not advice

Illustrative modelling tool. **Not tax, legal, accounting or investment
advice.** Public sources only; no real transaction's assumptions and no
employer data appear anywhere in this package.
