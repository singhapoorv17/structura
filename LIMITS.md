# Limitations

This is an illustrative modelling tool. It is not tax, legal, accounting or investment advice, and should not be relied on for a transaction.

---

## Unsourced values

The following are labelled placeholders rather than sourced figures. Each one raises a warning on any result that consumes it.

| Item | Status |
|---|---|
| MACR threshold table | Only solar / CY2026 (≥50%) is sourced from Notice 2026-15. Other technology-year cells are structural stand-ins; each lookup returns `threshold_is_placeholder`. |
| §45Y inflation factors | Only 2022 is implemented. `ptc_rate_per_kwh()` raises for later years rather than returning an estimate. |
| Notice 2025-08 assigned cost percentages | Not implemented; electing that safe harbor raises. |
| Tax-equity target yield, price per credit dollar, maximum investor share | No public source prices tax equity. |
| Preferred coupon and term, lessor target yield, sale-leaseback residual | No public source prices leases or preferred equity. The residual sits at the Rev. Proc. 2001-28 guideline floor. |
| IRR-meaningfulness thresholds | Reporting guards chosen for this tool, not market data. They affect which figures are displayed, not any computed value. |

## Partnership tax

Implemented: capital accounts under Reg. §1.704-1(b)(2)(iv), the alternate economic-effect test, DRO caps with pro-rata reallocation to capacity, outside basis under §705 with §752 tiers 1 and 3, the §704(d) limitation with indefinite FIFO carryforward, §731(a)(1) gain, and the §50(c)(3)/(c)(5) basis reduction.

Simplified or omitted:

- Minimum gain chargeback is pooled rather than property-by-property. No §1.704-2(f)(2)–(5) exceptions and no partner-nonrecourse-debt minimum gain.
- No §704(c). Ledgers are kept separate but no layer is computed.
- No qualified income offset. A distribution-driven deficit is reported as a structured warning rather than cured, which is why a capital-account breach can appear on aggressive configurations.
- No §465 at-risk or §469 passive-activity limits.
- No HLBV, revaluations or liquidating distribution.
- No PAYGO, back-leverage, sponsor call option, or simulated §50(a) recapture.

## Engine

- The ITC bridge loan is not modelled. `credit_proceeds_at_cod` is always zero, which makes the funding constraint conservative rather than exact. Market bridges advance approximately 98% at SOFR+150.
- One senior tranche. No default or acceleration mechanics. The maintenance reserve is exogenous.
- Nominal-annual interest convention; no seasonality within sub-annual periods.
- Project-level tax is federal straight-line only. The default treatment is pre-tax CFADS, following US renewable sizing convention.
- A facility constrained by gearing, LLCR or tail is sized by pro-rata scaling of the service profile rather than by shortening tenor.
- Equity is treated as a single COD outflow for IRR purposes. Lock-up is modelled as a 100% sweep.

## Excel export

One cell is solver-derived rather than a live formula: the applied grace period, which is determined by search rather than expression. It is highlighted and documented on the Notes sheet.

Six differences between the workbook and the Python engine are documented on the Notes sheet: display materiality floors, grid width fixed at generation, DSRA lookahead depth fixed at generation, a zero-month construction edge case, pre-tax equity IRR omitted, and payback text where the engine returns null. None affects any tested case.

## Scope

US federal tax only. No state tax, no ITC recapture simulation, no construction-period risk modelling, and no merchant price forecasting. PPA prices are user-supplied; no free source publishes them, so ATB LCOE is used only as a sanity anchor.
