# Phase 2 — the current-law tax engine (`engine/tax/`)

**Built:** 2026-08-06 · **Law state verified:** 2026-08-06 · **Tests:** 159 passing

Phase 2 of SPEC.md §9 delivers §6.4 — the current-law module. This is the
product's moat: SPEC §3.2 verified that **SAM 2026.7.3 / SSC 308 has zero
mentions of OBBBA, transferability, the domestic content adder, the energy
community adder, the §48E/§45Y phase-out or FEOC across all versions.** No
competitor is current here.

> The partnership-tax half of SPEC §9 Phase 2 — §704(b) capital accounts, DRO,
> outside basis, suspended losses, minimum gain chargeback — is a **separate
> workstream** and is not in this deliverable. See "Deferred" below.

---

## What was built

```
engine/tax/
├── __init__.py            public API + compute_tax() orchestrator
├── enums.py               Technology, CreditType, EligibilityPath, Notice202542Status, …
├── constants.py           EVERY number, each with authority + confidence
├── models.py              TaxProject, TaxScenario, and all result dataclasses
├── citations.py           32-entry structured citation registry (the moat)
├── eligibility.py         §48E/§45Y paths, PWA, adder stacking, phase-down
├── adders.py              domestic content (50% in 2026), energy community
├── feoc.py                MACR computation + thresholds + §70512(h)
├── begin_construction.py  5% SH vs Physical Work Test + the litigation toggle
├── depreciation.py        MACRS 5/15, SL 5/15/20/39, bonus, §50(c)(3)
├── transfer.py            §6418 economics, §6417 direct pay
├── README.md              the law model + the "when the law changes" runbook
└── UNVERIFIED.md          every rule this package is not certain about

tests/
├── test_tax_eligibility.py         24 tests
├── test_tax_adders.py              18
├── test_tax_feoc.py                25
├── test_tax_begin_construction.py  14
├── test_tax_depreciation.py        22
├── test_tax_transfer.py            12
└── test_tax_citations.py           44
```

`engine/tax` is **self-contained**: stdlib only, no imports from the rest of
`engine`, so it can be lifted into the `/current-law` page, the narrator or a
separate service without dragging the sculpting spine along. It was built
concurrently with Phase 1 and touches nothing outside `engine/tax/` and
`tests/test_tax_*.py`.

---

## Implemented with full confidence

Every item below is carried by SPEC §2 (verified live 2026-08-06) or is
black-letter statutory text, and each has a test **and** a citation.

| Rule | Where | Test |
|---|---|---|
| Wind/solar **BOC cliff 2026-07-04** (inclusive), four-year continuity window | `eligibility.py` | `test_solar_began_construction_before_the_cliff_is_eligible` |
| Wind/solar **PIS backstop 2027-12-31** (inclusive) | `eligibility.py` | `test_solar_missed_cliff_but_placed_in_service_by_2027_uses_the_backstop` |
| **Zero credit** where both are missed | `eligibility.py` | `test_solar_missed_cliff_and_backstop_gets_zero` |
| Storage/geothermal/nuclear/hydro runway: full → 2033, **75/50/0%** for 2034/35/36+ | `eligibility.py` | `test_storage_phase_down_by_begin_construction_year` |
| **6% base / 30% PWA** (5x multiplier), ITC and PTC | `eligibility.py` | `test_pwa_compliance_is_the_difference_between_30_percent_and_6_percent` |
| Domestic content threshold **40/45/50/55%**, cliff at **50% in 2026** | `adders.py` | `test_domestic_content_49_percent_in_2026_is_denied` / `..._50_percent_..._granted` |
| Adder amount **2pp base / 10pp PWA** on ITC; **×1.10** on PTC | `adders.py` | `test_adder_points_scale_with_pwa` |
| **MACR pass/fail is disqualifying**, not a warning | `feoc.py` → `eligibility.py` | `test_macr_failure_kills_credit_eligibility_it_is_not_a_warning` |
| FEOC effective **2026-01-01** | `feoc.py` | `test_feoc_does_not_apply_before_2026` |
| Solar eligible-component MACR **≥50% CY2026** (the one sourced cell) | `feoc.py` | `test_solar_cy2026_threshold_is_the_one_verified_cell` |
| **§70512(h)** transfer ban: 5 credits, specified foreign entity, TY beginning after 2025-07-04 | `feoc.py` / `transfer.py` | `test_transfer_to_a_specified_foreign_entity_is_blocked` |
| **5% cost safe harbor** and **Physical Work Test**; Notice 2025-42 >1.5 MW wind/solar | `begin_construction.py` | `test_five_percent_safe_harbor_boundary`, `test_notice_2025_42_does_not_reach_small_wind_and_solar` |
| ***Oregon Environmental Council v. IRS*, No. 25-4400 (CKK)** vacatur → 5% SH restored, as a **toggleable scenario** | `begin_construction.py` | `test_litigation_toggle_flips_eligibility_for_a_wind_project` |
| Four-year continuity safe harbor | `begin_construction.py` | `test_continuity_deadline_is_end_of_the_fourth_following_calendar_year` |
| **§50(c)(3): basis = capex − 0.5 × ITC** | `depreciation.py` | `test_itc_basis_reduction_is_half_the_credit` |
| MACRS 5-year and 15-year GDS tables (Pub. 946 A-1) | `depreciation.py` | `test_macrs_5_year_table_matches_pub_946` |
| **§6418 alive**, §6417 intact; 2025 market shape | `transfer.py` | `test_market_context_carries_the_crux_2025_shares` |

### ⚖️ The litigation fork, concretely

The same 200 MW wind project, relying on the 5% cost safe harbor, BOC
2026-06-01, PIS 2029-06-30:

| Scenario | Begin construction | Credit |
|---|---|---|
| `VACATED` (default — current law) | established 2026-06-01 | **30% ITC — $60m** |
| `REINSTATED_ON_APPEAL` | 5% SH unavailable → never established; PIS past the 2027-12-31 backstop | **$0** |

One enum flips a $60m outcome. That is the differentiating feature.

---

## Placeholders requiring verification

Full detail in `engine/tax/UNVERIFIED.md`. `tests/test_tax_citations.py` fails
if an uncertain rule is not disclosed there, so the two cannot drift.

**`PLACEHOLDER` — do not rely on the number:**

1. **The MACR threshold table** (`PROVISIONAL_MACR_THRESHOLDS`) — **the largest
   gap.** Only solar/CY2026 = 50% is sourced. All other technology/year cells
   are stand-ins. The *structure* matches the statutory table shape, so real
   values drop in; every lookup reports `threshold_is_placeholder`.
2. **§45Y(c) inflation adjustment factors** — only the 2022 base year ships.
   `ptc_rate_per_kwh()` **raises `NotImplementedError`** for any later year
   rather than guessing. The 0.3 ¢/kWh base, the 5x multiplier, the 0.05 ¢
   rounding and the ten-year period are verified.
3. **Notice 2025-08 elective safe-harbor assigned cost percentages** — not
   shipped. Electing the safe harbor raises rather than inventing a percentage.
4. **Notice 2025-42's prospective applicability date** (`2025-09-02`) — the
   effect and scope are verified; the exact cut-off is not. Only a late-2025 BOC
   date is sensitive to it.

**`PROVISIONAL` — believed correct, not confirmed against primary text:**
energy community qualification tests (see below), whether the §48E(e) phase-down
haircuts the bonus amounts, §168(k) bonus acquisition-date mechanics, the §6417
applicable-entity list, and the §6418(g)(2) 20% penalty.

---

## Deliberate simplifications (declared, not silent)

* **Energy community is asserted, not computed.** The three statutory limbs —
  brownfield, statistical-area employment/unemployment tests, post-1999 coal
  mine / post-2009 coal unit census tracts — need the annual IRS/DOE appendices
  and a geospatial join. The caller asserts qualification and names the limb;
  the engine records it and marks the adder `PROVISIONAL`.
* **Phase-down keys on the asserted BOC year** even where begin construction was
  not validly established (non-wind/solar only, where BOC does not gate
  eligibility).
* **FEOC uses the placed-in-service year.** The statute tests §45X eligible
  components by year of *sale*; Structura models facilities.
* **Half-year convention applied to all straight-line lives**, including 39-year
  real property (properly mid-month). Mid-quarter not implemented.
* **Uncertified components are treated as fully PFE-attributable** in the MACR
  build-up — conservative by design, and the diligence default a tax-credit
  buyer will insist on.
* Transfer transaction costs are a single percentage of face, not a modelled
  broker/insurance/legal stack.

---

## Deferred to later phases

* **Partnership tax rigor (SPEC §6.3)** — §704(b) capital accounts, DRO and DRO
  caps, outside basis, suspended losses, minimum gain chargeback, HLBV. Sibling
  workstream; `engine/tax` supplies the credit and depreciation inputs it needs.
* **Structure selector (SPEC §6.2, Phase 3)** — the five 2026 structures. The
  transfer economics and market-mix context this needs are already in
  `transfer.py`.
* **`/current-law` page (SPEC §7 M4, Phase 5)** — `get_all_citations()` and
  `unverified_citations()` are the render feed and are already tested for
  completeness.
* Recapture (§50(a)), at-risk (§49), passive activity (§469), CAMT interaction,
  state credits, §45X as a product.

---

## Known integration item for the repo owner

`pyproject.toml` declares `[tool.setuptools] packages = ["engine"]`, which does
**not** include the `engine.tax` subpackage in a built distribution. Tests run
fine because `[tool.pytest.ini_options] pythonpath = ["."]` imports from source.
Before packaging, change it to `packages = ["engine", "engine.tax"]` (or switch
to `find`). Not changed here: `pyproject.toml` is owned by the Phase 1
workstream.

---

## Verification

```
$ .venv/bin/pytest tests/test_tax_*.py
........................................................................ [ 45%]
........................................................................ [ 90%]
...............                                                          [100%]
159 passed in 0.60s
```

Full repository suite (Phase 1 + Phase 2): **1241 passed**.
