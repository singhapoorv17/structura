# LIMITS — what Structura does not claim

Stating limitations plainly is a design requirement, not a disclaimer exercise. A practitioner who finds an undeclared simplification stops trusting everything else in the tool.

**This is an illustrative modelling tool. It is not tax, legal, accounting or investment advice.** Do not rely on it for a transaction. Every real deal needs tax counsel.

---

## 1. Unsourced values (they flag themselves in the product)

These are labelled placeholders, not findings. Each one surfaces as a warning attached to any result that consumed it.

| Item | Status | Where |
|---|---|---|
| **MACR threshold table** | Only **solar / CY2026 (≥50%)** is sourced from Notice 2026-15. Every other technology-year cell is a structural stand-in. Each lookup returns `threshold_is_placeholder`. | `engine/tax/UNVERIFIED.md` |
| **§45Y inflation factors** | Only 2022 ships. `ptc_rate_per_kwh()` **raises** for later years rather than guessing a number. | `engine/tax/UNVERIFIED.md` |
| **Notice 2025-08 assigned cost percentages** | Not shipped; electing that safe harbor raises. | `engine/tax/UNVERIFIED.md` |
| **Tax-equity target yield, $/credit-$, max investor share** | No public source prices tax equity. Labelled benchmarks. | `engine/structures/LIMITS_STRUCTURES.md` |
| **Preferred coupon/term, lessor target yield, SLB residual** | No public source prices leases or preferred. Residual sits at the Rev. Proc. 2001-28 guideline floor. | `engine/structures/LIMITS_STRUCTURES.md` |
| **IRR-meaningfulness thresholds** | Structura's own **reporting guards**, not market data. They change no computed number — only what the tool refuses to headline. | `engine/structures/defaults.py` |

## 2. Partnership tax simplifications (declared)

Implemented in full: capital accounts (Reg. §1.704-1(b)(2)(iv)), the alternate economic-effect test, DRO caps with pro-rata reallocation to capacity, outside basis (§705) with §752 tiers 1 and 3, §704(d) limitation with indefinite FIFO carryforward, §731(a)(1) gain, and the §50(c)(3)/(c)(5) basis reduction.

Simplified or omitted, and why it matters:
- **Minimum gain chargeback** is pooled rather than property-by-property; no §1.704-2(f)(2)–(5) exceptions; no partner-nonrecourse-debt minimum gain.
- **No §704(c)** — ledgers are kept separate but no layer is computed.
- **No qualified income offset.** A distribution-driven deficit is *reported as a structured warning*, not cured. This is why a capital-account breach can appear on aggressive configurations.
- No §465 at-risk or §469 passive-activity limits; no HLBV, revaluations or liquidating distribution.
- No PAYGO, back-leverage, sponsor call option, or simulated §50(a) recapture event.

## 3. Structural / engine simplifications

- **The ITC bridge loan is not modelled.** `credit_proceeds_at_cod` is always zero, which makes the funding constraint conservative rather than exact. Real bridges advance ~98% at SOFR+150 (NRF).
- One senior tranche; no default or acceleration mechanics; MRA exogenous.
- Nominal-annual interest convention; no seasonality within sub-annual periods.
- Project-level tax is federal straight-line only; the default `TaxTreatment.NONE` (pre-tax CFADS) follows the US renewable sizing convention.
- A gearing/LLCR/tail-constrained facility is sized by pro-rata scaling of the service profile rather than by shortening tenor.
- Equity is treated as a single COD outflow for IRR purposes; lock-up is modelled as a 100% sweep.

## 4. Excel export

- Exactly **one** cell is solver-derived rather than a live formula: the applied grace period (a search, not an expression). It is amber-filled and documented on the Notes sheet; a test fails if a second appears.
- Six declared divergences from the Python engine are listed in `PHASE4.md` and on the Notes sheet (display materiality floors, grid width fixed at generation, DSRA lookahead depth fixed at generation, a zero-month construction edge case, pre-tax equity IRR omitted, and payback text where the engine returns null). None affects any tested case.

## 5. Scope

US federal only. No state tax, no ITC recapture simulation, no construction-period risk modelling, no merchant price forecasting (bring your own price), and no PPA price discovery — LevelTen's index is subscriber-only, so ATB LCOE is used as a sanity anchor rather than a price source.

---

If you find something wrong, that is a useful bug report — the citation registry and test suite exist precisely so a claim can be checked rather than trusted.
