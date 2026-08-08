# UNVERIFIED — what `engine/tax` does not know for certain

**Law state verified: 2026-08-06.** This file is a required deliverable, not an
apology. SPEC.md §4.3 makes honesty about limits a non-negotiable, and §11 names
overclaiming as the single largest risk to the project. Where a specific numeric
threshold or rule detail could not be sourced in this build, the **structure**
was implemented and the **number** was made a clearly-named placeholder. Nothing
below was invented to look complete.

Every item here corresponds to a citation in `engine/tax/citations.py` whose
`confidence` is `PROVISIONAL` or `PLACEHOLDER`. `tests/test_tax_citations.py`
asserts that this file and that registry stay in sync — you cannot add an
uncertain rule without listing it here.

Confidence levels:

| Level | Meaning |
|---|---|
| `VERIFIED` | Carried by the verified rulebook (SPEC §2, checked live 2026-08-06) or black-letter statutory text. |
| `PROVISIONAL` | Believed correct and consistent with practice; not confirmed against primary text in this build. |
| `PLACEHOLDER` | Structure only. The number is a stand-in. **Do not rely on it.** |

---

## PLACEHOLDER — must be replaced before production use

### 1. `macr-thresholds` — the MACR threshold table
**Where:** `constants.PROVISIONAL_MACR_THRESHOLDS`, consumed by
`feoc.macr_threshold()`.

**What is verified:** exactly one cell. SPEC §2.3 states that solar eligible
components sold in **CY2026 require a MACR of at least 50%**. That cell is
registered in `constants.VERIFIED_MACR_CELLS` and is the only lookup that
returns `is_placeholder=False`.

**What is not:** every other technology/year cell. The statutory MACR tables in
OBBBA §70512 and the interim methodology in IRS Notice 2026-15 were not obtained
in this build. The shipped values escalate plausibly by year and differ by
technology — the **shape** is right — but they are **not authority**.

**To fix:** replace the dict with the statutory table. The structure
(`{Technology: {year: threshold}}`) matches how the statute tabulates it, and
`macr_threshold()` already handles year inheritance, so this is a data drop-in.
Then extend `VERIFIED_MACR_CELLS` (or delete it and flip the default).

**Also unresolved:** the statute tests §45X eligible components by **year of
sale**; Structura models facilities and uses the **placed-in-service year**.
Declared simplification.

---

### 2. `ptc-inflation-adjustment` — §45Y(c) annual factors
**Where:** `constants.PLACEHOLDER_PTC_INFLATION_ADJUSTMENT`, consumed by
`eligibility.ptc_rate_per_kwh()`.

**What is verified:** the §45Y(a)(2)(A) base amount of **0.3 ¢/kWh in 2022
dollars**, the **5x PWA multiplier**, the **rounding to the nearest 0.05 ¢**
under §45Y(c)(1), and the **ten-year credit period**.

**What is not:** the inflation adjustment factor for any year after the 2022
base year. The IRS announces it annually and it was not sourced here.

**Behaviour:** `ptc_rate_per_kwh()` **raises `NotImplementedError`** for any year
without a factor rather than returning a guessed rate. A fabricated PTC rate
would flow straight into a sponsor IRR, so refusing is the correct failure mode.

**To fix:** add `{year: factor}` entries from the annual IRS notice.

---

### 3. `notice-2025-08-safe-harbor` — elective assigned cost percentages
**Where:** `constants.PLACEHOLDER_NOTICE_2025_08_SAFE_HARBOR_PCT`, consumed by
`adders.domestic_content_adder()`.

**What is verified:** that Notice 2025-08 (January 2025) exists and provides
elective safe-harbor cost percentages for the domestic content adder (SPEC §2.4).

**What is not:** the percentages themselves, which are published per technology
**and per component** — a far richer structure than the single ratio stubbed
here.

**Behaviour:** electing the safe harbor raises `NotImplementedError` naming this
file. Actual-cost build-up via `domestic_content_pct` works normally.

**To fix:** replace the stub with the real per-component tables and rework the
lookup to accept a component schedule.

---

### 4. `notice-2025-42-applicability-date` — the prospective cut-off
**Where:** `constants.NOTICE_2025_42_APPLIES_TO_BOC_AFTER = 2025-09-02`.

**What is verified:** that Notice 2025-42 (August 2025) eliminated the **5% cost
safe harbor** for **wind and solar above 1.5 MW**, and that it was **vacated in
full** on 2026-06-06 (SPEC §2.5).

**What is not:** the exact date after which the notice applied. IRS notices of
this kind are normally prospective; the placeholder is set to the notice's issue
month so that all 2026 begin-construction dates are exercised by the litigation
toggle. A project with a **late-2025 BOC date** is the case sensitive to this.

**To fix:** confirm the applicability paragraph of the notice.

---

## PROVISIONAL — believed correct, not confirmed here

### 5. `energy-community-adder` — declared simplification
**Structura does not determine energy community status.** The statutory test has
three limbs — brownfield site; statistical area meeting a fossil-fuel employment
or tax-revenue test *and* an unemployment test; census tract with a post-1999
coal mine closure or post-2009 coal unit retirement — each requiring the annual
IRS/DOE appendices and a geospatial join.

The caller **asserts** qualification via `TaxProject.energy_community` and names
the limb in `energy_community_category`. The engine records the assertion in the
audit trail and marks the adder `PROVISIONAL`. The **adder amount** (2 points
base / 10 points with PWA) is treated as verified.

**To fix:** ingest the IRS energy community appendices and add a lookup keyed on
project location.

---

### 6. `phase-down-application` — does the §48E(e) haircut reach the bonuses?
The non-wind/solar phase-out (75% / 50% / 0% for BOC years 2034 / 2035 / 2036+)
is expressed as a percentage of the credit determined under §48E(a). Whether the
domestic content and energy community bonuses ride the same haircut was not
confirmed.

**Behaviour:** modelled as a switch. `PhaseDownApplication.ALL_CREDIT` (default)
haircuts everything; `BASE_ONLY` haircuts the base rate and leaves the bonus
amounts whole. Both are computed correctly; only the default is a judgement.

---

### 7. `bonus-depreciation` — §168(k) rate and acquisition-date mechanics
100% bonus expensing is understood to have been restored by OBBBA for qualified
property acquired after **2025-01-19**. The rate is a **caller-supplied input**
everywhere in the engine (`TaxScenario.bonus_rate`); `DEFAULT_BONUS_RATE = 1.00`
is only a default. The acquisition-date mechanics are **not** implemented — the
engine does not test whether a given project qualifies for the restored rate.

---

### 8. `straight-line-conventions` — averaging conventions
Declared simplifications in `depreciation.py`:

* the **half-year** convention is applied to every straight-line life, including
  **39-year nonresidential real property**, which properly uses the **mid-month**
  convention;
* the **mid-quarter** convention (required where >40% of basis is placed in
  service in the final quarter) is **not** implemented;
* **state** depreciation, which frequently decouples from federal bonus, is out
  of scope for Phase 2.

The **MACRS 5-year and 15-year GDS tables** themselves (IRS Pub. 946 Table A-1)
and the **§50(c)(3) 50% basis reduction** are verified.

---

### 9. `section-6417-direct-pay` — applicable entity list
That §6417 survived OBBBA intact is verified (SPEC §2.2). The enumerated list of
applicable entities in `transfer.APPLICABLE_ENTITIES`, and the rule that a
taxable entity may elect direct pay only for §45Q/§45V/§45X, are stated from the
statutory categories rather than confirmed against text. §45V is not modelled.

---

### 10. `excessive-credit-transfer-penalty` — §6418(g)(2)
The 20% excessive credit transfer penalty is used only as **narrative
justification** for a non-zero transaction-cost default. It is not computed into
any cashflow.

---

## Market defaults that are assumptions, not law

These are not tax rules, but they are inputs a user will take at face value, so
they are declared:

| Constant | Value | Basis |
|---|---|---|
| `DEFAULT_ITC_TRANSFER_PRICE` | 0.90 | Implied by the SPEC §2.7 ITC bridge quote ("75% advance, ~67.5% net at 90¢"). |
| `DEFAULT_PTC_TRANSFER_PRICE` | 0.92 | **Placeholder.** No PTC clearing price is carried by the verified rulebook. |
| `DEFAULT_TRANSFER_TRANSACTION_COST_PCT` | 0.02 | **Placeholder.** Broker fee + credit insurance + legal. |

`ITC_MARKET_MIX_2025`, `PTC_DIRECT_TRANSFER_SHARE_2025` and
`TRANSFER_MARKET_SIZE_USD_BN` are Crux figures quoted in SPEC §2.2 and are used
for **context and narration only** — never as arithmetic inputs to a deal.

---

## Out of scope for Phase 2 (not gaps — deferred by plan)

* §704(b) capital accounts, deficit restoration obligations, outside basis,
  suspended losses, minimum gain chargeback (SPEC §6.3, Phase 2 partnership
  work — a sibling workstream).
* State and local tax credits and incentives.
* §45X advanced manufacturing production credit as a *product* (the section is
  modelled only as a transferable credit type for the §70512(h) test).
* Recapture (§50(a)) and the five-year ITC recapture period.
* At-risk (§49) and passive activity (§469) limitations.
* Alternative minimum tax and the corporate alternative minimum tax interaction
  with credits.
