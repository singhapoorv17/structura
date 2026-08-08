/** Number formatting. All rates are decimals; all money is USD. */

export function pct(v, dp = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return (v * 100).toFixed(dp) + '%';
}

export function bps(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const n = Math.round(v * 10000);
  return (n > 0 ? '+' : '') + n + ' bps';
}

export function usd(v, { dp = 0 } = {}) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const sign = v < 0 ? '-' : '';
  const a = Math.abs(v);
  return sign + '$' + a.toLocaleString('en-US', { maximumFractionDigits: dp });
}

export function usdM(v, dp = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const sign = v < 0 ? '-' : '';
  const a = Math.abs(v);
  if (a >= 1e9) return sign + '$' + (a / 1e9).toFixed(2) + 'bn';
  if (a >= 1e6) return sign + '$' + (a / 1e6).toFixed(dp) + 'm';
  if (a >= 1e3) return sign + '$' + (a / 1e3).toFixed(0) + 'k';
  return sign + '$' + a.toFixed(0);
}

export function num(v, dp = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return Number(v).toFixed(dp);
}

export function years(v, dp = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return Number(v).toFixed(dp) + ' yr';
}

export function xmult(v, dp = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return Number(v).toFixed(dp) + 'x';
}

/** Format a `why_this_wins` driver value according to its declared unit. */
export function driverValue(v, unit) {
  if (v === null || v === undefined) return '—';
  switch (unit) {
    case 'rate':
      return pct(v);
    case 'usd':
      return usdM(v);
    case 'years':
      return years(v);
    case 'x':
      return xmult(v);
    default:
      return typeof v === 'number' ? num(v) : String(v);
  }
}

export function driverDelta(v, unit) {
  if (v === null || v === undefined) return '—';
  if (unit === 'rate') return bps(v);
  const s = driverValue(Math.abs(v), unit);
  return (v > 0 ? '+' : v < 0 ? '-' : '') + s;
}
