# `engine/` — the Structura core spine

Pure Python. No web framework, no Excel, no network, no I/O. The web app and the
`.xlsx` exporter are thin shells over this package, and both are later phases.

This is **Phase 1** of SPEC.md: debt sizing, sculpting, reserves, the funding
circularity and the cash waterfall. Tax structures (`engine/tax/`), the
partnership mechanics and the five-structure selector are Phases 2–3.

---

## Module map

| Module | Responsibility |
|---|---|
| `models.py` | Frozen dataclasses for every input and output. No logic beyond validation and derived properties. |
| `defaults.py` | Market benchmarks (DSCR by technology, debt pricing, gearing, DSRA, fees) — each one a `Benchmark` carrying `source` and `verified_on`. Also every numeric tolerance in the engine. **No magic numbers live anywhere else.** |
| `cashflow.py` | Revenue → opex → EBITDA → cash tax → **CFADS**. Knows nothing about debt. |
| `debt.py` | The core: sculpting, level payment, fixed principal, DSCR/LLCR/PLCR, DSRA sizing, and `size_facility` — which runs every credit test and reports **which one binds**. |
| `circularity.py` | The IDC ↔ debt size ↔ fees ↔ DSRA fixed point, solved with `scipy.optimize.brentq` on an explicit two-level iteration schedule. |
| `waterfall.py` | The priority of payments, with **cash conservation asserted every period**. |
| `metrics.py` | IRR / XIRR / NPV / payback / effective cost of debt / WACC, via `pyxirr`. |

Dependency direction is strictly one-way:

```
defaults -> models -> cashflow -> debt -> circularity -> waterfall -> metrics
```

---

## The sculpting math

Let `C_t` be CFADS in period *t*, `d_t` the target DSCR, `r` the per-period
interest rate, `N` the number of debt periods and `g` the grace period.

**1. Available debt service.** The most the deal can pay while still covering
its target:

```
DS_t = C_t / d_t                       for t = g+1 .. N
DS_t = r · D                           for t = 1 .. g   (interest only)
```

**2. Debt quantum is the present value of that service at the debt rate:**

```
        N
D  =   SUM   DS_t · (1 + r)^-(t-g)
      t=g+1
```

Note the discount exponent is `t - g`, not `t`: during grace the balance is
still `D`, so the PV is taken back only as far as the end of the grace period.

**3. Split the service into interest and principal off the actual balance:**

```
I_t = r · B_(t-1)
P_t = DS_t - I_t
B_t = B_(t-1) - P_t          with B_0 = D
```

**Why step 2 makes step 3 land on zero.** The balance recursion is
`B_t = B_(t-1)·(1+r) - DS_t`, so unrolling it:

```
B_N = D·(1+r)^N - SUM_t DS_t·(1+r)^(N-t)
```

which is zero exactly when `D` is the PV in step 2. So **the debt size is the
present value of the sculpted debt service at the debt rate** — one line, no
iteration. That identity is the whole trick, and it is why a sculpting engine
does not need a solver even though a project-finance *model* does.

### Two constraints on top of the identity

**Grace-period interest coverage.** During grace the service is `r·D`, which
must still clear the target: `r·D ≤ min(C_t / d_t)` over the grace periods. If
it does not, the quantum is capped at `min(C_t/d_t)/r` and the post-grace
service is scaled down pro rata. Scaling is exact because every style's service
profile is homogeneous of degree one in `D` (including `r·D`), so one scalar
rescales the whole profile and the PV identity still holds.

**Non-negative amortisation.** A steeply ramping CFADS profile at a high rate
can produce `DS_1 < r·D` — principal going backwards. The arithmetic allows it;
no term facility does. `effective_grace_periods()` lengthens the interest-only
holiday one period at a time until every period amortises non-negatively. This
is deterministic and terminates in at most `N-1` steps. It costs debt capacity,
which is the correct economic answer.

### The alternatives

**Level payment.** A constant payment `A` must clear the target in *every*
amortising period, so it is set by the tightest one:

```
A = min_t (C_t / d_t)
D = A · [1 - (1+r)^-(N-g)] / r
```

Every period other than the binding one goes over-covered. That unused coverage
is exactly what sculpting monetises.

**Fixed principal.** With `m = N - g` amortising periods, principal is `D/m`
and the service in amortising period *k* is:

```
DS_k = D · [ 1/m + r·(1 - (k-1)/m) ] = D · f_k
D    = min_k  (C_k / d_k) / f_k
```

**Ranking.** Sculpted ≥ level and sculpted ≥ fixed principal, always. The
ranking *between* level and fixed principal is not universal: fixed principal
wins against a declining CFADS profile, because a declining service schedule
tracks declining cash better than a flat one. Both directions are asserted in
`tests/test_properties.py`.

---

## The coverage ratios, and why each uses the discount rate it does

**DSCR** — `C_t / DS_t`. A flow test. Says nothing about tomorrow.

**LLCR** — PV of CFADS to loan maturity, discounted at the **debt rate**,
over debt outstanding:

```
LLCR = [ SUM_(t=1..N) C_t·(1+r)^-t  +  reserves ] / D
```

The debt rate is the right discount rate because the denominator is a balance
that compounds at `r`. Discounting the numerator at anything else compares two
different currencies. An LLCR of 1.40x means the cash the loan can reach,
valued the way the loan is valued, is 1.4× the loan.

A useful identity falls straight out and is asserted in the tests: **for a deal
sculpted to a constant target `d`, LLCR = `d` exactly**, because
`C_t = d·DS_t` in every period so `PV(C) = d·PV(DS) = d·D`. If a model's LLCR
does not equal its flat sculpting target, the sculpt is not hitting target.

**PLCR** — the same calculation with the CFADS horizon extended to the **full
project life** rather than loan maturity. `PLCR ≥ LLCR` always, and the gap is
the PV of the tail divided by the debt: the residual value a lender could
restructure into. It is the reason lenders require a tail at all.

---

## The circularity, and how it is solved

Total project cost is an output, not an input:

```
TPC = capex + upfront fee + commitment fee + IDC + initial DSRA
D   = min( D_DSCR , max_gearing · TPC )
```

Every term after `capex` depends on `D`, and `D` depends on `TPC`. In Excel this
is what iterative calculation is for (`iterate="1"`, SPEC §5 — the reason the
stack is `openpyxl`). Here it is solved numerically so the Python model never
depends on Excel's solver, and Phase 4 asserts the two agree.

**Inner solve — the drawdown.** For a trial facility `D`, let `X` be the
debt-funded capex. Simulating the construction period month by month gives a
closing balance `B(X; D)` that is strictly increasing and continuous in `X`.
Brent's method on `[0, D]` finds `X` with `B(X; D) = D`, which yields IDC, the
commitment fee and the monthly draw schedule.

**Outer solve — the facility.** Define
`f(D) = min(D_DSCR, max_gearing·TPC(D)) - D`. `TPC` increases in `D` but with
slope far below `1/max_gearing` at any realistic rate, so `f` is continuous and
strictly decreasing and has exactly one root. `f(0) > 0`; if
`f(D_DSCR) > 0` the gearing cap is slack and `D = D_DSCR` outright with no
iteration. Otherwise `[0, D_DSCR]` brackets the root.

**Tax loop.** With `TaxTreatment.FULL`, cash tax deducts interest, so CFADS
depends on the debt schedule which depends on CFADS. Resolved as a fixed-point
iteration on the interest series, to the same tolerance, with the iteration
count reported and a hard failure if it does not converge.

**Conventions.** Draws land at the start of the month and interest accrues on
the post-draw balance (the lender's convention; a mid-month convention would
understate IDC by roughly half a month). IDC and the commitment fee are
capitalised. The upfront fee is drawn at first utilisation and financed by the
facility. The initial DSRA is funded at COD and accrues no IDC.

Determinism: Brent on a fixed bracket at a fixed tolerance produces
bit-identical reruns. Asserted in `tests/test_circularity.py`.

---

## The waterfall

Senior to junior, in credit-agreement order:

1. CFADS (revenue − opex − cash tax)
2. Senior **interest**, then senior **scheduled principal**
3. **DSRA** — drawn *up* the waterfall to cure a shortfall, topped back up
   here, excess over target released
4. **MRA** — exogenous in Phase 1
5. **Cash sweep** — a percentage of surplus prepays senior debt, applied in
   **inverse order of maturity** (retires the back end, preserving the
   near-term profile the deal was sculpted to)
6. **Lock-up test** — below the lock-up DSCR, nothing leaves the project
7. **Subordinated / back-leverage**, then **distributions to equity**

`assert_cash_conservation` checks, for every period:

```
CFADS + DSRA release + MRA release
   == interest + principal + sweep + DSRA deposit + MRA deposit
      + subordinated service + distributions
```

It runs automatically inside `run_waterfall`. A waterfall that does not conserve
cash is not a waterfall; it is a spreadsheet with a plug.

---

## Sizing tests and binding-constraint reporting

`size_facility()` evaluates all six tests and reports which one actually set the
debt:

| Test | Quantum it implies |
|---|---|
| DSCR | the sculpt / level / fixed-principal solve at the requested tenor |
| Gearing | `max_gearing × TPC` |
| Tail | the solve at the tail-compliant (shortened) tenor |
| LLCR | `PV(CFADS to maturity) / min_LLCR` |
| PLCR | `PV(CFADS to project end) / min_PLCR` |
| Tenor | reporting only — flags when the tail shortened the request |

The binder is the minimum. Ties break toward DSCR, because a deal sitting on
both its DSCR and its gearing limit is described by practitioners as DSCR-bound.

```python
>>> solution.sizing.summary()
'Debt is GEARING-bound at 0.75 ($162.8m). achieved min DSCR 1.614x against a
 1.300x target; tail 7y vs 2y required; LLCR 1.614x; PLCR 1.818x.'
```

---

## Quick start

```python
from engine import ProjectInputs, DebtTerms, run_model

solution, waterfall, returns = run_model(ProjectInputs(), DebtTerms())

print(solution.sizing.summary())
print(f"IDC ${solution.construction.idc/1e6:,.1f}m")
print(f"Equity IRR {returns.equity_irr_post_tax:.2%}")
```

Each step is available piecewise — `build_cashflow`, `size_facility`,
`solve_funding`, `run_waterfall`, `compute_returns` — and nothing is hidden
inside `run_model`.
