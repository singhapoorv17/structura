'use client';

import { useState } from 'react';

/**
 * Six fields. Everything else is resolved and badged.
 *
 * The size inputs change with the asset type because a battery is quoted in
 * MW and MWh, a data centre in IT MW, and asking for all of them at once is
 * how a six-field form becomes a forty-field form.
 */

const ASSETS = [
  { value: 'SOLAR', label: 'Solar' },
  { value: 'SOLAR_PLUS_STORAGE', label: 'Solar + storage' },
  { value: 'STORAGE', label: 'Standalone storage' },
  { value: 'WIND', label: 'Onshore wind' },
  { value: 'DATA_CENTRE', label: 'Data centre' },
  { value: 'AI_COMPUTE', label: 'AI compute' },
  { value: 'RNG', label: 'RNG' },
];

const CONTRACTS = [
  { value: 'PPA', label: 'PPA' },
  { value: 'TOLLING', label: 'Tolling' },
  { value: 'HEDGE', label: 'Bank hedge' },
  { value: 'HYPERSCALE_LEASE', label: 'Hyperscale lease' },
  { value: 'EQUIPMENT_LEASE', label: 'Equipment lease' },
  { value: 'MERCHANT', label: 'Merchant' },
];

const PRIORITIES = [
  { value: 'max_irr', label: 'Maximise sponsor IRR' },
  { value: 'max_near_term_cash', label: 'Maximise near-term cash' },
  { value: 'min_execution_risk', label: 'Minimise execution risk' },
  { value: 'max_proceeds_at_close', label: 'Maximise proceeds at close' },
];

const PRESETS = [
  {
    label: 'ERCOT solar + storage',
    deal: {
      asset_type: 'SOLAR_PLUS_STORAGE',
      size: { mwac: 430, mwh: 340 },
      state: 'TX',
      contract: { kind: 'PPA', tenor_years: 15 },
      cod: '2028-06',
    },
  },
  {
    label: 'Four-hour storage, CAISO',
    deal: {
      asset_type: 'STORAGE',
      size: { mw: 150, mwh: 600 },
      state: 'CA',
      contract: { kind: 'TOLLING', tenor_years: 15 },
      cod: '2028-01',
    },
  },
  {
    label: 'Hyperscale data centre',
    deal: {
      asset_type: 'DATA_CENTRE',
      size: { it_mw: 250 },
      state: 'VA',
      contract: { kind: 'HYPERSCALE_LEASE', tenor_years: 15 },
      cod: '2028-09',
    },
  },
  {
    label: 'AI compute equipment',
    deal: {
      asset_type: 'AI_COMPUTE',
      size: { mw: 1000 },
      state: 'TX',
      contract: { kind: 'EQUIPMENT_LEASE', tenor_years: 6 },
      cod: '2026-06',
    },
  },
];

function sizeFieldsFor(asset) {
  if (asset === 'STORAGE') return [['mw', 'MW'], ['mwh', 'MWh']];
  if (asset === 'SOLAR_PLUS_STORAGE') return [['mwac', 'MWac'], ['mwh', 'MWh']];
  if (asset === 'DATA_CENTRE') return [['it_mw', 'IT MW']];
  if (asset === 'AI_COMPUTE') return [['mw', 'MW']];
  return [['mwac', 'MWac']];
}

export default function DealForm({ deal, priority, busy, onChange, onPriority, onSubmit }) {
  const [local, setLocal] = useState(deal);

  function update(patch) {
    const next = { ...local, ...patch };
    setLocal(next);
    onChange(next);
  }

  function updateSize(key, raw) {
    const size = { ...local.size };
    if (raw === '') delete size[key];
    else size[key] = Number(raw);
    update({ size });
  }

  function applyPreset(preset) {
    setLocal(preset.deal);
    onChange(preset.deal);
  }

  const sizeFields = sizeFieldsFor(local.asset_type);

  return (
    <form
      className="dealform"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(local);
      }}
    >
      <div className="dealform-presets">
        <span className="dealform-presets-label">Start from</span>
        {PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            className="chip"
            onClick={() => applyPreset(p)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="dealform-grid">
        <label className="field">
          <span>Asset type</span>
          <select
            value={local.asset_type}
            onChange={(e) => update({ asset_type: e.target.value, size: {} })}
          >
            {ASSETS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
        </label>

        {sizeFields.map(([key, unit]) => (
          <label className="field" key={key}>
            <span>Size ({unit})</span>
            <input
              type="number"
              min="0"
              step="any"
              value={local.size[key] ?? ''}
              onChange={(e) => updateSize(key, e.target.value)}
              placeholder="—"
            />
          </label>
        ))}

        <label className="field field-sm">
          <span>State</span>
          <input
            type="text"
            maxLength={2}
            value={local.state}
            onChange={(e) => update({ state: e.target.value.toUpperCase() })}
            placeholder="TX"
          />
        </label>

        <label className="field">
          <span>Contract</span>
          <select
            value={local.contract.kind}
            onChange={(e) =>
              update({ contract: { ...local.contract, kind: e.target.value } })
            }
          >
            {CONTRACTS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field field-sm">
          <span>Tenor (yrs)</span>
          <input
            type="number"
            min="0"
            max="40"
            value={local.contract.tenor_years ?? ''}
            onChange={(e) =>
              update({
                contract: {
                  ...local.contract,
                  tenor_years: e.target.value === '' ? null : Number(e.target.value),
                },
              })
            }
          />
        </label>

        <label className="field field-sm">
          <span>Target COD</span>
          <input
            type="text"
            value={local.cod}
            onChange={(e) => update({ cod: e.target.value })}
            placeholder="2028-06"
          />
        </label>

        <label className="field">
          <span>Optimising for</span>
          <select value={priority} onChange={(e) => onPriority(e.target.value)}>
            {PRIORITIES.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </label>

        <button className="btn-primary" type="submit" disabled={busy}>
          {busy ? 'Running…' : 'Analyse'}
        </button>
      </div>

      <p className="dealform-note">
        Capex, coverage, pricing and production are resolved from comparable
        transactions and cited market bands. Every one is badged, and every one
        can be overridden.
      </p>
    </form>
  );
}
