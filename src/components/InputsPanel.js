'use client';

import { usdM } from '../lib/format';

function Num({ label, unit, value, onChange, step = 1, min }) {
  return (
    <div className="field">
      <label>
        <span>{label}</span>
        {unit ? <span className="unit">{unit}</span> : null}
      </label>
      <input
        type="number"
        value={value ?? ''}
        step={step}
        min={min}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
      />
    </div>
  );
}

function Day({ label, value, onChange }) {
  return (
    <div className="field">
      <label>
        <span>{label}</span>
        <span className="unit">ISO</span>
      </label>
      <input type="date" value={value || ''} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function Pick({ label, value, onChange, options, unit }) {
  return (
    <div className="field">
      <label>
        <span>{label}</span>
        {unit ? <span className="unit">{unit}</span> : null}
      </label>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export default function InputsPanel({
  deals,
  dealsLoading,
  dealsError,
  dealKey,
  onSelectDeal,
  values,
  onChange,
  onRun,
  onReset,
  running,
  dirty,
}) {
  const set = (k) => (v) => onChange(k, v);
  const isWindSolar = values.technology === 'SOLAR' || values.technology === 'WIND';

  return (
    <div>
      <section className="panel">
        <header>
          <h2>Reference deal</h2>
          <span className="sub">calibrated · sources = uses</span>
        </header>
        <div className="body">
          {dealsLoading ? (
            <div>
              <div className="skel" style={{ width: '85%' }} />
              <div className="skel" style={{ width: '60%' }} />
              <div className="skel" style={{ width: '72%' }} />
            </div>
          ) : dealsError ? (
            <div className="callout blocking">
              <div className="ct">Could not load reference deals</div>
              {dealsError}
            </div>
          ) : (
            <div className="deals">
              {deals.map((d) => (
                <button
                  key={d.key}
                  type="button"
                  className={'deal' + (d.key === dealKey ? ' on' : '')}
                  onClick={() => onSelectDeal(d.key)}
                >
                  <span className="dname">{d.name}</span>
                  <span className="dmeta">
                    <span>{d.technology}</span>
                    <span>{usdM(d.capex)} capex</span>
                    <span>DSCR {d.dscr_benchmark}</span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="panel">
        <header>
          <h2>Overrides</h2>
          <span className="sub">{dirty ? 'edited' : 'deal defaults'}</span>
        </header>
        <div className="body">
          <fieldset className="fieldset">
            <legend>Project</legend>
            <div className="grid2">
              <Num label="Capex" unit="USD" value={values.capex} onChange={set('capex')} step={1000000} min={0} />
              <Num
                label="Opex year 1"
                unit="USD/yr"
                value={values.opex_year1}
                onChange={set('opex_year1')}
                step={100000}
                min={0}
              />
              <Num
                label="Production P50"
                unit="MWh (1 = toll)"
                value={values.production_p50}
                onChange={set('production_p50')}
                step={1000}
                min={0}
              />
              <Num
                label="Contracted price"
                unit="$/MWh or $/yr"
                value={values.contracted_price}
                onChange={set('contracted_price')}
                step={1}
                min={0}
              />
              <Num
                label="Contract years"
                unit="yr"
                value={values.contract_years}
                onChange={set('contract_years')}
                step={1}
                min={1}
              />
              <Num
                label="Project life"
                unit="yr"
                value={values.project_life_years}
                onChange={set('project_life_years')}
                step={1}
                min={1}
              />
              <Pick
                label="Technology"
                value={values.technology}
                onChange={set('technology')}
                options={[
                  { value: 'STORAGE', label: 'Storage (BESS)' },
                  { value: 'SOLAR', label: 'Solar PV' },
                  { value: 'WIND', label: 'Wind' },
                  { value: 'DATA_CENTER', label: 'Data centre' },
                ]}
              />
            </div>
          </fieldset>

          <fieldset className="fieldset">
            <legend>Debt</legend>
            <div className="grid2">
              <Num
                label="Target DSCR"
                unit="x"
                value={values.target_dscr}
                onChange={set('target_dscr')}
                step={0.05}
                min={1}
              />
              <Num
                label="Interest rate"
                unit="decimal"
                value={values.interest_rate}
                onChange={set('interest_rate')}
                step={0.0025}
                min={0}
              />
              <Num label="Tenor" unit="yr" value={values.tenor_years} onChange={set('tenor_years')} step={1} min={1} />
            </div>
          </fieldset>

          <fieldset className="fieldset">
            <legend>Tax — §48E / §45Y</legend>
            <div className="grid2">
              <Day
                label="Begin construction"
                value={values.begin_construction_date}
                onChange={set('begin_construction_date')}
              />
              <Day
                label="Placed in service"
                value={values.placed_in_service_date}
                onChange={set('placed_in_service_date')}
              />
              <Num
                label="Domestic content"
                unit="decimal"
                value={values.domestic_content_pct}
                onChange={set('domestic_content_pct')}
                step={0.01}
                min={0}
              />
              <Num
                label="MACR ratio"
                unit="decimal"
                value={values.macr_ratio}
                onChange={set('macr_ratio')}
                step={0.01}
                min={0}
              />
              <Num
                label="Bonus depreciation"
                unit="decimal"
                value={values.bonus_rate}
                onChange={set('bonus_rate')}
                step={0.1}
                min={0}
              />
            </div>
            <div style={{ marginTop: 8 }}>
              <label className="check">
                <input
                  type="checkbox"
                  checked={!!values.is_pwa_compliant}
                  onChange={(e) => onChange('is_pwa_compliant', e.target.checked)}
                />
                Prevailing wage &amp; apprenticeship met (6% → 30%)
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  checked={!!values.energy_community}
                  onChange={(e) => onChange('energy_community', e.target.checked)}
                />
                Energy community asserted
              </label>
            </div>
          </fieldset>

          <fieldset className="fieldset">
            <legend>⚖ Litigation scenario</legend>
            <Pick
              label="Notice 2025-42 status"
              unit="scenario"
              value={values.notice_2025_42_status}
              onChange={set('notice_2025_42_status')}
              options={[
                { value: 'vacated', label: 'Vacated — law as of 2026-08-06' },
                { value: 'reinstated_on_appeal', label: 'Reinstated on appeal' },
              ]}
            />
            <p
              style={{
                margin: '7px 0 0',
                fontSize: 11,
                lineHeight: 1.45,
                color: 'var(--text-faint)',
              }}
            >
              {values.notice_2025_42_status === 'vacated' ? (
                <>
                  <em>Oregon Environmental Council v. IRS</em> (D.D.C., 2026-06-06) vacated Notice
                  2025-42 in full. The 5% cost safe harbor is restored, so wind and solar above 1.5 MW
                  may establish begin-construction on cost.{' '}
                  {isWindSolar ? '' : 'This technology was never in scope of the notice.'}
                </>
              ) : (
                <>
                  Assumes the government prevails on appeal: the 5% safe harbor closes again and wind
                  and solar above 1.5 MW must rely on the Physical Work Test.{' '}
                  {isWindSolar
                    ? 'This project is in scope — see the blocking risk on the results.'
                    : 'This technology was never in scope of the notice, so nothing changes.'}
                </>
              )}
            </p>
          </fieldset>

          <div className="btnrow" style={{ marginTop: 14 }}>
            <button className="btn primary" onClick={onRun} disabled={running}>
              {running ? 'Solving…' : 'Run comparison'}
            </button>
            <button className="btn ghost" onClick={onReset} disabled={running || !dirty}>
              Reset
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
