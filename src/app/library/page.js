'use client';

import { useEffect, useMemo, useState } from 'react';

import { Value } from '../../components/Provenance';
import { library } from '../../lib/api';

const FAMILIES = [
  ['all', 'All'],
  ['solar', 'Solar'],
  ['storage', 'Storage'],
  ['wind', 'Wind'],
  ['digital', 'Data centre and AI compute'],
  ['rng', 'RNG'],
  ['transmission', 'Transmission'],
];

const FIELDS = [
  ['sponsor', 'Sponsor'],
  ['total_quantum', 'Total quantum'],
  ['close_date', 'Closed'],
  ['capacity', 'Capacity'],
  ['location', 'Location'],
  ['offtake', 'Offtake'],
  ['credit_route', 'Credit route'],
];

export default function Library() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [family, setFamily] = useState('all');

  useEffect(() => {
    library()
      .then(setData)
      .catch((e) => setError(e.message || 'The library is unreachable.'));
  }, []);

  const deals = useMemo(() => {
    if (!data) return [];
    return family === 'all'
      ? data.deals
      : data.deals.filter((d) => d.family === family);
  }, [data, family]);

  return (
    <main className="page">
      <section className="hero">
        <h1>Transaction library</h1>
        <p>
          Every transaction here was verified against a public source, and every
          field carries the URL it came from. Where a source did not disclose
          something, the record says so rather than leaving a blank or inferring
          a figure. Pricing is almost never disclosed on a project financing;
          that is what the market bands are for.
        </p>
      </section>

      {error ? <p className="error">{error}</p> : null}

      {data ? (
        <>
          <div className="lib-filters">
            {FAMILIES.map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`chip${family === key ? ' on' : ''}`}
                onClick={() => setFamily(key)}
              >
                {label}
              </button>
            ))}
            <span className="dealform-presets-label">
              {deals.length} of {data.count}
            </span>
          </div>

          <div className="lib-grid">
            {deals.map((d) => (
              <article key={d.key} className="lib-card">
                <h3>{d.name}</h3>
                <p className="lib-meta">
                  {d.vintage || '—'} · {d.technology} · {d.disclosure.stated}{' '}
                  disclosed / {d.disclosure.not_disclosed} not
                </p>
                <dl>
                  {FIELDS.map(([key, label]) => (
                    <div key={key} style={{ display: 'contents' }}>
                      <dt>{label}</dt>
                      <dd>
                        <Value cell={d.fields[key]} compact />
                      </dd>
                    </div>
                  ))}
                </dl>
                {d.lenders.length ? (
                  <p className="cell-note">Lenders: {d.lenders.join(', ')}</p>
                ) : null}
              </article>
            ))}
          </div>
        </>
      ) : error ? null : (
        <p className="empty">Loading the library…</p>
      )}
    </main>
  );
}
