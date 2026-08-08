# Structura — API contract (frozen 2026-08-07)

Both the Next.js frontend and the Python serverless layer build against THIS. Do not change it unilaterally; if something is genuinely wrong, report it rather than diverging.

Runtime: **Next.js (JS) frontend on Vercel** + **Python serverless functions** under `api/`.
Vercel limits that matter: Hobby function duration **300 s max**, bundle 500 MB, **4.5 MB request/response body cap** (stream/limit big payloads).

---

## POST `/api/compare`

Runs a project through all five structures.

**Request**
```json
{
  "deal_key": "storage_bess_contracted",      // optional: load a reference deal
  "overrides": {                                // optional, all fields optional
    "capex": 140000000,
    "opex_year1": 3500000,
    "production_p50": 200000,
    "contracted_price": 95.0,
    "contract_years": 15,
    "project_life_years": 20,
    "target_dscr": 1.20,
    "interest_rate": 0.062,
    "tenor_years": 18,
    "technology": "STORAGE",                    // STORAGE|SOLAR|WIND|DATA_CENTER
    "begin_construction_date": "2026-03-01",
    "placed_in_service_date": "2027-01-01",
    "is_pwa_compliant": true,
    "domestic_content_pct": 0.55,
    "energy_community": false,
    "macr_ratio": 0.80,
    "bonus_rate": 0.0,
    "notice_2025_42_status": "vacated"          // vacated | reinstated_on_appeal
  }
}
```

**Response 200**
```json
{
  "deal": { "key": "...", "name": "...", "summary": "...", "capex": 140000000 },
  "headline": "Partnership flip: sponsor after-tax IRR 14.85% ...",
  "law_verified_on": "2026-08-06",
  "ranked": [
    {
      "rank": 1,
      "key": "partnership_flip",
      "label": "Partnership flip",
      "feasible": true,
      "infeasible_reason": null,
      "sponsor_after_tax_irr": 0.1485,
      "irr_is_meaningful": true,
      "irr_not_meaningful_reason": null,
      "sponsor_npv": 27500000,
      "effective_cost_of_capital": 0.0803,
      "sponsor_equity_required": 27875518,
      "third_party_capital_raised": 119000000,
      "total_capital_raised": 147000000,
      "flip_year": 6.4,
      "credit_transferred": 0,
      "credit_retained": 42000000,
      "cash_timing": { "cash_weighted_average_years": 12.1, "share_by_year_5": 0.19 },
      "risks": [ { "code": "...", "severity": "BLOCKING|HIGH|MEDIUM|LOW", "message": "..." } ],
      "warnings": ["..."]
    }
  ],
  "why_this_wins": {
    "winner": "partnership_flip",
    "primary_metric": "sponsor_after_tax_irr",
    "winner_value": 0.1485,
    "runner_up": "t_flip",
    "runner_up_value": 0.1401,
    "margin": 0.0084,
    "drivers": [ { "name": "...", "unit": "...", "winner_value": 0, "runner_up_value": 0, "delta": 0, "higher_is_better": true, "note": "..." } ],
    "disqualified": [], "tie_breaks": [], "caveats": []
  },
  "sources_and_uses": { "funding_requirement": 147000000, "debt": 0, "third_party_equity": 0, "sponsor_equity": 0, "post_cod_monetisation": 0 },
  "debt": { "quantum": 0, "gearing": 0, "min_dscr": 0, "binding_constraint": "DSCR", "llcr": 0, "plcr": 0 },
  "tax": { "credit_section": "48E", "credit_rate": 0.30, "credit_value": 42000000, "eligibility_path": "...", "feoc_pass": true, "adders": ["domestic_content"], "warnings": ["..."] },
  "capital_account_breaches": [],
  "warnings": ["engine.tax: The MACR threshold applied is a PLACEHOLDER ..."],
  "compute_ms": 850
}
```

**Errors**: `400` `{ "error": "message", "field": "capex" }` for validation; `500` `{ "error": "..." }`. Never leak stack traces.

---

## POST `/api/export`

Generates the lender-grade Excel workbook.

**Request**: same shape as `/api/compare`, plus optional `"structure": "partnership_flip"`.
**Response**: `200` with `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `Content-Disposition: attachment; filename="structura-<deal>-<date>.xlsx"`, raw bytes.
⚠️ The sample workbook is ~55 KB, well under the 4.5 MB cap. If a generated file would exceed 4 MB, return `413` with a JSON error rather than truncating.

---

## GET `/api/reference-deals`

```json
{ "deals": [ { "key": "storage_bess_contracted", "name": "...", "summary": "...", "capex": 140000000, "technology": "STORAGE", "dscr_benchmark": "1.15–1.20x (NRF Jan 2026)" } ] }
```

---

## GET `/api/current-law`

Renders the citation registry for the `/current-law` page.

```json
{
  "law_verified_on": "2026-08-06",
  "citations": [
    { "id": "section-48e", "authority": "IRC §48E", "summary": "...", "source": "...", "verified_on": "2026-08-06", "confidence": "HIGH|MEDIUM|PLACEHOLDER" }
  ],
  "unverified": [ { "item": "MACR threshold table", "detail": "Only solar CY2026 (≥50%) is sourced ...", "impact": "..." } ],
  "litigation": {
    "case": "Oregon Environmental Council v. IRS, No. 25-4400 (CKK)",
    "decided": "2026-06-06",
    "effect": "Notice 2025-42 vacated in full; 5% safe harbor restored",
    "status": "appeal expected",
    "toggle_values": ["vacated", "reinstated_on_appeal"]
  }
}
```

---

## Conventions

- All rates are **decimals** (0.1485 = 14.85%); all money is **USD floats**; all dates are **ISO `YYYY-MM-DD`**.
- `irr_is_meaningful: false` → the UI **must not** display the IRR as a headline number. Show the reason and lead with `sponsor_npv`.
- Every `warnings` string is displayed verbatim somewhere reachable — placeholders must never be silently swallowed.
- `risks` with `severity: "BLOCKING"` render prominently (red), not in a collapsed list.
