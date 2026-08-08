'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { currentLaw } from '../../lib/api';

const TOPICS = [
  ['eligibility', '§48E / §45Y eligibility and phase-down'],
  ['adders', 'Adders — domestic content and energy community'],
  ['feoc', 'FEOC and the Material Assistance Cost Ratio'],
  ['begin_construction', 'Begin construction — and the litigation'],
  ['depreciation', 'Depreciation and basis'],
  ['transfer', 'Transferability — §6418 and §6417'],
  ['market', 'Market benchmarks used as defaults'],
];

const CONF_BADGE = {
  VERIFIED: 'win',
  HIGH: 'win',
  MEDIUM: 'info',
  PROVISIONAL: 'warn',
  PLACEHOLDER: 'danger',
};

function Conf({ c }) {
  return <span className={'badge ' + (CONF_BADGE[c] || '')}>{(c || '').toLowerCase()}</span>;
}

export default function CurrentLawPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    currentLaw()
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e.message || 'Could not load the citation registry.'));
    return () => {
      live = false;
    };
  }, []);

  const byTopic = useMemo(() => {
    if (!data) return [];
    const known = new Set(TOPICS.map((t) => t[0]));
    const groups = TOPICS.map(([key, label]) => [
      label,
      data.citations.filter((c) => c.topic === key),
    ]);
    const other = data.citations.filter((c) => !c.topic || !known.has(c.topic));
    if (other.length) groups.push(['Other', other]);
    return groups.filter(([, rows]) => rows.length);
  }, [data]);

  const counts = useMemo(() => {
    if (!data) return null;
    const c = { VERIFIED: 0, PROVISIONAL: 0, PLACEHOLDER: 0 };
    data.citations.forEach((x) => {
      const k = x.confidence === 'HIGH' ? 'VERIFIED' : x.confidence;
      if (c[k] !== undefined) c[k] += 1;
    });
    return c;
  }, [data]);

  if (error) {
    return (
      <main>
        <div className="pagehead">
          <h1>Current law</h1>
        </div>
        <div className="callout blocking">
          <div className="ct">Could not load the citation registry</div>
          {error}
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main>
        <div className="pagehead">
          <div className="kicker">the rulebook</div>
          <h1>Current law</h1>
        </div>
        <section className="panel">
          <div className="state">
            <div className="bar" />
            Loading the citation registry…
          </div>
        </section>
      </main>
    );
  }

  const lit = data.litigation;

  return (
    <main>
      <div className="pagehead">
        <div className="kicker">the rulebook · verified {data.law_verified_on}</div>
        <h1>Current law</h1>
        <p>
          Every tax rule Structura implements, with its authority, what it means in plain English,
          where the statement comes from, and the date it was last checked. Rules whose confidence
          is below <em>verified</em> are listed separately below.
        </p>
      </div>

      <div className="stats" style={{ border: '1px solid var(--line)', borderRadius: 4, marginBottom: 14 }}>
        <div className="stat">
          <div className="k">Rules registered</div>
          <div className="v">{data.citations.length}</div>
        </div>
        <div className="stat">
          <div className="k">Verified</div>
          <div className="v" style={{ color: 'var(--win)' }}>
            {counts.VERIFIED}
          </div>
          <div className="n">primary text or the verified rulebook</div>
        </div>
        <div className="stat">
          <div className="k">Provisional</div>
          <div className="v" style={{ color: 'var(--warn)' }}>
            {counts.PROVISIONAL}
          </div>
          <div className="n">believed correct, not confirmed here</div>
        </div>
        <div className="stat">
          <div className="k">Placeholder</div>
          <div className="v" style={{ color: 'var(--danger)' }}>
            {counts.PLACEHOLDER}
          </div>
          <div className="n">structure only — the number is a stand-in</div>
        </div>
        <div className="stat">
          <div className="k">Law verified on</div>
          <div className="v sm">{data.law_verified_on}</div>
        </div>
      </div>

      {/* ---------------- litigation ---------------- */}
      <section className="panel">
        <header>
          <h2>⚖ Active litigation — begin construction</h2>
          <span className="spacer" />
          <span className="badge danger">{lit.status}</span>
        </header>
        <div className="body">
          <div className="callout blocking">
            <div className="ct">
              <span className="badge danger">decided {lit.decided}</span>
              {lit.case}
            </div>
            <p style={{ margin: '6px 0 0', color: 'var(--text)' }}>
              <strong>{lit.effect}.</strong>
            </p>
            <p style={{ margin: '6px 0 0' }}>{lit.reasoning}</p>
          </div>

          <div className="split2" style={{ marginTop: 12 }}>
            <div className="callout">
              <div className="ct">
                <code>vacated</code> <span className="badge win">law today</span>
              </div>
              Notice 2025-42 has no effect. A wind or solar facility above 1.5 MW may establish
              begin-construction with the <strong>5% cost safe harbor</strong> — the cheaper and far
              more common route — as well as by the Physical Work Test.
            </div>
            <div className="callout high">
              <div className="ct">
                <code>reinstated_on_appeal</code> <span className="badge warn">scenario</span>
              </div>
              The government prevails on appeal and the notice returns. The 5% safe harbor closes for
              wind and solar above 1.5 MW; begin-construction must be established by the{' '}
              <strong>Physical Work Test</strong> alone. A project that cannot do so misses the
              2026-07-04 cliff and is thrown onto the 2027-12-31 placed-in-service backstop — or gets
              nothing.
            </div>
          </div>

          <div className="callout info" style={{ marginTop: 12 }}>
            <div className="ct">What the toggle does</div>
            {lit.toggle_explanation}
          </div>

          <p style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 12, marginBottom: 0 }}>
            Court: {lit.court}. Toggle values on <code>/api/compare</code>:{' '}
            {lit.toggle_values.map((v) => (
              <code key={v} style={{ marginRight: 6 }}>
                {v}
              </code>
            ))}
            — set it on the{' '}
            <Link href="/">structure selector</Link>.
          </p>
        </div>
      </section>

      {/* ---------------- unverified ---------------- */}
      <section className="panel">
        <header>
          <h2>What is not verified</h2>
          <span className="sub">
            {data.unverified.length} items — read this before quoting any number
          </span>
        </header>
        <div className="body">
          <p style={{ color: 'var(--text-dim)', marginTop: 0 }}>
            Where a threshold or rule detail could not be sourced, the <strong>structure</strong> was
            implemented and the <strong>number</strong> was made a clearly-named placeholder. Nothing
            was invented to look complete. Every item here corresponds to a registry entry below
            whose confidence is <em>provisional</em> or <em>placeholder</em>, and a test asserts the
            two stay in sync — you cannot add an uncertain rule without listing it.
          </p>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Item</th>
                  <th>What is not known</th>
                  <th>Why it matters</th>
                  <th className="r">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {data.unverified.map((u) => (
                  <tr key={u.item}>
                    <td style={{ minWidth: 170 }}>
                      <span className="sname" style={{ whiteSpace: 'normal' }}>
                        {u.item}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-dim)', minWidth: 260 }}>{u.detail}</td>
                    <td style={{ color: 'var(--text-dim)', minWidth: 240 }}>{u.impact}</td>
                    <td className="r">
                      <Conf c={u.confidence || 'PLACEHOLDER'} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ---------------- registry ---------------- */}
      {byTopic.map(([label, rows]) => (
        <section className="panel" key={label}>
          <header>
            <h2>{label}</h2>
            <span className="sub">{rows.length} rules</span>
          </header>
          <div className="body flush">
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>Authority</th>
                    <th>Rule</th>
                    <th>Source of this statement</th>
                    <th className="r">Verified</th>
                    <th className="r">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c) => (
                    <tr key={c.id}>
                      <td style={{ minWidth: 200 }}>
                        <span className="sname" style={{ whiteSpace: 'normal' }}>
                          {c.authority}
                        </span>
                        <div className="srcnote">{c.id}</div>
                      </td>
                      <td style={{ minWidth: 280 }}>
                        <strong style={{ color: 'var(--text)' }}>{c.headline}</strong>
                        <div style={{ color: 'var(--text-dim)', marginTop: 2 }}>{c.summary}</div>
                      </td>
                      <td style={{ color: 'var(--text-faint)', minWidth: 200 }}>{c.source}</td>
                      <td className="r num">{c.verified_on}</td>
                      <td className="r">
                        <Conf c={c.confidence} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ))}

      <div className="callout" style={{ marginTop: 14 }}>
        <div className="ct">Not advice</div>
        Illustrative modelling tool. Not tax, legal, accounting or investment advice. Nothing on this
        page is a representation that any project qualifies for any credit.
      </div>
    </main>
  );
}
