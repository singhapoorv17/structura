'use client';

import { pct, usdM, xmult, years } from '../lib/format';

/**
 * The structure comparison table.
 *
 * The hard rule (API_CONTRACT.md, Conventions): where `irr_is_meaningful` is
 * false the IRR must NOT be a headline figure. It is struck through and greyed,
 * the reason is carried inline and on the title attribute, and the row leads
 * with `sponsor_npv` instead.
 */
export default function ComparisonTable({ ranked }) {
  const feasible = ranked.filter((r) => r.feasible);
  const infeasible = ranked.filter((r) => !r.feasible);

  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th className="rank">#</th>
            <th>Structure</th>
            <th className="r">Sponsor after-tax IRR</th>
            <th className="r">Sponsor NPV</th>
            <th className="r">Effective cost of capital</th>
            <th className="r">Sponsor equity</th>
            <th className="r">Third-party capital</th>
            <th className="r">Total capital</th>
            <th className="r">Flip year</th>
            <th className="r">Feasibility</th>
          </tr>
        </thead>
        <tbody>
          {feasible.map((r, i) => {
            const winner = i === 0;
            const meaningful = r.irr_is_meaningful;
            return (
              <tr key={r.key} className={winner ? 'winner' : ''}>
                <td className="rank">{r.rank}</td>
                <td>
                  <span className="sname">{r.label}</span>{' '}
                  {winner ? <span className="badge win">winner</span> : null}
                </td>

                <td className="r num">
                  {meaningful ? (
                    <span className={'shead' + (winner ? ' win' : '')}>
                      {pct(r.sponsor_after_tax_irr)}
                    </span>
                  ) : (
                    <>
                      <span
                        className="struck"
                        title={r.irr_not_meaningful_reason || 'Not a meaningful rate.'}
                      >
                        {pct(r.sponsor_after_tax_irr)}
                      </span>{' '}
                      <span className="badge warn">not meaningful</span>
                      <span className="notmeaningful">{r.irr_not_meaningful_reason}</span>
                    </>
                  )}
                </td>

                <td className="r num">
                  <span className={meaningful ? '' : 'shead'}>{usdM(r.sponsor_npv)}</span>
                  {!meaningful ? (
                    <span className="notmeaningful" style={{ color: 'var(--text-faint)' }}>
                      ranked on NPV
                    </span>
                  ) : null}
                </td>

                <td className="r num">{pct(r.effective_cost_of_capital)}</td>
                <td className="r num">{usdM(r.sponsor_equity_required)}</td>
                <td className="r num">{usdM(r.third_party_capital_raised)}</td>
                <td className="r num">{usdM(r.total_capital_raised)}</td>
                <td className="r num">{r.flip_year != null ? years(r.flip_year) : '—'}</td>
                <td className="r">
                  <span className="badge win">feasible</span>
                </td>
              </tr>
            );
          })}

          {infeasible.map((r) => (
            <tr key={r.key} className="dim">
              <td className="rank">—</td>
              <td>
                <span className="sname">{r.label}</span>
              </td>
              <td className="r num">—</td>
              <td className="r num">—</td>
              <td className="r num">—</td>
              <td className="r num">—</td>
              <td className="r num">—</td>
              <td className="r num">—</td>
              <td className="r num">—</td>
              <td className="r">
                <span className="badge danger">infeasible</span>
              </td>
            </tr>
          ))}

          {infeasible.map((r) => (
            <tr key={r.key + '-why'} className="infeasible-row">
              <td />
              <td colSpan={9}>
                <strong style={{ color: 'var(--text-dim)' }}>{r.label} —</strong>{' '}
                {r.infeasible_reason}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CashTimingStrip({ ranked }) {
  const rows = ranked.filter((r) => r.feasible && r.cash_timing);
  if (!rows.length) return null;
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th>Structure</th>
            <th className="r">Cash-weighted average life</th>
            <th className="r">Share of sponsor cash by year 5</th>
            <th className="r">Credit retained</th>
            <th className="r">Credit transferred (§6418)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td>
                <span className="sname">{r.label}</span>
              </td>
              <td className="r num">{xmult(r.cash_timing.cash_weighted_average_years, 1).replace('x', ' yr')}</td>
              <td className="r num">{pct(r.cash_timing.share_by_year_5, 0)}</td>
              <td className="r num">{usdM(r.credit_retained)}</td>
              <td className="r num">{usdM(r.credit_transferred)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
