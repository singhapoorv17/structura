'use client';

import { pct, usd, usdM, xmult } from '../lib/format';

const CONSTRAINT_NOTE = {
  DSCR:
    'The minimum debt service coverage test is the binding constraint — the loan is sized by coverage, not by the gearing cap or the tail. Move the target DSCR and the quantum moves with it.',
  GEARING:
    'The gearing cap binds before the coverage test does, so achieved DSCR sits above the market floor. That headroom follows from the ITC: a 30% §48E credit is a source, not a return, and it displaces equity. In the market the headroom is taken as back-leverage at the holdco, which Structura does not model.',
  LLCR: 'The loan life coverage ratio binds — the lender is constrained by the present value of cash over the debt term rather than by any single year.',
  PLCR: 'The project life coverage ratio binds — the tail beyond the debt term is what limits the quantum.',
  TENOR: 'The maximum tenor binds; the loan amortises faster than coverage would require.',
};

export function SourcesAndUses({ su, tax }) {
  if (!su) return null;
  const sources =
    (su.debt || 0) + (su.third_party_equity || 0) + (su.sponsor_equity || 0);
  const reconciles = Math.abs(sources - (su.funding_requirement || 0)) < 1000;

  return (
    <section className="panel">
      <header>
        <h2>Sources &amp; uses</h2>
        <span className="sub">winning structure</span>
      </header>
      <div className="body">
        <dl className="kv">
          <dt>Senior debt</dt>
          <dd>{usd(su.debt)}</dd>
          <dt>Third-party equity</dt>
          <dd>{usd(su.third_party_equity)}</dd>
          <dt>Sponsor equity</dt>
          <dd>{usd(su.sponsor_equity)}</dd>
          <dt className="total">Total sources</dt>
          <dd className="total">{usd(sources)}</dd>
        </dl>

        <dl className="kv" style={{ marginTop: 14 }}>
          <dt className="total" style={{ marginTop: 0 }}>
            Funding requirement (uses)
          </dt>
          <dd className="total" style={{ marginTop: 0 }}>
            {usd(su.funding_requirement)}
          </dd>
        </dl>

        <div className={'callout ' + (reconciles ? 'win' : 'blocking')} style={{ marginTop: 12 }}>
          <div className="ct">
            <span className={'badge ' + (reconciles ? 'win' : 'danger')}>
              {reconciles ? 'reconciled' : 'oversubscribed'}
            </span>
            Sources {reconciles ? '=' : '≠'} uses
          </div>
          {reconciles
            ? 'Capex plus IDC, fees and funded reserves is matched exactly. An over-sized commitment does not silently floor sponsor equity at zero — it raises a BLOCKING risk naming the excess.'
            : 'Sources exceed uses by ' +
              usd(sources - su.funding_requirement) +
              '. This is a funding failure, not a rounding artefact.'}
        </div>

        {su.post_cod_monetisation ? (
          <div className="callout info" style={{ marginTop: 8 }}>
            <div className="ct">Post-COD monetisation {usdM(su.post_cod_monetisation)}</div>
            Deliberately excluded from every source total. A §6418 credit does not exist until the
            property is placed in service, so its sale cannot fund construction — the proceeds are a
            reimbursement of committed capital, not construction capital.
          </div>
        ) : null}

        {tax ? (
          <dl className="kv" style={{ marginTop: 14 }}>
            <dt>Credit section</dt>
            <dd>{tax.credit_section || 'none'}</dd>
            <dt>Credit rate</dt>
            <dd>{tax.credit_rate ? pct(tax.credit_rate, 0) : '—'}</dd>
            <dt>Credit value</dt>
            <dd>{usd(tax.credit_value)}</dd>
            <dt>FEOC / MACR gate</dt>
            <dd style={{ color: tax.feoc_pass ? 'var(--win)' : 'var(--danger)' }}>
              {tax.feoc_pass ? 'PASS' : 'FAIL'}
            </dd>
            <dt>Adders applied</dt>
            <dd>{tax.adders && tax.adders.length ? tax.adders.join(', ') : 'none'}</dd>
          </dl>
        ) : null}

        {tax && tax.eligibility_path ? (
          <p style={{ color: 'var(--text-dim)', fontSize: 12, marginTop: 10, marginBottom: 0 }}>
            {tax.eligibility_path}
          </p>
        ) : null}

        {tax && tax.warnings && tax.warnings.length ? (
          <ul className="warnlist" style={{ marginTop: 10 }}>
            {tax.warnings.map((w, i) => (
              <li key={i} style={{ color: 'var(--warn)' }}>
                {w}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}

export function DebtSummary({ debt }) {
  if (!debt) return null;
  const note = CONSTRAINT_NOTE[debt.binding_constraint] || null;
  return (
    <section className="panel">
      <header>
        <h2>Debt summary</h2>
        <span className="sub">one sizing serves all five structures</span>
      </header>

      <div className="stats">
        <div className="stat">
          <div className="k">Quantum</div>
          <div className="v">{usdM(debt.quantum)}</div>
        </div>
        <div className="stat">
          <div className="k">Gearing</div>
          <div className="v">{pct(debt.gearing, 1)}</div>
        </div>
        <div className="stat">
          <div className="k">Minimum DSCR</div>
          <div className="v">{xmult(debt.min_dscr)}</div>
        </div>
        <div className="stat">
          <div className="k">LLCR</div>
          <div className="v">{xmult(debt.llcr)}</div>
        </div>
        <div className="stat">
          <div className="k">PLCR</div>
          <div className="v">{xmult(debt.plcr)}</div>
        </div>
      </div>

      <div className="body">
        <div className="callout info">
          <div className="ct">
            <span className="badge info">binding constraint</span>
            {debt.binding_constraint}
          </div>
          {note}
        </div>
      </div>
    </section>
  );
}
