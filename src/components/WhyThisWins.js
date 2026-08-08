'use client';

import { bps, driverDelta, driverValue, pct, usdM } from '../lib/format';

function labelFor(ranked, key) {
  const r = ranked.find((x) => x.key === key);
  return r ? r.label : key;
}

export default function WhyThisWins({ why, ranked }) {
  if (!why) return null;
  const winnerLabel = labelFor(ranked, why.winner);
  const runnerLabel = why.runner_up ? labelFor(ranked, why.runner_up) : null;
  const onIrr = why.primary_metric === 'sponsor_after_tax_irr';

  return (
    <section className="panel">
      <header>
        <h2>Why this wins</h2>
        <span className="sub">
          ranked on {onIrr ? 'sponsor after-tax IRR' : 'sponsor NPV'}
        </span>
      </header>

      <div className="stats">
        <div className="stat">
          <div className="k">Winner</div>
          <div className="v sm">{winnerLabel}</div>
          <div className="n">
            {onIrr ? pct(why.winner_value) : usdM(why.winner_value)} on the primary metric
          </div>
        </div>
        <div className="stat">
          <div className="k">Runner-up</div>
          <div className="v sm">{runnerLabel || '—'}</div>
          <div className="n">
            {why.runner_up_value != null ? pct(why.runner_up_value) : 'no second structure with a meaningful rate'}
          </div>
        </div>
        <div className="stat">
          <div className="k">Margin</div>
          <div className="v">{why.margin != null ? bps(why.margin) : '—'}</div>
          <div className="n">winner over runner-up</div>
        </div>
      </div>

      <div className="body">
        {why.drivers && why.drivers.length ? (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Driver</th>
                  <th className="r">{winnerLabel}</th>
                  <th className="r">{runnerLabel || 'runner-up'}</th>
                  <th className="r">Delta</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {why.drivers.map((d) => {
                  const better =
                    d.delta == null
                      ? null
                      : d.higher_is_better
                        ? d.delta > 0
                        : d.delta < 0;
                  return (
                    <tr key={d.name}>
                      <td>
                        <span className="sname">{d.name}</span>
                      </td>
                      <td className="r num">{driverValue(d.winner_value, d.unit)}</td>
                      <td className="r num">{driverValue(d.runner_up_value, d.unit)}</td>
                      <td
                        className="r num"
                        style={{
                          color:
                            better === null
                              ? 'var(--text-faint)'
                              : better
                                ? 'var(--win)'
                                : 'var(--warn)',
                        }}
                      >
                        {driverDelta(d.delta, d.unit)}
                      </td>
                      <td style={{ color: 'var(--text-dim)', minWidth: 260 }}>{d.note}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: 'var(--text-dim)', margin: 0 }}>
            No runner-up with a meaningful rate, so no driver comparison is produced.
          </p>
        )}

        {why.disqualified && why.disqualified.length ? (
          <div style={{ marginTop: 12 }}>
            {why.disqualified.map((d) => (
              <div className="callout" key={d.structure}>
                <div className="ct">
                  <span className="badge danger">disqualified</span>
                  {labelFor(ranked, d.structure)}
                </div>
                {d.reason}
              </div>
            ))}
          </div>
        ) : null}

        {why.tie_breaks && why.tie_breaks.length ? (
          <div style={{ marginTop: 12 }}>
            {why.tie_breaks.map((t, i) => (
              <div className="callout info" key={i}>
                <div className="ct">Tie-break</div>
                {typeof t === 'string' ? t : JSON.stringify(t)}
              </div>
            ))}
          </div>
        ) : null}

        {why.caveats && why.caveats.length ? (
          <details className="disclose" style={{ marginTop: 12 }} open>
            <summary>
              {why.caveats.length} caveat{why.caveats.length === 1 ? '' : 's'} on this ranking
            </summary>
            <div className="dbody">
              <ul className="warnlist">
                {why.caveats.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          </details>
        ) : null}
      </div>
    </section>
  );
}
