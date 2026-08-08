# Structura — deploy

Single Vercel project: Next.js frontend + Python serverless functions in `api/`.

## Measured facts (2026-08-07, verified not estimated)

| Constraint | Vercel limit | Structura | Headroom |
|---|---|---|---|
| Python bundle | 500 MB | **~137 MB** deps (scipy 99, numpy 34, openpyxl 2.8, pyxirr 1.0) + CPython/app | comfortable |
| Function duration | 300 s (Hobby) | **5–24 ms** per `/api/compare` | ~4 orders of magnitude |
| Response body | 4.5 MB | **11–17 KB** JSON; **~55 KB** xlsx | comfortable |

`/api/compare` timings by reference deal: storage 15 ms · solar 24 ms · data-centre 5 ms.
**No Fly.io/Render escape hatch needed** — the spec's fallback is not required.

## Env vars

**None required.** The engine is assumption-driven; there is no database, no auth, no external API in the core path. If a narrator/LLM layer is added later it gets its own optional key and must degrade gracefully when absent.

## Deploy

```bash
# from builds/structura/app
vercel            # preview
vercel --prod     # production
```

Or import the GitHub repo at vercel.com/new (framework auto-detects Next.js; leave build/output defaults). Push-to-`main` then auto-deploys.

`vercel.json` already declares:
- `functions."api/**/*.py"` with `maxDuration: 60` and an `excludeFiles` glob that keeps `.venv`, `node_modules`, `.next`, `tests`, `samples` and `__pycache__` out of the bundle (this is what keeps it at ~137 MB).
- Rewrites mapping the hyphenated public routes to the underscored Python filenames: `/api/reference-deals` → `/api/reference_deals`, `/api/current-law` → `/api/current_law`.

## Post-deploy verification

1. `/` loads, a reference deal renders the five-structure comparison.
2. `POST /api/compare` with `{"deal_key":"storage_bess_contracted"}` returns rank 1 = `partnership_flip`, IRR ≈ 0.1485.
3. The sale-leaseback row shows its IRR **suppressed as not meaningful** — if a 41% IRR is displayed as a headline number, the meaningfulness guard is not wired through and that is a release blocker.
4. `/api/export` downloads a workbook; open it and change `Target_DSCR` on Inputs — the model must recalculate.
5. `/current-law` renders the citation registry, the placeholder list, and the litigation toggle explanation.
6. Every PLACEHOLDER warning is visible somewhere in the UI (MACR threshold, tax-equity pricing, lease pricing).

## Cold starts

Python functions with scipy/numpy cold-start slower than the 5–24 ms warm compute. Expect a noticeably slower first request after idle. Acceptable for a portfolio tool; if it becomes annoying, the fix is a lightweight warming ping, not an architecture change.

## Repo hygiene

Public repo — all sources are public data and the engine is the artifact. `.gitignore` covers `node_modules/`, `.next/`, `.venv/`, `__pycache__/`, `.vercel`. No secrets exist in this project; if that ever changes, they go in Vercel env vars and never in git.
