'use client';

const ORDER = ['BLOCKING', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const CLASS = {
  BLOCKING: 'blocking',
  HIGH: 'high',
  MEDIUM: '',
  LOW: '',
  INFO: 'info',
};
const BADGE = {
  BLOCKING: 'danger',
  HIGH: 'warn',
  MEDIUM: 'warn',
  LOW: '',
  INFO: 'info',
};

/**
 * Risks and warnings.
 *
 * Contract rule: `severity: "BLOCKING"` renders prominently in red and is never
 * collapsed. Every `warnings` string is displayed verbatim somewhere reachable —
 * placeholders must never be silently swallowed.
 */
export default function RiskPanel({ result }) {
  const collected = [];

  (result.risks || []).forEach((r) => collected.push({ ...r, scope: 'Project' }));
  (result.ranked || []).forEach((row) => {
    (row.risks || []).forEach((r) => collected.push({ ...r, scope: row.label }));
  });

  const blocking = collected.filter((r) => r.severity === 'BLOCKING');
  const rest = collected
    .filter((r) => r.severity !== 'BLOCKING')
    .sort((a, b) => ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity));

  const structureWarnings = [];
  (result.ranked || []).forEach((row) => {
    (row.warnings || []).forEach((w) => structureWarnings.push(row.label + ': ' + w));
  });
  const warnings = [...(result.warnings || []), ...structureWarnings];
  const breaches = result.capital_account_breaches || [];

  return (
    <section className="panel">
      <header>
        <h2>Risks &amp; warnings</h2>
        <span className="sub">
          {blocking.length} blocking · {rest.length} other · {warnings.length} assumptions flagged
        </span>
      </header>
      <div className="body">
        {blocking.length ? (
          <div style={{ marginBottom: 12 }}>
            {blocking.map((r, i) => (
              <div className="callout blocking" key={r.code + i}>
                <div className="ct">
                  <span className="badge danger">blocking</span>
                  <span>{r.scope}</span>
                  <code style={{ color: 'var(--text-faint)' }}>{r.code}</code>
                </div>
                {r.message}
              </div>
            ))}
          </div>
        ) : (
          <div className="callout win" style={{ marginBottom: 12 }}>
            <div className="ct">
              <span className="badge win">clear</span>
              No blocking risks
            </div>
            Nothing in this run voids the credit or breaks the funding stack. That is not the same as
            the deal being financeable — read the flagged assumptions below.
          </div>
        )}

        {breaches.length ? (
          <div style={{ marginBottom: 12 }}>
            {breaches.map((b, i) => (
              <div className="callout high" key={i}>
                <div className="ct">
                  <span className="badge warn">§704(b)</span>
                  Capital account below floor — {b.partner || 'partner'}
                </div>
                {b.detail ||
                  'A distribution drove a capital account below its DRO floor. Treas. Reg. §1.704-1(b)(2)(ii)(d) would cure this with a qualified income offset; Structura reports it rather than curing it.'}
              </div>
            ))}
          </div>
        ) : null}

        {rest.length ? (
          <details className="disclose" open>
            <summary>{rest.length} non-blocking risks across the five structures</summary>
            <div className="dbody">
              {rest.map((r, i) => (
                <div className={'callout ' + CLASS[r.severity]} key={r.code + i}>
                  <div className="ct">
                    <span className={'badge ' + BADGE[r.severity]}>
                      {(r.severity || '').toLowerCase()}
                    </span>
                    <span>{r.scope}</span>
                    <code style={{ color: 'var(--text-faint)' }}>{r.code}</code>
                  </div>
                  {r.message}
                </div>
              ))}
            </div>
          </details>
        ) : null}

        {warnings.length ? (
          <details className="disclose">
            <summary>
              {warnings.length} assumptions flagged — placeholders, simplifications and declared
              limits
            </summary>
            <div className="dbody">
              <ul className="warnlist">
                {warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          </details>
        ) : null}
      </div>
    </section>
  );
}
