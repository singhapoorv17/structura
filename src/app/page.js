'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import ComparisonTable, { CashTimingStrip } from '../components/ComparisonTable';
import InputsPanel from '../components/InputsPanel';
import RiskPanel from '../components/RiskPanel';
import WhyThisWins from '../components/WhyThisWins';
import { DebtSummary, SourcesAndUses } from '../components/CapitalPanels';
import { compare, exportWorkbook, referenceDeals } from '../lib/api';
import { MOCK_DEAL_INPUTS, MOCK_REFERENCE_DEALS } from '../lib/mockData';
import { pct, usdM } from '../lib/format';

const DEFAULT_DEAL = 'storage_bess_contracted';

/**
 * Seed the form from the deal's REAL calibrated inputs, as published by
 * /api/reference-deals. The mock is a last-resort fallback for when the API is
 * unreachable — it must never be the source of values we post back to a live
 * engine, or the page silently displays an uncalibrated deal.
 */
function inputsFor(key, deals) {
  const fromApi = (deals || []).find((d) => d.key === key);
  if (fromApi && fromApi.inputs) return { ...fromApi.inputs };
  return { ...(MOCK_DEAL_INPUTS[key] || MOCK_DEAL_INPUTS[DEFAULT_DEAL]) };
}

export default function Page() {
  const [deals, setDeals] = useState([]);
  const [dealsLoading, setDealsLoading] = useState(true);
  const [dealsError, setDealsError] = useState(null);

  const [dealKey, setDealKey] = useState(DEFAULT_DEAL);
  const [values, setValues] = useState(() => inputsFor(DEFAULT_DEAL));
  const [dirty, setDirty] = useState(false);

  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(null);
  const [exportOk, setExportOk] = useState(null);

  const seq = useRef(0);

  // ---- reference deals -----------------------------------------------------
  useEffect(() => {
    let live = true;
    referenceDeals()
      .then((d) => {
        if (!live) return;
        setDeals(d.deals && d.deals.length ? d.deals : MOCK_REFERENCE_DEALS);
        setDealsLoading(false);
      })
      .catch((e) => {
        if (!live) return;
        setDealsError(e.message || 'Unknown error');
        setDeals(MOCK_REFERENCE_DEALS);
        setDealsLoading(false);
      });
    return () => {
      live = false;
    };
  }, []);

  // ---- run -----------------------------------------------------------------
  const run = useCallback(
    (key, overrides) => {
      const id = ++seq.current;
      setRunning(true);
      setError(null);
      compare({ deal_key: key, overrides })
        .then((r) => {
          if (id !== seq.current) return;
          setResult(r);
          setRunning(false);
        })
        .catch((e) => {
          if (id !== seq.current) return;
          setError(e.message || 'The comparison failed.');
          setRunning(false);
        });
    },
    []
  );

  // First run: wait for the deal list so the form and the engine both use the
  // deal's real calibrated inputs. Sending mock values to the live engine
  // produces a different, uncalibrated deal.
  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current || dealsLoading) return;
    seeded.current = true;
    const next = inputsFor(DEFAULT_DEAL, deals);
    setValues(next);
    run(DEFAULT_DEAL, next);
  }, [run, deals, dealsLoading]);

  const selectDeal = (key) => {
    const next = inputsFor(key, deals);
    setDealKey(key);
    setValues(next);
    setDirty(false);
    setExportError(null);
    setExportOk(null);
    run(key, next);
  };

  const onChange = (k, v) => {
    setValues((prev) => {
      const next = { ...prev, [k]: v };
      return next;
    });
    setDirty(true);
  };

  const onReset = () => {
    const next = inputsFor(dealKey, deals);
    setValues(next);
    setDirty(false);
    run(dealKey, next);
  };

  const onRun = () => run(dealKey, values);

  const onExport = async () => {
    setExporting(true);
    setExportError(null);
    setExportOk(null);
    try {
      const name = await exportWorkbook({ deal_key: dealKey, overrides: values });
      setExportOk(name);
    } catch (e) {
      setExportError(e.message || 'Export failed.');
    } finally {
      setExporting(false);
    }
  };

  const winner = useMemo(
    () => (result && result.ranked ? result.ranked.find((r) => r.feasible) : null),
    [result]
  );

  return (
    <main>
      <div className="pagehead">
        <div className="kicker">Structure selector · law as of {result ? result.law_verified_on : '2026-08-06'}</div>
        <h1>Which capital structure gives this project the lowest cost of capital today?</h1>
        <p>
          One project, sculpted once to a target DSCR, run through all five structures live in the
          2026 market — partnership flip, T-flip, preferred equity, direct §6418 transfer and
          sale-leaseback — under OBBBA, FEOC/MACR and the current state of the begin-construction
          litigation. Free and open source.{' '}
          <Link href="/methods">What this does not claim →</Link>
        </p>
      </div>

      <div className="cols">
        <div className="rail">
          <InputsPanel
            deals={deals}
            dealsLoading={dealsLoading}
            dealsError={dealsError}
            dealKey={dealKey}
            onSelectDeal={selectDeal}
            values={values}
            onChange={onChange}
            onRun={onRun}
            onReset={onReset}
            running={running}
            dirty={dirty}
          />

          <section className="panel">
            <header>
              <h2>Export</h2>
              <span className="sub">openpyxl · live formulas</span>
            </header>
            <div className="body">
              <button className="btn wide" onClick={onExport} disabled={exporting || !result}>
                {exporting ? 'Generating workbook…' : 'Download Excel model'}
              </button>
              <p style={{ fontSize: 11, color: 'var(--text-faint)', margin: '8px 0 0' }}>
                Inputs · Assumptions · Construction · Operations · Debt · Tax · Structure · Waterfall
                · Returns · Summary. Named ranges on every driver, iterative calculation enabled, no
                pasted values — change the DSCR cell and the workbook re-solves.
              </p>
              {exportError ? (
                <div className="callout blocking" style={{ marginTop: 10 }}>
                  <div className="ct">Export unavailable</div>
                  {exportError}
                </div>
              ) : null}
              {exportOk ? (
                <div className="callout win" style={{ marginTop: 10 }}>
                  <div className="ct">Downloaded</div>
                  <code>{exportOk}</code>
                </div>
              ) : null}
            </div>
          </section>
        </div>

        <div>
          {error ? (
            <section className="panel">
              <header>
                <h2>Comparison failed</h2>
              </header>
              <div className="body">
                <div className="callout blocking">
                  <div className="ct">The engine did not return a result</div>
                  {error}
                </div>
                <div className="btnrow" style={{ marginTop: 10 }}>
                  <button className="btn" onClick={onRun}>
                    Retry
                  </button>
                </div>
              </div>
            </section>
          ) : null}

          {running && !result ? (
            <section className="panel">
              <div className="state">
                <div className="bar" />
                Sculpting debt, running the tax gate, solving five structures…
              </div>
            </section>
          ) : null}

          {result ? (
            <>
              <section className="panel">
                <header>
                  <h2>{result.deal.name}</h2>
                  <span className="spacer" />
                  <span className="sub">
                    {result._source === 'mock' ? (
                      <span className="badge warn" title={result._fallback_reason || 'Local mock'}>
                        demo data — engine not connected
                      </span>
                    ) : (
                      <span className="badge win">live engine</span>
                    )}{' '}
                    <span className="srcnote">{result.compute_ms} ms</span>
                  </span>
                </header>
                <div className="body">
                  <p style={{ margin: 0, color: 'var(--text-dim)', maxWidth: '86ch' }}>
                    {result.deal.summary}
                  </p>
                </div>
                <div className="stats">
                  <div className="stat">
                    <div className="k">Capex</div>
                    <div className="v">{usdM(result.deal.capex)}</div>
                  </div>
                  <div className="stat">
                    <div className="k">Funding requirement</div>
                    <div className="v">{usdM(result.sources_and_uses.funding_requirement)}</div>
                  </div>
                  <div className="stat">
                    <div className="k">Winning structure</div>
                    <div className="v sm">{winner ? winner.label : '—'}</div>
                  </div>
                  <div className="stat">
                    <div className="k">
                      {winner && winner.irr_is_meaningful ? 'Sponsor after-tax IRR' : 'Sponsor NPV'}
                    </div>
                    <div className="v">
                      {winner
                        ? winner.irr_is_meaningful
                          ? pct(winner.sponsor_after_tax_irr)
                          : usdM(winner.sponsor_npv)
                        : '—'}
                    </div>
                  </div>
                  <div className="stat">
                    <div className="k">Effective cost of capital</div>
                    <div className="v">
                      {winner ? pct(winner.effective_cost_of_capital) : '—'}
                    </div>
                  </div>
                </div>
              </section>

              <section className="panel">
                <header>
                  <h2>Structure comparison</h2>
                  <span className="sub">
                    all five structures, one debt sizing, same project
                  </span>
                  <span className="spacer" />
                  {running ? <span className="badge info">re-solving…</span> : null}
                </header>
                <div className="body flush" style={{ opacity: running ? 0.55 : 1, transition: 'opacity .12s ease' }}>
                  <ComparisonTable ranked={result.ranked} />
                </div>
              </section>

              <WhyThisWins why={result.why_this_wins} ranked={result.ranked} />

              <div className="split2">
                <SourcesAndUses su={result.sources_and_uses} tax={result.tax} />
                <div>
                  <DebtSummary debt={result.debt} />
                  <section className="panel">
                    <header>
                      <h2>Cash timing &amp; credit disposition</h2>
                      <span className="sub">two structures with the same IRR are not the same deal</span>
                    </header>
                    <div className="body flush">
                      <CashTimingStrip ranked={result.ranked} />
                    </div>
                  </section>
                </div>
              </div>

              <RiskPanel result={result} />
            </>
          ) : null}
        </div>
      </div>
    </main>
  );
}
