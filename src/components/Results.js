'use client';

import { useState } from 'react';

import { Badge, Confidence, Value, fmtNumber } from './Provenance';

/* -------------------------------------------------------------------------
 * Advisories — what the tool wants to say before the model is read
 * ---------------------------------------------------------------------- */

export function Advisories({ items }) {
  if (!items || !items.length) return null;
  return (
    <div className="advisories">
      {items.map((a) => (
        <div key={a.id} className={`advisory advisory-${a.severity}`}>
          <span className="advisory-tag">{a.severity}</span>
          <div>
            <p>{a.message}</p>
            <p className="advisory-src">
              {a.source_url && a.source_url.startsWith('http') ? (
                <a href={a.source_url} target="_blank" rel="noreferrer noopener">
                  {a.source}
                </a>
              ) : (
                a.source
              )}
              {a.source_date ? ` · ${a.source_date}` : ''}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------
 * Resolved inputs
 * ---------------------------------------------------------------------- */

const INPUT_ORDER = [
  'capacity_mw',
  'energy_mwh',
  'capex',
  'production_p50',
  'contracted_price',
  'opex_year1',
  'target_dscr',
  'debt_spread_bps',
  'construction_spread_bps',
  'credit_price',
  'construction_months',
  'tenor_years',
  'project_life_years',
];

const INPUT_LABELS = {
  capacity_mw: 'Capacity',
  energy_mwh: 'Energy',
  capex: 'Total capital cost',
  production_p50: 'Production, P50',
  contracted_price: 'Contract price',
  opex_year1: 'Operating cost, year 1',
  target_dscr: 'Target DSCR',
  debt_spread_bps: 'Term loan spread',
  construction_spread_bps: 'Construction spread',
  credit_price: 'Credit transfer price',
  construction_months: 'Construction period',
  tenor_years: 'Debt tenor',
  project_life_years: 'Modelling horizon',
};

export function ResolvedInputs({ deal }) {
  const [onlyAssumed, setOnlyAssumed] = useState(false);
  const inputs = deal.inputs || {};
  const keys = INPUT_ORDER.filter((k) => inputs[k]).filter(
    (k) => !onlyAssumed || inputs[k].provenance === 'assumed'
  );

  return (
    <section className="panel">
      <header className="panel-head">
        <h2>Resolved inputs</h2>
        <label className="toggle">
          <input
            type="checkbox"
            checked={onlyAssumed}
            onChange={(e) => setOnlyAssumed(e.target.checked)}
          />
          show only what is assumed
        </label>
      </header>
      <Confidence counts={deal.confidence} />
      <table className="tbl tbl-inputs">
        <tbody>
          {keys.map((k) => (
            <tr key={k}>
              <th>{INPUT_LABELS[k] || k}</th>
              <td>
                <Value cell={inputs[k]} />
                {inputs[k].note ? (
                  <p className="cell-note">{inputs[k].note}</p>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {keys.length === 0 ? (
        <p className="empty">Nothing in this category.</p>
      ) : null}
    </section>
  );
}

/* -------------------------------------------------------------------------
 * Comparables — two panels, deliberately apart
 * ---------------------------------------------------------------------- */

export function Comparables({ comparables }) {
  const { deals = [], market_bands: bands = [], coverage_statement: coverage } =
    comparables || {};
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>Comparable transactions</h2>
      </header>
      <p className="coverage">{coverage}</p>

      <div className="comps">
        {deals.map((d) => (
          <article key={d.key} className="comp">
            <h3>{d.name}</h3>
            <p className="comp-meta">
              {d.vintage ? <span className="comp-year">{d.vintage}</span> : null}
              <span>{d.primary_source}</span>
            </p>
            <p className="comp-reasons">{d.match_reasons.join(' · ')}</p>
            <p className="comp-disclosure">
              {d.disclosure.stated} disclosed · {d.disclosure.not_disclosed} not
            </p>
            {d.vintage_warning ? (
              <p className="comp-warning">{d.vintage_warning}</p>
            ) : null}
          </article>
        ))}
      </div>

      <h3 className="subhead">What the market is pricing</h3>
      <p className="subnote">
        These are bands for deals of this shape. They are not attached to any
        transaction above.
      </p>
      <table className="tbl">
        <thead>
          <tr>
            <th>Term</th>
            <th className="r">Range</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {bands.map((b) => (
            <tr key={b.key}>
              <td>{b.label}</td>
              <td className="r num">
                {b.low === b.high
                  ? fmtNumber(b.low, b.unit === 'USD' ? 'USD' : '')
                  : `${fmtNumber(b.low, '')}–${fmtNumber(b.high, '')}`}{' '}
                <span className="unit">{b.unit}</span>
              </td>
              <td className="src">
                <a href={b.source_url} target="_blank" rel="noreferrer noopener">
                  {b.source}
                </a>
                <span> · {b.source_date}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/* -------------------------------------------------------------------------
 * Recommendation
 * ---------------------------------------------------------------------- */

export function Recommendation({ comparison }) {
  const rec = comparison.recommendation;
  const blocked = rec.ranked.filter((r) => !r.feasible);
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>Recommended structure</h2>
        <span className="tag">{rec.priority_label}</span>
      </header>
      <p className="rationale">{rec.rationale}</p>
      {comparison.value_warning ? (
        <p className="value-warning">{comparison.value_warning}</p>
      ) : null}

      {blocked.length ? (
        <>
          <h3 className="subhead">Not available on this deal</h3>
          <ul className="blocked">
            {blocked.map((b) => (
              <li key={b.structure}>
                <strong>{b.label}</strong>
                <span className="gate-id">
                  {b.gates_failed.map((g) => g.gate_id).join(', ')}
                </span>
                <p>{b.blocking_reason}</p>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

/* -------------------------------------------------------------------------
 * Comparison — quantitative rows, then the qualitative band
 * ---------------------------------------------------------------------- */

export function Comparison({ comparison }) {
  const structures = comparison.structures;
  const dims = comparison.dimensions;
  const qual = {};
  comparison.qualitative.forEach((c) => {
    qual[`${c.structure}.${c.dimension}`] = c;
  });

  if (!structures.length) {
    return (
      <section className="panel">
        <header className="panel-head">
          <h2>Comparison</h2>
        </header>
        <p className="empty">No structure survived the screens for this deal.</p>
      </section>
    );
  }

  return (
    <section className="panel panel-wide">
      <header className="panel-head">
        <h2>Comparison</h2>
      </header>
      {comparison.headline_note ? (
        <p className="headline-note">{comparison.headline_note}</p>
      ) : null}

      <div className="scroll-x">
        <table className="tbl tbl-compare">
          <thead>
            <tr>
              <th className="rowhead" />
              {structures.map((s) => (
                <th key={s.key}>{s.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {comparison.quantitative.map((row) => (
              <tr
                key={row.id}
                className={row.id === comparison.headline_metric ? 'headline' : ''}
              >
                <th className="rowhead">{row.label}</th>
                {structures.map((s) => {
                  const cell = row.values[s.key];
                  if (!cell) return <td key={s.key}>—</td>;
                  if (cell.not_meaningful) {
                    return (
                      <td key={s.key} className="nm" title={cell.reason}>
                        not meaningful
                      </td>
                    );
                  }
                  return (
                    <td key={s.key} className="num">
                      {fmtNumber(cell.value, row.unit)}
                    </td>
                  );
                })}
              </tr>
            ))}

            <tr className="band-head">
              <th className="rowhead" colSpan={structures.length + 1}>
                Qualitative — what the numbers do not reach
              </th>
            </tr>

            {dims.map((d) => (
              <tr key={d.id}>
                <th className="rowhead" title={d.question}>
                  {d.label}
                </th>
                {structures.map((s) => {
                  const cell = qual[`${s.key}.${d.id}`];
                  if (!cell) return <td key={s.key}>—</td>;
                  return (
                    <td key={s.key} className="qual" title={cell.reason}>
                      <span className={`rating rating-${cell.rating}`}>
                        {cell.rating}
                      </span>
                      <span className="qual-reason">{cell.reason}</span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------
 * Returns by party
 * ---------------------------------------------------------------------- */

export function Parties({ parties, structures }) {
  const keys = Object.keys(parties || {});
  const [chosen, setChosen] = useState(null);
  if (!keys.length) return null;
  // The selection is derived, not stored: a new analysis can return a
  // different set of structures, and a stored key would point at one that is
  // no longer there.
  const active = keys.includes(chosen) ? chosen : keys[0];
  const setActive = setChosen;
  const current = parties[active];
  const label = (k) => (structures.find((s) => s.key === k) || {}).label || k;

  return (
    <section className="panel panel-wide">
      <header className="panel-head">
        <h2>Returns by party</h2>
        <div className="tabs">
          {keys.map((k) => (
            <button
              key={k}
              className={k === active ? 'on' : ''}
              onClick={() => setActive(k)}
              type="button"
            >
              {label(k)}
            </button>
          ))}
        </div>
      </header>

      {current.conservation && current.conservation.length ? (
        <p className="value-warning">
          Conservation failed: {current.conservation.join('; ')}
        </p>
      ) : (
        <p className="subnote">
          Partner distributions, contributions and book allocations reconcile in
          every period.
        </p>
      )}

      <div className="scroll-x">
        <table className="tbl">
          <thead>
            <tr>
              <th>Party</th>
              <th className="r">Capital in</th>
              <th className="r">IRR</th>
              <th className="r">MOIC</th>
              <th className="r">Payback</th>
              <th>Traced to</th>
            </tr>
          </thead>
          <tbody>
            {current.ledgers.map((l) => {
              const m = l.metrics;
              const invested = l.components && l.components.contributions
                ? l.components.contributions.reduce((a, b) => a + b, 0)
                : -l.cashflow.filter((c) => c < 0).reduce((a, b) => a + b, 0);
              return (
                <tr key={l.party}>
                  <td>
                    <strong>{l.party}</strong>
                    <p className="cell-note">{l.role}</p>
                  </td>
                  <td className="r num">{fmtNumber(invested, 'USD')}</td>
                  <td className="r num">
                    {m.irr === null ? (
                      <span className="nm" title={m.not_meaningful_reason}>
                        n/m
                      </span>
                    ) : (
                      `${(m.irr * 100).toFixed(2)}%`
                    )}
                  </td>
                  <td className="r num">{m.moic === null ? '—' : `${m.moic}x`}</td>
                  <td className="r num">{m.payback_year || '—'}</td>
                  <td className="src">{l.trace}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {current.ledgers.some((l) => l.metrics.not_meaningful_reason) ? (
        <ul className="nm-notes">
          {current.ledgers
            .filter((l) => l.metrics.not_meaningful_reason)
            .map((l) => (
              <li key={l.party}>
                <strong>{l.party}</strong> {l.metrics.not_meaningful_reason}
              </li>
            ))}
        </ul>
      ) : null}
    </section>
  );
}

/* -------------------------------------------------------------------------
 * Structure chart
 * ---------------------------------------------------------------------- */

export function Charts({ charts, structures }) {
  const keys = Object.keys(charts || {});
  const [chosen, setChosen] = useState(null);
  if (!keys.length) return null;
  const active = keys.includes(chosen) ? chosen : keys[0];
  const setActive = setChosen;
  const label = (k) => (structures.find((s) => s.key === k) || {}).label || k;

  return (
    <section className="panel panel-wide">
      <header className="panel-head">
        <h2>Structure chart</h2>
        <div className="tabs">
          {keys.map((k) => (
            <button
              key={k}
              className={k === active ? 'on' : ''}
              onClick={() => setActive(k)}
              type="button"
            >
              {label(k)}
            </button>
          ))}
        </div>
      </header>
      <div
        className="chart"
        dangerouslySetInnerHTML={{ __html: charts[active] || '' }}
      />
      <p className="subnote">
        Generated from the model. Every box is a party the model carries and
        every line a flow it computes.
      </p>
    </section>
  );
}

/* -------------------------------------------------------------------------
 * Chat rail
 * ---------------------------------------------------------------------- */

export function ChatRail({ turns, onSend, busy }) {
  const [text, setText] = useState('');
  return (
    <section className="panel chatrail">
      <header className="panel-head">
        <h2>Argue with it</h2>
      </header>
      <p className="subnote">
        Every answer re-runs the model. Anything that cannot be turned into a
        model change is refused rather than answered.
      </p>
      <ul className="turns">
        {turns.map((t, i) => (
          <li key={i} className={t.understood ? 'ok' : 'refused'}>
            <p className="turn-q">{t.question}</p>
            <p className="turn-a">{t.answer || t.needed}</p>
          </li>
        ))}
      </ul>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!text.trim()) return;
          onSend(text.trim());
          setText('');
        }}
      >
        <input
          type="text"
          value={text}
          placeholder="what if the PPA is 22 years?"
          onChange={(e) => setText(e.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy}>
          Ask
        </button>
      </form>
      <p className="chat-hints">
        try: <code>price $52/MWh</code> · <code>capex $780m</code> ·{' '}
        <code>why not a direct transfer?</code>
      </p>
    </section>
  );
}
