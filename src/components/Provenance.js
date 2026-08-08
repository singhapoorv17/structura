'use client';

/**
 * Badges and small readouts for the provenance system.
 *
 * Every number on the screen carries where it came from. These are the pieces
 * that render that: the badge itself, the confidence header, and the value
 * cell that shows a range where the source published one.
 */

const LABEL = {
  stated: 'stated',
  benchmark: 'benchmark',
  assumed: 'assumed',
  not_disclosed: 'not disclosed',
};

const TITLE = {
  stated: 'Taken from a cited public source.',
  benchmark: 'A cited market figure, or derived from named comparable transactions.',
  assumed: 'A tool default with no external source.',
  not_disclosed: 'The source exists and does not say.',
};

export function Badge({ kind }) {
  return (
    <span className={`prov prov-${kind}`} title={TITLE[kind]}>
      {LABEL[kind] || kind}
    </span>
  );
}

export function Confidence({ counts }) {
  if (!counts) return null;
  const order = ['stated', 'benchmark', 'assumed', 'not_disclosed'];
  const total = counts.total || 1;
  return (
    <div className="confidence">
      <div className="confidence-bar" aria-hidden="true">
        {order.map((k) =>
          counts[k] ? (
            <span
              key={k}
              className={`seg seg-${k}`}
              style={{ width: `${(counts[k] / total) * 100}%` }}
            />
          ) : null
        )}
      </div>
      <div className="confidence-keys">
        {order.map((k) =>
          counts[k] ? (
            <span key={k} className="confidence-key">
              <i className={`swatch seg-${k}`} />
              {counts[k]} {LABEL[k]}
            </span>
          ) : null
        )}
      </div>
    </div>
  );
}

/**
 * Money, rates and plain quantities all reach this, so the unit decides the
 * shape. "USD per year" is still money; "$/MWh" is a price and wants cents.
 */
function fmtNumber(value, unit) {
  if (value === null || value === undefined) return '—';
  if (typeof value !== 'number') return String(value);
  const u = unit || '';

  if (u.includes('USD')) {
    const abs = Math.abs(value);
    if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}bn`;
    if (abs >= 1e6) return `$${(value / 1e6).toFixed(1)}m`;
    if (abs >= 1e3) return `$${(value / 1e3).toFixed(0)}k`;
    return `$${value.toFixed(0)}`;
  }
  if (u === '%') return `${(value * 100).toFixed(2)}%`;
  if (u.startsWith('$/') || u.includes('per credit dollar')) {
    return `$${value.toFixed(2)}`;
  }
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  return String(Number(value.toFixed(4)));
}

/** The unit as a suffix, where the formatted number does not already carry it. */
function suffix(unit) {
  const u = unit || '';
  if (!u || u === '%' || u.includes('USD') || u.includes('per credit dollar')) {
    return '';
  }
  if (u.startsWith('$/')) return u.slice(1);
  return u;
}

/** A single provenanced value: the number, its badge, its range, its source. */
export function Value({ cell, unit, compact }) {
  if (!cell) return <span className="val-none">—</span>;
  const kind = cell.provenance;
  const u = cell.unit || unit;

  if (kind === 'not_disclosed') {
    return (
      <span className="val val-nd" title={cell.reason}>
        not disclosed
      </span>
    );
  }

  const hasRange =
    cell.low !== null && cell.low !== undefined && cell.low !== cell.high;

  return (
    <span className="val">
      <span className="num">
        {fmtNumber(cell.value, u)}
        {suffix(u) ? (
          <span className="unit">{suffix(u).startsWith('/') ? '' : ' '}{suffix(u)}</span>
        ) : null}
      </span>
      {hasRange ? (
        <span className="val-range">
          {fmtNumber(cell.low, u)}–{fmtNumber(cell.high, u)}
        </span>
      ) : null}
      {compact ? null : <Badge kind={kind} />}
      {cell.source && !compact ? (
        <span className="val-src" title={cell.note || ''}>
          {cell.source_url && cell.source_url.startsWith('http') ? (
            <a href={cell.source_url} target="_blank" rel="noreferrer noopener">
              {cell.source}
            </a>
          ) : (
            cell.source
          )}
          {cell.source_date ? ` · ${cell.source_date}` : ''}
          {cell.source_date_unknown ? ' · date not captured' : ''}
        </span>
      ) : null}
    </span>
  );
}

export { fmtNumber };
