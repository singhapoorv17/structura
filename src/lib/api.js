/**
 * The single switch between the real Python serverless layer and the local
 * mock. Nothing else in the app knows whether the API exists.
 *
 * Mode resolution:
 *   NEXT_PUBLIC_API_MODE = "live" → always hit /api/*, never fall back.
 *   NEXT_PUBLIC_API_MODE = "mock" → never hit the network.
 *   unset (default)              → try /api/*, fall back to the mock if the
 *                                  endpoint is absent or unreachable.
 *
 * Under the default, the page renders end to end whether or not the API is
 * reachable. Every response carries `_source: 'live' | 'mock'` so the UI can
 * say which it used.
 */

import { mockCompare, mockCurrentLaw, mockReferenceDeals } from './mockData';

const MODE = process.env.NEXT_PUBLIC_API_MODE || 'auto';
const BASE = process.env.NEXT_PUBLIC_API_BASE || '';

export const API_MODE = MODE;

function url(path) {
  return BASE ? BASE.replace(/\/$/, '') + path : path;
}

async function tryJson(path, init) {
  const res = await fetch(url(path), {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init && init.headers) },
  });
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body.error || body.detail || '';
    } catch (e) {
      detail = res.statusText;
    }
    const err = new Error(detail || 'Request failed with status ' + res.status);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Live-first with mock fallback. A 4xx from a *present* endpoint is a real
 * validation error and is re-thrown; only an absent or unreachable endpoint
 * falls back.
 */
async function withFallback(path, init, mockFn) {
  if (MODE === 'mock') return { ...mockFn(), _source: 'mock' };
  try {
    const data = await tryJson(path, init);
    return { ...data, _source: 'live' };
  } catch (err) {
    const absent = err.status === 404 || err.status === 405 || err.status === undefined;
    if (MODE === 'live' || !absent) throw err;
    return { ...mockFn(), _source: 'mock', _fallback_reason: err.message || 'API not reachable' };
  }
}

/** POST /api/compare */
export async function compare(payload) {
  const t0 = typeof performance !== 'undefined' ? performance.now() : Date.now();
  const out = await withFallback(
    '/api/compare',
    { method: 'POST', body: JSON.stringify(payload) },
    () => mockCompare(payload)
  );
  const t1 = typeof performance !== 'undefined' ? performance.now() : Date.now();
  if (!out.compute_ms) out.compute_ms = Math.round(t1 - t0);
  return out;
}

/** GET /api/reference-deals */
export async function referenceDeals() {
  return withFallback('/api/reference-deals', { method: 'GET' }, mockReferenceDeals);
}

/** GET /api/current-law */
export async function currentLaw() {
  return withFallback('/api/current-law', { method: 'GET' }, mockCurrentLaw);
}

/**
 * POST /api/export → .xlsx bytes. Not mocked: a placeholder workbook would not
 * recalculate, so an export failure is surfaced instead.
 */
export async function exportWorkbook(payload) {
  const res = await fetch(url('/api/export'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    let msg = 'Export failed (HTTP ' + res.status + ').';
    if (res.status === 404 || res.status === 405) {
      msg =
        'The Excel export endpoint is not available in this environment. ' +
        'The workbook is generated server-side by openpyxl — it is the one thing that cannot be faked in the browser.';
    } else if (res.status === 413) {
      msg = 'The generated workbook exceeds the 4.5 MB response cap. Reduce the project life or tenor and retry.';
    } else {
      try {
        const body = await res.json();
        if (body.error) msg = body.error;
      } catch (e) {
        /* keep the generic message */
      }
    }
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }

  const blob = await res.blob();
  const disposition = res.headers.get('Content-Disposition') || '';
  const match = /filename="?([^"]+)"?/.exec(disposition);
  const filename = match ? match[1] : 'structura-model.xlsx';

  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
  return filename;
}

/* ---------------------------------------------------------------------------
 * The analysis flow.
 *
 * These endpoints have no mock. The whole point of the screen is that every
 * number traces to the engine or to a cited source, and a mock that stood in
 * for that would be the exact failure the provenance system exists to prevent.
 * If the API is unreachable the screen says so.
 * ------------------------------------------------------------------------ */

export async function analyse(deal) {
  return tryJson('/api/analyse', { method: 'POST', body: JSON.stringify(deal) });
}

export async function chat(deal, message) {
  return tryJson('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ deal, message }),
  });
}

export async function library() {
  return tryJson('/api/library', { method: 'GET' });
}
