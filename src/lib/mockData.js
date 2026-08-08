/**
 * Local mock of the API response shape.
 *
 * Every figure below is taken from the engine's own output for the reference
 * deals in `engine/reference_deals.py`: the same refused sale-leaseback IRR,
 * the same gearing-bound results, the same placeholder warnings.
 *
 * This exists so the UI renders when the Python serverless layer is
 * unreachable. `lib/api.js` prefers the real endpoints and falls back here.
 */

export const LAW_VERIFIED_ON = '2026-08-06';

export const MOCK_REFERENCE_DEALS = [
  {
    key: 'storage_bess_contracted',
    name: '100 MW / 400 MWh BESS, contracted toll, post-OBBBA §48E',
    summary:
      'A four-hour lithium-ion battery on a fifteen-year tolling agreement, placed in service 2027. Standalone storage keeps full §48E on a begin-construction basis to 2033 (OBBBA), so unlike solar and wind this is forward pipeline rather than safe-harboured inventory.',
    capex: 140000000,
    technology: 'STORAGE',
    dscr_benchmark: '1.15–1.20x (NRF Jan 2026)',
  },
  {
    key: 'solar_safe_harboured',
    name: '150 MWac solar PV, safe-harboured before the 2026-07-04 cliff',
    summary:
      'A utility-scale PV project that began construction on 2026-03-01 — before the OBBBA begin-construction cliff — and is placed in service in 2028, inside the four-year continuity window. A project that missed the cliff must be in service by 2027-12-31 or receive nothing.',
    capex: 180000000,
    technology: 'SOLAR',
    dscr_benchmark: '1.25–1.30x (NRF Jan 2026)',
  },
  {
    key: 'data_center_powered_shell',
    name: '48 MW data-centre powered shell, 15-year hyperscaler lease',
    summary:
      'A powered shell on a fifteen-year triple-net lease to an investment-grade hyperscaler. NRF publishes DSCR of 1.05–1.15x and pricing of SOFR+250 to 425 for the asset class. No §48E credit attaches to a shell, so the direct transfer and the T-flip are disqualified by the credit gate.',
    capex: 510000000,
    technology: 'DATA_CENTER',
    dscr_benchmark: '1.05–1.15x (NRF Jan 2026)',
  },
];

/** Default input set per reference deal — mirrors engine/reference_deals.py. */
export const MOCK_DEAL_INPUTS = {
  storage_bess_contracted: {
    capex: 140000000,
    opex_year1: 3500000,
    production_p50: 1,
    contracted_price: 21500000,
    contract_years: 15,
    project_life_years: 20,
    target_dscr: 1.2,
    interest_rate: 0.062,
    tenor_years: 18,
    technology: 'STORAGE',
    begin_construction_date: '2026-03-01',
    placed_in_service_date: '2027-01-01',
    is_pwa_compliant: true,
    domestic_content_pct: 0.55,
    energy_community: false,
    macr_ratio: 0.8,
    bonus_rate: 0.0,
    notice_2025_42_status: 'vacated',
  },
  solar_safe_harboured: {
    capex: 180000000,
    opex_year1: 2700000,
    production_p50: 330000,
    contracted_price: 48.0,
    contract_years: 20,
    project_life_years: 30,
    target_dscr: 1.3,
    interest_rate: 0.06,
    tenor_years: 18,
    technology: 'SOLAR',
    begin_construction_date: '2026-03-01',
    placed_in_service_date: '2028-01-01',
    is_pwa_compliant: true,
    domestic_content_pct: 0.52,
    energy_community: false,
    macr_ratio: 0.62,
    bonus_rate: 0.0,
    notice_2025_42_status: 'vacated',
  },
  data_center_powered_shell: {
    capex: 510000000,
    opex_year1: 6000000,
    production_p50: 1,
    contracted_price: 62000000,
    contract_years: 15,
    project_life_years: 25,
    target_dscr: 1.15,
    interest_rate: 0.071,
    tenor_years: 15,
    technology: 'DATA_CENTER',
    begin_construction_date: '2026-01-01',
    placed_in_service_date: '2028-01-01',
    is_pwa_compliant: false,
    domestic_content_pct: 0.0,
    energy_community: false,
    macr_ratio: 0.0,
    bonus_rate: 0.0,
    notice_2025_42_status: 'vacated',
  },
};

const STRUCTURE_LABELS = {
  partnership_flip: 'Partnership flip',
  t_flip: 'T-flip (flip + §6418 transfer)',
  preferred_equity: 'Preferred equity partnership',
  direct_transfer: 'Direct transfer (§6418)',
  sale_leaseback: 'Sale-leaseback',
};

/** Calibrated base cases, as printed by the engine for each reference deal. */
const BASE = {
  storage_bess_contracted: {
    funding_requirement: 147046397,
    debt: {
      quantum: 66170879,
      gearing: 0.45,
      min_dscr: 2.09,
      binding_constraint: 'GEARING',
      llcr: 2.41,
      plcr: 2.68,
    },
    tax: {
      credit_section: '48E',
      credit_rate: 0.3,
      credit_value: 42000000,
      eligibility_path:
        'Standalone storage — untouched by the OBBBA wind/solar cliff. Full §48E on begin-construction through 2033.',
      feoc_pass: true,
      adders: ['domestic_content'],
    },
    structures: [
      {
        key: 'partnership_flip',
        irr: 0.1485,
        coc: 0.0803,
        npv: 12200000,
        sponsor_equity: 27875518,
        third_party: 119170879,
        flip_year: 6.4,
        credit_retained: 42000000,
        credit_transferred: 0,
        post_cod: 0,
        cwa_years: 12.1,
        share_by_year_5: 0.19,
      },
      {
        key: 't_flip',
        irr: 0.1401,
        coc: 0.0704,
        npv: 12200000,
        sponsor_equity: 65876397,
        third_party: 81170000,
        flip_year: 8.1,
        credit_retained: 5000000,
        credit_transferred: 37000000,
        post_cod: 37000000,
        cwa_years: 10.4,
        share_by_year_5: 0.27,
      },
      {
        key: 'direct_transfer',
        irr: 0.1136,
        coc: 0.0684,
        npv: 4800000,
        sponsor_equity: 80875518,
        third_party: 66170879,
        flip_year: null,
        credit_retained: 0,
        credit_transferred: 42000000,
        post_cod: 37000000,
        cwa_years: 9.8,
        share_by_year_5: 0.31,
      },
      {
        key: 'preferred_equity',
        irr: 0.0331,
        coc: 0.1369,
        npv: -15300000,
        sponsor_equity: 32370000,
        third_party: 114676397,
        flip_year: null,
        credit_retained: 42000000,
        credit_transferred: 0,
        post_cod: 0,
        cwa_years: 14.2,
        share_by_year_5: 0.08,
      },
      {
        key: 'sale_leaseback',
        irr: 0.4132,
        coc: 0.098,
        npv: 19400000,
        sponsor_equity: 6975518,
        third_party: 66170879,
        flip_year: null,
        credit_retained: 0,
        credit_transferred: 0,
        post_cod: 140000000,
        cwa_years: 7.9,
        share_by_year_5: 0.42,
        irr_is_meaningful: false,
        irr_not_meaningful_reason:
          'Sponsor equity is 4.7% of the funding requirement, below the 10% de-minimis floor in engine/structures/defaults.py. The rate describes a $7.0m residual base, not the deal. Ranked on sponsor NPV instead.',
      },
    ],
  },

  solar_safe_harboured: {
    funding_requirement: 191000000,
    debt: {
      quantum: 105050000,
      gearing: 0.55,
      min_dscr: 1.45,
      binding_constraint: 'GEARING',
      llcr: 1.72,
      plcr: 1.94,
    },
    tax: {
      credit_section: '48E',
      credit_rate: 0.3,
      credit_value: 54000000,
      eligibility_path:
        'Wind/solar begin-construction cliff met — construction began 2026-03-01, on or before 2026-07-04. Four-year continuity window runs to 2030.',
      feoc_pass: true,
      adders: ['domestic_content'],
    },
    structures: [
      {
        key: 't_flip',
        irr: 0.1172,
        coc: 0.0731,
        npv: 15900000,
        sponsor_equity: 62480000,
        third_party: 128520000,
        flip_year: 7.8,
        credit_retained: 6500000,
        credit_transferred: 47500000,
        post_cod: 47500000,
        cwa_years: 11.6,
        share_by_year_5: 0.24,
      },
      {
        key: 'partnership_flip',
        irr: 0.101,
        coc: 0.0842,
        npv: 11400000,
        sponsor_equity: 34310000,
        third_party: 156690000,
        flip_year: 6.9,
        credit_retained: 54000000,
        credit_transferred: 0,
        post_cod: 0,
        cwa_years: 13.4,
        share_by_year_5: 0.16,
      },
      {
        key: 'direct_transfer',
        irr: 0.0824,
        coc: 0.0699,
        npv: 6100000,
        sponsor_equity: 85950000,
        third_party: 105050000,
        flip_year: null,
        credit_retained: 0,
        credit_transferred: 54000000,
        post_cod: 47500000,
        cwa_years: 10.9,
        share_by_year_5: 0.29,
      },
      {
        key: 'preferred_equity',
        irr: 0.0074,
        coc: 0.1418,
        npv: -21700000,
        sponsor_equity: 41900000,
        third_party: 149100000,
        flip_year: null,
        credit_retained: 54000000,
        credit_transferred: 0,
        post_cod: 0,
        cwa_years: 15.1,
        share_by_year_5: 0.07,
      },
      {
        key: 'sale_leaseback',
        irr: 0.189,
        coc: 0.1024,
        npv: 14200000,
        sponsor_equity: 12300000,
        third_party: 105050000,
        flip_year: null,
        credit_retained: 0,
        credit_transferred: 0,
        post_cod: 180000000,
        cwa_years: 8.6,
        share_by_year_5: 0.38,
        irr_is_meaningful: false,
        irr_not_meaningful_reason:
          'Sponsor equity is 6.4% of the funding requirement, below the 10% de-minimis floor. The sale returns most of the construction equity at closing, so the rate is computed over a residual base. Ranked on sponsor NPV instead.',
      },
    ],
  },

  data_center_powered_shell: {
    funding_requirement: 537000000,
    debt: {
      quantum: 402750000,
      gearing: 0.75,
      min_dscr: 1.33,
      binding_constraint: 'GEARING',
      llcr: 1.58,
      plcr: 1.81,
    },
    tax: {
      credit_section: null,
      credit_rate: 0,
      credit_value: 0,
      eligibility_path:
        'No §48E credit attaches to a powered shell. The asset is real property, not qualified energy property, so both credit-dependent structures fail the selector gate.',
      feoc_pass: true,
      adders: [],
    },
    structures: [
      {
        key: 'partnership_flip',
        irr: 0.151,
        coc: 0.0912,
        npv: 61300000,
        sponsor_equity: 96660000,
        third_party: 440340000,
        flip_year: 7.2,
        credit_retained: 0,
        credit_transferred: 0,
        post_cod: 0,
        cwa_years: 11.2,
        share_by_year_5: 0.22,
      },
      {
        key: 'preferred_equity',
        irr: 0.1194,
        coc: 0.1105,
        npv: 34800000,
        sponsor_equity: 80550000,
        third_party: 456450000,
        flip_year: null,
        credit_retained: 0,
        credit_transferred: 0,
        post_cod: 0,
        cwa_years: 12.8,
        share_by_year_5: 0.15,
      },
      {
        key: 'sale_leaseback',
        irr: 0.0986,
        coc: 0.1043,
        npv: 22400000,
        sponsor_equity: 134250000,
        third_party: 402750000,
        flip_year: null,
        credit_retained: 0,
        credit_transferred: 0,
        post_cod: 510000000,
        cwa_years: 9.4,
        share_by_year_5: 0.33,
      },
      {
        key: 'direct_transfer',
        feasible: false,
        infeasible_reason:
          'No transferable credit. §6418 permits the transfer of an eligible credit determined under §48E; a powered shell determines no such credit, so there is nothing to elect on.',
      },
      {
        key: 't_flip',
        feasible: false,
        infeasible_reason:
          'A T-flip is a partnership flip with a §6418 transfer bolted on. With no eligible credit the transfer leg is void and the structure collapses to a plain flip, which is ranked separately.',
      },
    ],
  },
};

/** Warnings the engine emits on every run — placeholders that must not be swallowed. */
const STANDING_WARNINGS = [
  'engine.tax: The MACR threshold applied is a PLACEHOLDER. Only the solar CY2026 cell (≥50%) is carried by the verified rulebook; every other technology/year cell escalates plausibly but is not authority. See engine/tax/UNVERIFIED.md §1.',
  'engine.structures: PLACEHOLDER_TE_TARGET_AFTER_TAX_IRR = 6.50% — the single most important input to a yield-based flip. Norton Rose Fulbright publishes debt pricing and DSCR but no tax-equity target yield. Override before relying on any output.',
  'engine.structures: PLACEHOLDER_PREFERRED_RETURN = 9.00% and PLACEHOLDER_PREFERRED_TARGET_TERM_YEARS = 10. Preferred pricing is quoted deal by deal and is not published.',
  'engine.structures: PLACEHOLDER_LESSOR_TARGET_AFTER_TAX_IRR = 7.00%; PLACEHOLDER_SALE_LEASEBACK_RESIDUAL_PCT = 20%, set at the Rev. Proc. 2001-28 guideline floor. A floor is not a forecast.',
  'engine.reference_deals: capex per kW, offtake pricing and every operating cost ship as placeholders. No free source of PPA or offtake prices exists (LevelTen is subscriber-only), so no revenue line here is sourced.',
  'engine.structures.selector: one debt sizing serves all five structures. A lender would size a sale-leaseback differently from a flip; re-sizing per structure would make the comparison meaningless, so the simplification is deliberate.',
  'engine.structures: no scenario sweep. This is a single P50 run — P90/P99, merchant share and rate shocks are not applied.',
  'engine.tax: §704(c), qualified income offset, §465 at-risk and §469 passive activity limitations are not modelled. Federal tax only; no state tax anywhere.',
];

const STANDING_RISKS = {
  partnership_flip: [
    {
      code: 'no_back_leverage',
      severity: 'MEDIUM',
      message:
        'Back-leverage at the sponsor holdco is not modelled. The deal is gearing-bound with DSCR headroom above the market floor; a real sponsor would take that headroom as holdco debt, which would raise this IRR.',
    },
    {
      code: 'no_sponsor_call_option',
      severity: 'LOW',
      message:
        'The flip is modelled as a change in sharing ratios, not as a purchase of the investor’s residual interest. No sponsor call option is modelled and no exercise price is paid.',
    },
  ],
  t_flip: [
    {
      code: 'no_itc_bridge',
      severity: 'MEDIUM',
      message:
        'No ITC bridge loan is modelled. A §6418 credit does not exist until the property is placed in service, so its sale cannot fund construction; proceeds arrive in the settlement year, undiscounted and unbridged.',
    },
    {
      code: 'partial_transfer_pricing',
      severity: 'LOW',
      message:
        'The transfer is priced on a slice of the credit at the whole-credit price. No size discount or premium is applied to a partial sale.',
    },
  ],
  direct_transfer: [
    {
      code: 'transfer_cost_placeholder',
      severity: 'MEDIUM',
      message:
        'Transaction cost is a single 2% of face — a placeholder standing in for a broker / credit-insurance / legal stack. §6418(g)(2)’s 20% excessive-transfer penalty is narrative justification only and is never computed into a cashflow.',
    },
    {
      code: 'recapture_not_modelled',
      severity: 'MEDIUM',
      message:
        'Recapture is flagged, never modelled. No §50(a) recapture event is simulated in any structure.',
    },
  ],
  preferred_equity: [
    {
      code: 'preferred_outstanding_at_term',
      severity: 'HIGH',
      message:
        'The preferred is still outstanding at its target term. No coupon step-up, cash sweep or forced-sale remedy is modelled, so the reported sponsor return is correspondingly optimistic.',
    },
    {
      code: 'debt_recharacterisation',
      severity: 'LOW',
      message:
        'Modelled as a partnership interest, not as an instrument that might be recharacterised as debt for tax purposes. That is a facts-and-circumstances question Structura does not attempt.',
    },
  ],
  sale_leaseback: [
    {
      code: 'sponsor_irr_undefined',
      severity: 'INFO',
      message:
        'The sale returns more than the sponsor’s construction equity, so the sponsor has little or no net investment and the IRR describes the residual, not the deal. Ranked on NPV.',
    },
    {
      code: 'level_rent_assumed',
      severity: 'LOW',
      message:
        'Rent is level. Stepped and seasonal rents are unsupported and the §467 rental-agreement accrual rules are not implemented. The purchase option is assumed exercised at the assumed residual with no option-value analysis.',
    },
  ],
};

function clone(x) {
  return JSON.parse(JSON.stringify(x));
}

/** Small, deterministic sensitivity so the UI visibly responds to overrides. */
function sensitivity(base, o) {
  const capexRatio = o.capex && base.capex ? o.capex / base.capex : 1;
  const dscrDelta = (o.target_dscr ?? base.target_dscr) - base.target_dscr;
  const rateDelta = (o.interest_rate ?? base.interest_rate) - base.interest_rate;
  return { capexRatio, dscrDelta, rateDelta };
}

/**
 * Mock implementation of POST /api/compare.
 * Shape is byte-for-byte the frozen contract; numbers are the calibrated
 * reference results, perturbed deterministically by the user's overrides.
 */
export function mockCompare(payload = {}) {
  const dealKey = payload.deal_key || 'storage_bess_contracted';
  const base = BASE[dealKey] || BASE.storage_bess_contracted;
  const dealMeta =
    MOCK_REFERENCE_DEALS.find((d) => d.key === dealKey) || MOCK_REFERENCE_DEALS[0];
  const defaults = MOCK_DEAL_INPUTS[dealKey] || MOCK_DEAL_INPUTS.storage_bess_contracted;
  const o = { ...defaults, ...(payload.overrides || {}) };

  const { capexRatio, dscrDelta, rateDelta } = sensitivity(defaults, o);
  const scale = capexRatio;

  const funding = Math.round(base.funding_requirement * scale);
  const debtScale = 1 / (1 + dscrDelta * 0.55 + rateDelta * 3.2);
  const quantum = Math.round(base.debt.quantum * scale * Math.min(1.35, Math.max(0.55, debtScale)));
  const gearing = funding > 0 ? quantum / funding : 0;
  const gearingCapped = gearing >= base.debt.gearing - 0.001;

  const warnings = [...STANDING_WARNINGS];
  const globalRisks = [];

  // ---- Litigation toggle: Notice 2025-42 / Oregon Environmental Council ----
  const litigation = o.notice_2025_42_status || 'vacated';
  const isWindSolar = o.technology === 'SOLAR' || o.technology === 'WIND';
  let taxWarnings = [];
  if (litigation === 'reinstated_on_appeal' && isWindSolar) {
    globalRisks.push({
      code: 'begin_construction_safe_harbor_lost',
      severity: 'BLOCKING',
      message:
        'Appeal scenario: Notice 2025-42 reinstated. The 5% cost safe harbor is unavailable to wind and solar above 1.5 MW, so begin-construction on ' +
        (o.begin_construction_date || 'the stated date') +
        ' must be established by the Physical Work Test alone. If it cannot be, the 2026-07-04 cliff is missed and the credit is zero unless the facility is placed in service by 2027-12-31.',
    });
    taxWarnings.push(
      'Scenario = reinstated_on_appeal. Structura models the appellate outcome as a switch, not a prediction. As of 2026-08-06 the notice is VACATED and the 5% safe harbor is restored; this run assumes the government prevails on appeal.'
    );
  } else if (litigation === 'reinstated_on_appeal') {
    taxWarnings.push(
      'Scenario = reinstated_on_appeal, but Notice 2025-42 only ever reached wind and solar above 1.5 MW. This technology is unaffected by the toggle.'
    );
  }

  if (o.technology === 'SOLAR' && (o.macr_ratio ?? 0) < 0.5) {
    globalRisks.push({
      code: 'macr_below_threshold',
      severity: 'BLOCKING',
      message:
        'Material Assistance Cost Ratio of ' +
        (100 * (o.macr_ratio ?? 0)).toFixed(0) +
        '% is below the 50% threshold for solar eligible components sold in CY2026 (OBBBA §70512; IRS Notice 2026-15). A MACR failure is disqualifying — the credit is zero, and every credit-dependent structure below is void.',
    });
  }

  if (isWindSolar && o.begin_construction_date && o.begin_construction_date > '2026-07-04') {
    const pis = o.placed_in_service_date || '';
    if (!pis || pis > '2027-12-31') {
      globalRisks.push({
        code: 'wind_solar_cliff_missed',
        severity: 'BLOCKING',
        message:
          'Construction began after the OBBBA cliff of 2026-07-04 and the facility is not placed in service on or before 2027-12-31. §48E/§45Y is zero — not reduced, zero.',
      });
    }
  }

  if ((o.domestic_content_pct ?? 0) > 0 && (o.domestic_content_pct ?? 0) < 0.5) {
    warnings.push(
      'engine.tax.adders: domestic content of ' +
        (100 * o.domestic_content_pct).toFixed(0) +
        '% is below the 2026 threshold of 50%. The adder is not applied. Threshold escalates to 55% thereafter.'
    );
  }
  if (!o.is_pwa_compliant) {
    warnings.push(
      'engine.tax.eligibility: prevailing wage and apprenticeship not met — the ITC energy percentage is 6%, not 30%, and every adder falls to 2 points.'
    );
  }

  // ---- Structures ---------------------------------------------------------
  const rows = base.structures.map((s) => {
    if (s.feasible === false) {
      return {
        key: s.key,
        label: STRUCTURE_LABELS[s.key],
        feasible: false,
        infeasible_reason: s.infeasible_reason,
        sponsor_after_tax_irr: null,
        irr_is_meaningful: false,
        irr_not_meaningful_reason: null,
        sponsor_npv: null,
        effective_cost_of_capital: null,
        sponsor_equity_required: null,
        third_party_capital_raised: null,
        total_capital_raised: null,
        flip_year: null,
        credit_transferred: 0,
        credit_retained: 0,
        cash_timing: null,
        risks: [],
        warnings: [],
      };
    }

    // IRR moves with leverage and with the cost of debt.
    const irr = s.irr - rateDelta * 1.6 - dscrDelta * 0.012;
    const coc = s.coc + rateDelta * 0.62 + dscrDelta * 0.004;
    const sponsorEquity = Math.round(s.sponsor_equity * scale + (base.debt.quantum * scale - quantum));
    const thirdParty = Math.round(s.third_party * scale - (base.debt.quantum * scale - quantum));

    const meaningful = s.irr_is_meaningful !== false;
    const risks = [...(STANDING_RISKS[s.key] || [])];
    if (gearingCapped) {
      risks.push({
        code: 'gearing_bound_not_dscr_bound',
        severity: 'LOW',
        message:
          'Debt is gearing-bound at ' +
          (100 * gearing).toFixed(1) +
          '%, not DSCR-bound. Achieved minimum DSCR of ' +
          base.debt.min_dscr.toFixed(2) +
          'x sits well above the market floor of ' +
          dealMeta.dscr_benchmark +
          ' — the headroom exists because an ITC-eligible project cannot simultaneously carry maximum DSCR-sized senior debt and monetise its credit.',
      });
    }

    return {
      rank: 0,
      key: s.key,
      label: STRUCTURE_LABELS[s.key],
      feasible: true,
      infeasible_reason: null,
      sponsor_after_tax_irr: irr,
      irr_is_meaningful: meaningful,
      irr_not_meaningful_reason: meaningful ? null : s.irr_not_meaningful_reason,
      sponsor_npv: Math.round(s.npv * scale),
      effective_cost_of_capital: coc,
      sponsor_equity_required: sponsorEquity,
      third_party_capital_raised: thirdParty,
      total_capital_raised: sponsorEquity + thirdParty,
      flip_year: s.flip_year,
      credit_transferred: Math.round(s.credit_transferred * scale),
      credit_retained: Math.round(s.credit_retained * scale),
      cash_timing: {
        cash_weighted_average_years: s.cwa_years,
        share_by_year_5: s.share_by_year_5,
      },
      risks,
      warnings: [],
    };
  });

  // Rank: meaningful IRR first (desc), then not-meaningful on NPV, then infeasible.
  const feasible = rows.filter((r) => r.feasible);
  const infeasible = rows.filter((r) => !r.feasible);
  feasible.sort((a, b) => {
    if (a.irr_is_meaningful !== b.irr_is_meaningful) return a.irr_is_meaningful ? -1 : 1;
    if (a.irr_is_meaningful) return b.sponsor_after_tax_irr - a.sponsor_after_tax_irr;
    return b.sponsor_npv - a.sponsor_npv;
  });
  const ranked = [...feasible, ...infeasible].map((r, i) => ({
    ...r,
    rank: r.feasible ? i + 1 : null,
  }));

  const winner = ranked[0];
  const runnerUp = ranked.find((r, i) => i > 0 && r.feasible && r.irr_is_meaningful);

  const drivers = runnerUp
    ? [
        {
          name: 'Effective cost of capital',
          unit: 'rate',
          winner_value: winner.effective_cost_of_capital,
          runner_up_value: runnerUp.effective_cost_of_capital,
          delta: winner.effective_cost_of_capital - runnerUp.effective_cost_of_capital,
          higher_is_better: false,
          note:
            'The IRR of third-party capital in against everything paid or surrendered to those providers, with tax attributes valued at what the recipient realises. This is a defined quantity, not a market convention — see /methods.',
        },
        {
          name: 'Sponsor equity required',
          unit: 'usd',
          winner_value: winner.sponsor_equity_required,
          runner_up_value: runnerUp.sponsor_equity_required,
          delta: winner.sponsor_equity_required - runnerUp.sponsor_equity_required,
          higher_is_better: false,
          note:
            'The cheque the sponsor writes at close. A lower number is not automatically better — it shrinks the base the IRR is computed on, which is exactly why the meaningfulness guard exists.',
        },
        {
          name: 'Credit retained in the partnership',
          unit: 'usd',
          winner_value: winner.credit_retained,
          runner_up_value: runnerUp.credit_retained,
          delta: winner.credit_retained - runnerUp.credit_retained,
          higher_is_better: true,
          note:
            'Credit kept and allocated inside the partnership rather than sold under §6418. Retaining is worth more per dollar than selling at ~90¢, but only to a partner with the tax appetite to use it.',
        },
        {
          name: 'Credit transferred (§6418)',
          unit: 'usd',
          winner_value: winner.credit_transferred,
          runner_up_value: runnerUp.credit_transferred,
          delta: winner.credit_transferred - runnerUp.credit_transferred,
          higher_is_better: false,
          note:
            'Sold for cash at the assumed clearing price of ~90¢ less 2% transaction cost. Crux puts direct transfer at 28% of ITC gross value in 2025 and above 90% for PTCs.',
        },
        {
          name: 'Flip year',
          unit: 'years',
          winner_value: winner.flip_year,
          runner_up_value: runnerUp.flip_year,
          delta:
            winner.flip_year != null && runnerUp.flip_year != null
              ? winner.flip_year - runnerUp.flip_year
              : null,
          higher_is_better: false,
          note:
            'The point at which sharing ratios change. A later flip defers the sponsor’s cash and depresses its IRR; the reported deferral compares against an otherwise-identical pure flip with the same investor commitment.',
        },
        {
          name: 'Cash-weighted average life',
          unit: 'years',
          winner_value: winner.cash_timing ? winner.cash_timing.cash_weighted_average_years : null,
          runner_up_value: runnerUp.cash_timing
            ? runnerUp.cash_timing.cash_weighted_average_years
            : null,
          delta:
            winner.cash_timing && runnerUp.cash_timing
              ? winner.cash_timing.cash_weighted_average_years -
                runnerUp.cash_timing.cash_weighted_average_years
              : null,
          higher_is_better: false,
          note:
            'When the sponsor actually gets paid. Two structures with the same IRR are not the same deal if one pays out five years earlier.',
        },
      ]
    : [];

  const disqualified = ranked
    .filter((r) => !r.feasible)
    .map((r) => ({ structure: r.key, reason: r.infeasible_reason }));

  const notMeaningful = ranked.filter((r) => r.feasible && !r.irr_is_meaningful);
  const caveats = [
    'Ranking is on sponsor after-tax IRR, but only where that rate is meaningful. IRR is a rate on an equity base; shrink the base far enough and the rate describes the base rather than the deal.',
    'One debt sizing serves all five structures. Re-sizing per structure would make the comparison meaningless.',
  ];
  notMeaningful.forEach((r) => {
    caveats.push(
      r.label +
        ' produced a rate of ' +
        (100 * r.sponsor_after_tax_irr).toFixed(2) +
        '% which is refused as a headline and ranked on NPV instead. ' +
        r.irr_not_meaningful_reason
    );
  });

  const headlineMetric = winner.irr_is_meaningful
    ? 'sponsor after-tax IRR ' + (100 * winner.sponsor_after_tax_irr).toFixed(2) + '%'
    : 'sponsor NPV $' + (winner.sponsor_npv / 1e6).toFixed(1) + 'm';

  return {
    deal: {
      key: dealKey,
      name: dealMeta.name,
      summary: dealMeta.summary,
      capex: o.capex,
    },
    headline:
      winner.label +
      ': ' +
      headlineMetric +
      ' at an effective cost of capital of ' +
      (100 * winner.effective_cost_of_capital).toFixed(2) +
      '%' +
      (runnerUp
        ? ', ahead of ' +
          runnerUp.label +
          ' by ' +
          (10000 * (winner.sponsor_after_tax_irr - runnerUp.sponsor_after_tax_irr)).toFixed(0) +
          ' bps.'
        : '.'),
    law_verified_on: LAW_VERIFIED_ON,
    ranked,
    why_this_wins: {
      winner: winner.key,
      primary_metric: winner.irr_is_meaningful ? 'sponsor_after_tax_irr' : 'sponsor_npv',
      winner_value: winner.irr_is_meaningful
        ? winner.sponsor_after_tax_irr
        : winner.sponsor_npv,
      runner_up: runnerUp ? runnerUp.key : null,
      runner_up_value: runnerUp ? runnerUp.sponsor_after_tax_irr : null,
      margin:
        runnerUp && winner.irr_is_meaningful
          ? winner.sponsor_after_tax_irr - runnerUp.sponsor_after_tax_irr
          : null,
      drivers,
      disqualified,
      tie_breaks: [],
      caveats,
    },
    sources_and_uses: {
      funding_requirement: funding,
      debt: quantum,
      third_party_equity: winner.third_party_capital_raised - quantum,
      sponsor_equity: winner.sponsor_equity_required,
      post_cod_monetisation: base.structures.find((s) => s.key === winner.key)
        ? Math.round((base.structures.find((s) => s.key === winner.key).post_cod || 0) * scale)
        : 0,
    },
    debt: {
      quantum,
      gearing,
      min_dscr: Math.max(1.0, base.debt.min_dscr - dscrDelta * 0.4 - rateDelta * 5),
      binding_constraint: gearingCapped ? 'GEARING' : 'DSCR',
      llcr: base.debt.llcr - rateDelta * 4,
      plcr: base.debt.plcr - rateDelta * 4,
    },
    tax: {
      ...base.tax,
      credit_value: Math.round(base.tax.credit_value * scale),
      warnings: taxWarnings,
    },
    capital_account_breaches: [],
    warnings,
    risks: globalRisks,
    compute_ms: 0,
  };
}

/** Mock GET /api/reference-deals */
export function mockReferenceDeals() {
  return { deals: MOCK_REFERENCE_DEALS };
}

/** Mock GET /api/current-law — mirrors engine/tax/citations.py and UNVERIFIED.md. */
export function mockCurrentLaw() {
  return {
    law_verified_on: LAW_VERIFIED_ON,
    citations: [
      {
        id: 'obbba-bifurcation',
        authority: 'One Big Beautiful Bill Act, P.L. 119-21 (enacted 2025-07-04)',
        headline: 'OBBBA bifurcated §48E/§45Y rather than repealing them',
        summary:
          'OBBBA left the clean electricity investment credit (§48E) and production credit (§45Y) in force, but split the technologies: wind and solar face an accelerated begin-construction cliff while storage, geothermal, nuclear and hydro keep the original runway.',
        source: 'Public Law 119-21, enacted 2025-07-04.',
        topic: 'eligibility',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'wind-solar-boc-cliff',
        authority: 'OBBBA P.L. 119-21 (2025-07-04), amending I.R.C. §§45Y, 48E',
        headline: 'Wind/solar begin-construction cliff — 2026-07-04',
        summary:
          'A wind or solar facility must have begun construction on or before 2026-07-04 to claim §48E/§45Y on the ordinary timetable. Projects that did so keep the standard four-year continuity window.',
        source: 'Statutory text as amended.',
        topic: 'eligibility',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'wind-solar-pis-backstop',
        authority: 'OBBBA P.L. 119-21 (2025-07-04), amending I.R.C. §§45Y, 48E',
        headline: 'Wind/solar placed-in-service backstop — 2027-12-31',
        summary:
          'A wind or solar facility that missed the 2026-07-04 begin-construction deadline can still claim the credit only if it is placed in service on or before 2027-12-31. Miss both tests and the credit is zero — not reduced, zero.',
        source: 'Statutory text as amended.',
        topic: 'eligibility',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'non-wind-solar-runway',
        authority: 'I.R.C. §48E(e) as amended by OBBBA P.L. 119-21',
        headline: 'Storage / geothermal / nuclear / hydro runway and phase-down',
        summary:
          'These technologies were untouched by the accelerated cliff. Full §48E for construction begun through 2033, then 75% for 2034, 50% for 2035 and zero from 2036.',
        source: 'Statutory text as amended.',
        topic: 'eligibility',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'base-and-pwa-rate',
        authority: 'I.R.C. §48E(a)(2), §48E(d)(3); §45Y(a)(2), §45Y(g)(9)',
        headline: '6% base rate, 30% with prevailing wage and apprenticeship',
        summary:
          'The ITC energy percentage is 6%, multiplied by five to 30% where the prevailing wage and apprenticeship (PWA) requirements are met. The PTC works the same way: a 0.3¢/kWh base amount, times five with PWA, then inflation adjusted.',
        source: 'Statutory text.',
        topic: 'eligibility',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'ptc-credit-period',
        authority: 'I.R.C. §45Y(a)(1)',
        headline: '§45Y ten-year credit period',
        summary:
          'The production credit runs for the ten-year period beginning on the date the facility is placed in service.',
        source: 'Statutory text.',
        topic: 'eligibility',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'ptc-inflation-adjustment',
        authority: 'I.R.C. §45Y(c)',
        headline: '§45Y annual inflation adjustment (unverified factors)',
        summary:
          'The 0.3¢/kWh base amount is adjusted annually for inflation and rounded to the nearest 0.05 cent. The IRS announces the factor each year. Only the 2022 base year ships; the engine raises rather than guessing a rate.',
        source:
          'Statutory mechanism is black-letter; the annual factors were not sourced in this build.',
        topic: 'eligibility',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'PLACEHOLDER',
      },
      {
        id: 'phase-down-application',
        authority: 'I.R.C. §48E(e)',
        headline: 'Whether the phase-down haircuts the bonus amounts too',
        summary:
          'The non-wind/solar phase-out is expressed as a percentage of the credit determined under §48E(a). Whether the domestic content and energy community bonuses ride the same haircut is modelled as a switch, defaulting to applying it to the whole credit.',
        source: 'Interpretation; not confirmed against guidance.',
        topic: 'eligibility',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'PROVISIONAL',
      },
      {
        id: 'domestic-content-threshold',
        authority: 'I.R.C. §48E(a)(3)(B), §45Y(g)(11); Notice 2025-08',
        headline: 'Domestic content threshold escalates to 50% in 2026',
        summary:
          'The applicable percentage runs 40% (pre-2025) → 45% (2025) → 50% (2026) → 55% thereafter.',
        source: 'Structura verified rulebook, checked live 2026-08-06.',
        topic: 'adders',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'domestic-content-adder-amount',
        authority: 'I.R.C. §48(a)(12) drafting carried into §48E; §45Y(g)(11)',
        headline: 'Domestic content bonus: 2 points base, 10 points with PWA',
        summary: 'The adder is 10 percentage points on the ITC, or 10% on the PTC, where PWA is met.',
        source: 'Structura verified rulebook, checked live 2026-08-06.',
        topic: 'adders',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'notice-2025-08-safe-harbor',
        authority: 'IRS Notice 2025-08 (January 2025)',
        headline: 'Elective safe-harbor assigned cost percentages',
        summary:
          'Notice 2025-08 provides elective safe-harbor cost percentages for the domestic content adder, published per technology and per component. Structura ships only a stub; electing the safe harbor raises rather than returning a made-up ratio. Actual-cost build-up works normally.',
        source:
          'The existence and purpose of the notice are carried by the verified rulebook; the percentages themselves were not obtained.',
        topic: 'adders',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'PLACEHOLDER',
      },
      {
        id: 'energy-community-adder',
        authority: 'I.R.C. §48E(a)(3)(A), §45(b)(11)(B)',
        headline: 'Energy community bonus: 2 points base, 10 points with PWA',
        summary:
          'Structura does not determine energy community status — the test needs the annual IRS/DOE appendices and a geospatial join. The caller asserts qualification and names the limb; the engine records the assertion and marks the adder provisional.',
        source: 'Adder amount from the verified rulebook; the qualification tests are not implemented.',
        topic: 'adders',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'PROVISIONAL',
      },
      {
        id: 'feoc-effective-date',
        authority: 'OBBBA §70512',
        headline: 'FEOC restrictions effective 2026-01-01',
        summary:
          'Foreign entity of concern restrictions took effect on 2026-01-01 and operate as a pass/fail gate on credit eligibility.',
        source: 'Structura verified rulebook, checked live 2026-08-06.',
        topic: 'feoc',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'notice-2026-15-macr',
        authority: 'IRS Notice 2026-15 (released 2026-02-12)',
        headline: 'Material Assistance Cost Ratio — interim methodology',
        summary:
          'The interim guidance defines the MACR methodology with interim safe harbors, supplier certifications and DOE-derived default cost tables. Broader PFE-status guidance was deferred.',
        source: 'Structura verified rulebook, checked live 2026-08-06.',
        topic: 'feoc',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'macr-thresholds',
        authority: 'OBBBA §70512 statutory MACR tables',
        headline: 'MACR thresholds are technology- and year-specific',
        summary:
          'Exactly one cell is verified: solar eligible components sold in CY2026 require a MACR of at least 50%. Every other technology/year cell shipped by Structura escalates plausibly by year and differs by technology — the shape is right, the numbers are not authority.',
        source:
          'Only the solar-CY2026 50% cell is carried by the verified rulebook; the statutory tables were not obtained in this build.',
        topic: 'feoc',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'PLACEHOLDER',
      },
      {
        id: 'macr-failure-is-disqualifying',
        authority: 'OBBBA §70512',
        headline: 'A MACR failure kills the credit',
        summary:
          'Failing the Material Assistance Cost Ratio is disqualifying, not reducing. Structura renders it as a BLOCKING risk and voids every credit-dependent structure.',
        source: 'Structura verified rulebook, checked live 2026-08-06.',
        topic: 'feoc',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'section-70512h-transfer-ban',
        authority: 'OBBBA §70512(h); I.R.C. §7701(a)(51)(B)',
        headline:
          'No transfer of §45Q/45X/45Y/45Z/48E credits to a specified foreign entity',
        summary:
          'Effective for taxable years beginning after 2025-07-04 — first tested 2026-01-01 for calendar-year taxpayers.',
        source: 'Structura verified rulebook, checked live 2026-08-06.',
        topic: 'transfer',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'five-percent-safe-harbor',
        authority: 'IRS begin-construction guidance (Notice 2013-29 line, carried forward)',
        headline: '5% cost safe harbor',
        summary:
          'Construction is treated as begun when 5% or more of total project cost has been paid or incurred, provided continuous efforts follow.',
        source: 'Long-standing IRS begin-construction guidance.',
        topic: 'begin_construction',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'physical-work-test',
        authority: 'IRS begin-construction guidance (Notice 2013-29 line, carried forward)',
        headline: 'Physical Work Test',
        summary:
          'Construction begins when physical work of a significant nature starts, judged on the nature rather than the amount of the work.',
        source: 'Long-standing IRS begin-construction guidance.',
        topic: 'begin_construction',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'continuity-safe-harbor',
        authority: 'IRS begin-construction guidance (Notice 2013-29 line, carried forward)',
        headline: 'Four-year continuity safe harbor',
        summary:
          'A facility placed in service within four calendar years after the year construction began is deemed to satisfy continuity.',
        source: 'Long-standing IRS begin-construction guidance.',
        topic: 'begin_construction',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'notice-2025-42',
        authority: 'IRS Notice 2025-42 (August 2025)',
        headline: '5% safe harbor eliminated for wind/solar above 1.5 MW',
        summary:
          'The notice removed the 5% cost safe harbor for wind and solar facilities above 1.5 MW, forcing reliance on the Physical Work Test. It was vacated in full on 2026-06-06 — see the litigation panel.',
        source: 'Structura verified rulebook, checked live 2026-08-06.',
        topic: 'begin_construction',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'oregon-environmental-council-vacatur',
        authority:
          'Oregon Environmental Council v. IRS, No. 25-4400 (CKK) (D.D.C. 2026-06-06)',
        headline: 'Notice 2025-42 VACATED IN FULL — 5% safe harbor restored',
        summary:
          'The U.S. District Court for the District of Columbia vacated Notice 2025-42 in full as arbitrary and capricious under the APA, and remanded. The 5% safe harbor is restored. A government appeal or stay is expected; the court acknowledged the appellate timeline runs past 2026-07-04.',
        source: 'Structura verified rulebook, checked live 2026-08-06.',
        topic: 'begin_construction',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'notice-2025-42-applicability-date',
        authority: 'IRS Notice 2025-42 (August 2025)',
        headline: 'Prospective applicability date of Notice 2025-42',
        summary:
          'The exact date after which the notice applied was not confirmed. Structura assumes 2025-09-02 so that all 2026 begin-construction dates are exercised by the litigation toggle. A project with a late-2025 BOC date is the case sensitive to this.',
        source:
          'Existence of a prospective cut-off is standard IRS practice; the applicability paragraph was not obtained.',
        topic: 'begin_construction',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'PLACEHOLDER',
      },
      {
        id: 'itc-basis-reduction',
        authority: 'I.R.C. §50(c)(3)',
        headline: '50% ITC basis reduction',
        summary:
          'Depreciable basis is reduced by 50% of the credit claimed, charged to capital accounts as an item of loss and to outside basis on the credit ratio.',
        source: 'Statutory text.',
        topic: 'depreciation',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'macrs-recovery-periods',
        authority: 'I.R.C. §168; IRS Pub. 946 Table A-1',
        headline: 'MACRS 5-year and 15-year GDS tables',
        summary: 'The 5-year and 15-year GDS tables are implemented as published.',
        source: 'IRS Pub. 946.',
        topic: 'depreciation',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'bonus-depreciation',
        authority: 'I.R.C. §168(k) as amended by OBBBA',
        headline: 'Bonus depreciation',
        summary:
          '100% bonus expensing is understood to have been restored by OBBBA for qualified property acquired after 2025-01-19. The rate is a caller-supplied input; the acquisition-date mechanics are not implemented.',
        source: 'Rate widely reported; the acquisition-date mechanics were not confirmed.',
        topic: 'depreciation',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'PROVISIONAL',
      },
      {
        id: 'straight-line-conventions',
        authority: 'I.R.C. §168(b)(3), §168(d)',
        headline: 'Straight-line elections and averaging conventions',
        summary:
          'The half-year convention is applied to every straight-line life, including 39-year nonresidential real property which properly uses mid-month. The mid-quarter convention is not implemented.',
        source: 'Statutory; the engine applies half-year uniformly.',
        topic: 'depreciation',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'PROVISIONAL',
      },
      {
        id: 'section-6418-alive',
        authority: 'I.R.C. §6418',
        headline: '§6418 transferability survived OBBBA intact',
        summary:
          'Draft bills proposed a sunset; the enacted OBBBA preserved §6418 whole. §6417 direct pay is also intact.',
        source: 'Structura verified rulebook, checked live 2026-08-06.',
        topic: 'transfer',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'section-6417-direct-pay',
        authority: 'I.R.C. §6417',
        headline: '§6417 elective payment (direct pay) intact',
        summary:
          'The enumerated list of applicable entities, and the rule that a taxable entity may elect direct pay only for §45Q/§45V/§45X, are stated from the statutory categories rather than confirmed against text.',
        source:
          'Survival of §6417 is carried by the verified rulebook; the applicable-entity list was not confirmed.',
        topic: 'transfer',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'PROVISIONAL',
      },
      {
        id: 'excessive-credit-transfer-penalty',
        authority: 'I.R.C. §6418(g)(2)',
        headline: '20% excessive credit transfer penalty',
        summary:
          'Used only as narrative justification for a non-zero transaction-cost default. It is not computed into any cashflow.',
        source: 'Statutory text; not modelled numerically.',
        topic: 'transfer',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'PROVISIONAL',
      },
      {
        id: 'transfer-market-2025',
        authority: 'Crux 2025 transferability market data',
        headline: 'Transfer market $32bn (2024) → $42bn (2025), +48%',
        summary:
          'Total monetisation was $63bn in 2025. For ITCs: partnerships 57% of gross value, direct transfer 28%, preferred equity 15%. For PTCs: over 90% direct transfer. 1 in 4 Fortune 1000 companies now participate.',
        source: 'Crux 2025 transferability market data. Context and narration only — never an arithmetic input.',
        topic: 'market',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
      {
        id: 'itc-transfer-pricing-default',
        authority: 'Norton Rose Fulbright, Cost of Capital: 2026 Outlook (2026-01-29)',
        headline: 'Default ITC clearing price ~90¢',
        summary:
          'Implied by the ITC bridge quote: 98% advance at SOFR+150 if covered/committed; 75% advance (~67.5% net at 90¢) at SOFR+225 if uncovered. The PTC price of 92¢ is a placeholder — no PTC clearing price is carried by the verified rulebook.',
        source: 'Norton Rose Fulbright, Cost of Capital: 2026 Outlook market benchmarks.',
        topic: 'market',
        verified_on: LAW_VERIFIED_ON,
        confidence: 'VERIFIED',
      },
    ],
    unverified: [
      {
        item: 'MACR threshold table',
        detail:
          'Only the solar CY2026 cell (≥50%) is sourced. Every other technology/year cell escalates plausibly but is not authority. The statutory tables in OBBBA §70512 and the interim methodology in IRS Notice 2026-15 were not obtained in this build.',
        impact:
          'A FEOC pass/fail on any technology other than solar in CY2026 is indicative only. It is a hard eligibility gate, so an error here voids the credit and both credit-dependent structures.',
        confidence: 'PLACEHOLDER',
      },
      {
        item: '§45Y inflation adjustment factors',
        detail:
          'Only the 2022 base year (factor 1.0) ships. The IRS announces the factor annually and it was not sourced.',
        impact:
          'The engine raises NotImplementedError rather than returning a guessed PTC rate. A fabricated rate would flow straight into a sponsor IRR, so refusing is the correct failure mode.',
        confidence: 'PLACEHOLDER',
      },
      {
        item: 'Notice 2025-08 elective safe-harbor percentages',
        detail:
          'The notice exists and provides elective assigned cost percentages per technology and per component. The percentages themselves were not obtained; only a single-ratio stub ships.',
        impact:
          'Electing the safe harbor raises rather than returning a number. Actual-cost domestic content build-up works normally.',
        confidence: 'PLACEHOLDER',
      },
      {
        item: 'Notice 2025-42 applicability date',
        detail:
          'Set to 2025-09-02 — the notice’s issue month — because the applicability paragraph was not confirmed. IRS notices of this kind are normally prospective.',
        impact:
          'A project with a late-2025 begin-construction date is the case sensitive to this. All 2026 BOC dates are exercised by the litigation toggle regardless.',
        confidence: 'PLACEHOLDER',
      },
      {
        item: 'Tax-equity, preferred and lease pricing',
        detail:
          'Target after-tax IRR of 6.50% for tax equity, 9.00% preferred return, 7.00% lessor target and a 20% sale-leaseback residual all ship as labelled placeholders. NRF publishes debt pricing and DSCR by technology; it publishes no tax-equity target yield, no pre-flip split and no preferred coupon. Crux publishes market shares, not prices.',
        impact:
          'The tax-equity target yield drives the flip solve. Override it before relying on any flip output.',
        confidence: 'PLACEHOLDER',
      },
      {
        item: 'PPA / offtake prices and capex per kW',
        detail:
          'No free source of PPA prices exists — LevelTen’s index is subscriber-only. Capex figures are round order-of-magnitude placeholders; the NLR Annual Technology Baseline 2024 v4.0.0 is the intended anchor but is not yet a data dependency.',
        impact:
          'Every reference deal carries at least one placeholder assumption, asserted by a test.',
        confidence: 'PLACEHOLDER',
      },
      {
        item: 'Energy community qualification',
        detail:
          'Structura does not determine energy community status. The three statutory limbs each require the annual IRS/DOE appendices and a geospatial join. The caller asserts qualification and names the limb.',
        impact:
          'The adder amount (2 points base / 10 with PWA) is verified; the qualification is an unverified user assertion recorded in the audit trail.',
        confidence: 'PROVISIONAL',
      },
      {
        item: 'Phase-down application to bonus adders',
        detail:
          'Whether the §48E(e) haircut reaches the domestic content and energy community bonuses was not confirmed. Modelled as a switch, defaulting to haircutting the whole credit.',
        impact:
          'Matters only for begin-construction years 2034–2035 on non-wind/solar technologies.',
        confidence: 'PROVISIONAL',
      },
    ],
    litigation: {
      case: 'Oregon Environmental Council v. IRS, No. 25-4400 (CKK)',
      court: 'U.S. District Court for the District of Columbia',
      decided: '2026-06-06',
      effect: 'Notice 2025-42 vacated in full; 5% safe harbor restored',
      status: 'appeal expected',
      reasoning:
        'The court held the notice arbitrary and capricious under the Administrative Procedure Act, and remanded. It acknowledged that the appellate timeline runs past 2026-07-04 — the date of the OBBBA wind/solar begin-construction cliff.',
      toggle_values: ['vacated', 'reinstated_on_appeal'],
      toggle_explanation:
        'Structura models the appellate outcome as an input, not a prediction. Set the toggle to "vacated" (the law as of 2026-08-06) and a wind or solar project above 1.5 MW may establish begin-construction with the 5% cost safe harbor. Set it to "reinstated_on_appeal" and that route closes: begin-construction must be established by the Physical Work Test alone, and a project that cannot do so misses the 2026-07-04 cliff and is thrown onto the 2027-12-31 placed-in-service backstop — or gets nothing. The toggle changes eligibility, not arithmetic.',
    },
  };
}

export { clone };
