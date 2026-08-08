# `engine/tax` — the current-law tax engine

**Law state verified: 2026-08-06.** Re-verify before launch. One rule in here is
in active litigation and one is expressly interim guidance.

---

## Why this package is the product

SPEC.md §3.2 establishes the competitive fact this whole build rests on. A full
release-note and issue search of **SAM 2026.7.3 / SSC 308** — the only credible
incumbent, and a genuinely good piece of software — returns **zero mentions** of
OBBBA, "One Big Beautiful Bill", transferability, the domestic content adder,
the energy community adder, the §48E/§45Y phase-out, or FEOC, across all
versions. **SAM has not been updated for the current tax regime at all.** Ed
Bodmer's library, the other serious free resource, shows no evidence of OBBBA or
FEOC updates either.

Structura's edge over both is **not novelty of the math**. It is packaging,
currency, reproducibility and auditability. Say that plainly; claiming novelty
you do not have is the fastest way to lose a practitioner audience (SPEC §3.4).

That makes this package a maintenance commitment, not a feature. Treat law
updates as **features, not maintenance** (SPEC §11).

---

## The law model, in one page

### 1. OBBBA bifurcated §48E/§45Y — it did not repeal them

| Technology | Rule |
|---|---|
| **Wind, solar** | Must have **begun construction on or before 2026-07-04**. If so: standard **four-year continuity window**. If not: must be **placed in service by 2027-12-31**, or the credit is **zero**. |
| **Storage, geothermal, nuclear, hydro** | Untouched by the accelerated cliff. Full §48E for **begin construction through 2033**, then **75% (2034)**, **50% (2035)**, **0% from 2036**. |

The product consequence is stated in SPEC §6.4 and should drive the demo:
**lead with storage and data centers.** Wind and solar's forward pipeline is now
safe-harboured inventory with a 2030 outside date; storage has a seven-year
runway.

### 2. Rate build-up

```
base 6% ITC                                  (0.3 ¢/kWh PTC, 2022 dollars)
  ×5   prevailing wage & apprenticeship  →  30%      (1.5 ¢/kWh)
  +10pp domestic content                                (or ×1.10 on the PTC)
  +10pp energy community                                (or ×1.10 on the PTC)
  ×    §48E(e) phase-down                    (non-wind/solar, BOC 2034+)
  ×0   if the FEOC / MACR gate fails
```

Without PWA the adders are **2 points**, not 10 — the same 5x multiplier that
lifts 6% to 30% lifts 2 points to 10. SPEC §2.4 quotes the 10-point figure,
which presumes PWA compliance.

### 3. Domestic content threshold escalates

40% (pre-2025) → 45% (2025) → **50% (2026)** → 55% thereafter. It is a **cliff**:
49% in 2026 gets nothing, 50% gets the whole adder. Notice 2025-08 offers
elective safe-harbor assigned cost percentages (**not shipped** — see
`UNVERIFIED.md`).

### 4. FEOC / MACR is a pass/fail gate on eligibility

Effective **2026-01-01**. IRS **Notice 2026-15** (released **2026-02-12**) is the
interim methodology: Material Assistance Cost Ratio, interim safe harbors,
supplier certifications, DOE-derived default cost tables.

```
MACR = (total direct costs − PFE-attributable costs) / total direct costs
```

Below the applicable threshold, **the credit is denied**. `assess_feoc()` returns
`passes=False` and `evaluate_eligibility()` converts that into a zero credit with
a disqualification reason. It is never a warning.

### 5. ⚖️ Begin construction is in active litigation — so it is a scenario

* Two methods: **5% cost safe harbor** and the **Physical Work Test**, each
  followed by the **four-year continuity safe harbor**.
* **IRS Notice 2025-42** (Aug 2025) removed the 5% safe harbor for **wind/solar
  above 1.5 MW**.
* **2026-06-06:** *Oregon Environmental Council v. IRS*, No. 25-4400 (CKK)
  (D.D.C.) **vacated Notice 2025-42 in full** under the APA and remanded. **The
  5% safe harbor is restored.** A government appeal/stay is expected and the
  court acknowledged the appellate timeline runs past 2026-07-04.

```python
TaxScenario(notice_2025_42_status=Notice202542Status.VACATED)              # default: current law
TaxScenario(notice_2025_42_status=Notice202542Status.REINSTATED_ON_APPEAL) # the appeal outcome
```

For a >1.5 MW wind project that relied on the 5% safe harbor, flipping that one
enum is the difference between a 30% ITC and zero. That is the whole point.

### 6. §6418 transferability is ALIVE, and §6417 direct pay is intact

Draft bills proposed a sunset; the enacted OBBBA preserved both. New restriction:
**§70512(h)** prohibits transfer of §45Q/45X/45Y/45Z/48E credits to a **specified
foreign entity** (§7701(a)(51)(B)), for taxable years beginning after 2025-07-04
— first tested **2026-01-01** for a calendar-year taxpayer.

Market shape (Crux, SPEC §2.2): transfer market **$32bn (2024) → $42bn (2025),
+48%**; total monetisation $63bn in 2025. ITC gross value split **partnerships
57% / direct transfer 28% / preferred equity 15%**; PTCs **>90% direct transfer**.

### 7. Depreciation and the rule outsiders get wrong

**§50(c)(3): depreciable basis = eligible cost − 0.5 × ITC.** A $100m project
taking a 30% ITC depreciates $85m. MACRS 5/15 (Pub. 946 Table A-1), straight line
5/15/20/39, and §168(k) bonus at a caller-supplied rate on the reduced basis.

---

## Module map

| Module | Contains |
|---|---|
| `constants.py` | **Every number**, with authority and confidence. No magic numbers live anywhere else. |
| `enums.py` | Technology, credit type, eligibility path, BOC method, litigation status, confidence. |
| `models.py` | `TaxProject`, `TaxScenario`, and all result dataclasses. Frozen, self-contained. |
| `citations.py` | The structured registry. `get_all_citations()` feeds `/current-law`. |
| `eligibility.py` | §48E/§45Y paths, PWA, adder stacking, phase-down. |
| `adders.py` | Domestic content threshold schedule; energy community (asserted). |
| `feoc.py` | MACR computation, thresholds, pass/fail; §70512(h) test. |
| `begin_construction.py` | 5% SH vs Physical Work Test, continuity, the vacatur toggle. |
| `depreciation.py` | MACRS/SL/bonus + §50(c)(3). |
| `transfer.py` | §6418 economics, §6417 direct pay eligibility. |
| `UNVERIFIED.md` | Every rule this package is not certain about. **Read it.** |

`engine/tax` imports nothing from the rest of `engine` — stdlib only. It can be
lifted into the `/current-law` page, the narrator or a separate service without
dragging the sculpting spine along.

---

## Usage

```python
from datetime import date
from engine.tax import (
    TaxProject, TaxScenario, Technology, Notice202542Status,
    BeginConstructionMethod, ForeignEntityFlags, MacrInputs, MacrMethod,
    compute_tax,
)

project = TaxProject(
    technology=Technology.STORAGE,
    capacity_mw=100.0,
    capex=200_000_000.0,
    placed_in_service_date=date(2028, 6, 30),
    begin_construction_date=date(2026, 3, 1),
    begin_construction_method=BeginConstructionMethod.PHYSICAL_WORK_TEST,
    physical_work_commenced=True,
    is_pwa_compliant=True,
    domestic_content_pct=0.55,
    macr_inputs=MacrInputs(method=MacrMethod.USER_ASSERTED, asserted_ratio=0.70),
)

result = compute_tax(project)
print(f"{result.credit.final_rate:.0%}  ${result.credit.credit_amount:,.0f}")
for step in result.steps:          # the audit trail the narrator renders
    print(" -", step)
```

Scenario comparison — the differentiating feature:

```python
current  = compute_tax(project, TaxScenario())
on_appeal = compute_tax(project, TaxScenario(
    notice_2025_42_status=Notice202542Status.REINSTATED_ON_APPEAL))
```

Every result object carries `steps` (ordered `DeterminationStep`s) and
`citation_ids`. The narrator (SPEC §6.6) renders those and **never computes**.

---

## When the law changes — the update runbook

This is the process that keeps the moat. Follow it in order; each step is
enforced by a test.

1. **`citations.py` first.** Add or amend the `Citation`. Set `authority`,
   `plain_english`, `source`, `verified_on` and `confidence`. Never edit a rule
   without touching its citation — a rule whose citation still says 2026-08-06
   while the rule has moved is worse than no citation.
2. **`constants.py` second.** Change the number. If you cannot source it, make it
   a `PLACEHOLDER_`-prefixed constant and give the lookup an
   `is_placeholder` signal. **Do not invent a threshold.**
3. **`UNVERIFIED.md` third**, if confidence is not `VERIFIED`.
   `tests/test_tax_citations.py::test_every_uncertain_rule_is_disclosed_in_unverified_md`
   fails otherwise.
4. **The rule module fourth.** Add the `DeterminationStep` that explains the new
   behaviour to a user, and attach the citation id to it.
5. **A test fifth.** SPEC §10.4: every rule in §2 has a test and a citation. If
   the change moves a boundary (a date, a threshold), test **both sides** of it —
   the whole package is boundary behaviour.
6. **Bump `LAW_VERIFIED_ON`** only when you have actually re-checked every
   `VERIFIED` rule, not just the one you touched. The date is a claim.

### Items most likely to move next

* **The appeal in *Oregon Environmental Council*.** If the D.C. Circuit stays or
  reverses, the default `TaxScenario.notice_2025_42_status` flips to
  `REINSTATED_ON_APPEAL` and a large volume of safe-harboured wind/solar loses
  eligibility. The toggle already exists; only the default changes.
* **Final FEOC guidance** superseding Notice 2026-15, and the statutory MACR
  tables (see `UNVERIFIED.md` item 1 — the largest known gap).
* **The annual §45Y(c) inflation adjustment**, which currently makes
  `ptc_rate_per_kwh()` raise for any year after 2022.

---

## Tests

```bash
.venv/bin/pytest tests/test_tax_*.py -q
```

| File | Covers |
|---|---|
| `test_tax_eligibility.py` | The three headline wind/solar cases, storage phase-down, PWA 30% vs 6%, PTC. |
| `test_tax_adders.py` | The 49% / 50% domestic content boundary in 2026. |
| `test_tax_feoc.py` | MACR boundary, failure killing eligibility, §70512(h). |
| `test_tax_begin_construction.py` | The litigation toggle flipping a wind project. |
| `test_tax_depreciation.py` | `basis = capex − 0.5 × ITC`, recovery tables, bonus. |
| `test_tax_transfer.py` | Transfer economics, foreign-entity block, direct pay. |
| `test_tax_citations.py` | Registry completeness and disclosure of every uncertain rule. |

---

## Not advice

Illustrative modelling tool. Not tax, legal, accounting or investment advice
(SPEC §4.4). Public sources only; no real transaction's assumptions and no
employer data appear anywhere in this package (SPEC §4.5).
