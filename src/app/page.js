'use client';

import { useCallback, useState } from 'react';

import DealForm from '../components/DealForm';
import {
  Advisories,
  Charts,
  ChatRail,
  Comparables,
  Comparison,
  Parties,
  Recommendation,
  ResolvedInputs,
} from '../components/Results';
import { analyse, chat } from '../lib/api';

const INITIAL = {
  asset_type: 'STORAGE',
  size: { mw: 150, mwh: 600 },
  state: 'CA',
  contract: { kind: 'TOLLING', tenor_years: 15 },
  cod: '2028-01',
};

export default function Home() {
  const [deal, setDeal] = useState(INITIAL);
  const [priority, setPriority] = useState('max_irr');
  const [result, setResult] = useState(null);
  const [turns, setTurns] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const run = useCallback(
    async (nextDeal, nextPriority) => {
      setBusy(true);
      setError('');
      try {
        const payload = await analyse({
          ...nextDeal,
          priority: nextPriority || priority,
        });
        setResult(payload);
      } catch (e) {
        setResult(null);
        setError(
          e && e.message
            ? e.message
            : 'The analysis service is unreachable, so nothing is shown.'
        );
      } finally {
        setBusy(false);
      }
    },
    [priority]
  );

  const send = useCallback(
    async (message) => {
      setBusy(true);
      try {
        const turn = await chat(deal, message);
        setTurns((t) => [...t, { ...turn, question: message }]);
        if (turn.mutated && turn.deal) {
          setDeal(turn.deal);
          await run(turn.deal);
        }
      } catch (e) {
        setTurns((t) => [
          ...t,
          { question: message, understood: false, needed: e.message },
        ]);
      } finally {
        setBusy(false);
      }
    },
    [deal, run]
  );

  return (
    <main className="page">
      <section className="hero">
        <h1>Structure a project, or reconstruct one that closed</h1>
        <p>
          Describe a project in six fields. Structura resolves the rest from
          comparable transactions and cited market bands, screens every capital
          structure, and shows the economics by party. Each number says whether
          it is a stated fact, a market benchmark, a tool assumption, or
          something the sources never disclosed.
        </p>
      </section>

      <DealForm
        deal={deal}
        priority={priority}
        busy={busy}
        onChange={setDeal}
        onPriority={(p) => {
          setPriority(p);
          if (result) run(deal, p);
        }}
        onSubmit={(d) => run(d)}
      />

      {error ? <p className="error">{error}</p> : null}

      {result ? (
        <>
          <Advisories items={result.deal.advisories} />
          <div className="cols">
            <ResolvedInputs deal={result.deal} />
            <Comparables comparables={result.comparables} />
          </div>
          <Recommendation comparison={result.comparison} />
          <Comparison comparison={result.comparison} />
          <Charts
            charts={result.charts}
            structures={result.comparison.structures}
          />
          <Parties
            parties={result.parties}
            structures={result.comparison.structures}
          />
          <ChatRail turns={turns} onSend={send} busy={busy} />
        </>
      ) : null}

      {!result && !error && !busy ? (
        <p className="empty">
          Pick a starting point above, or enter a project, and press Analyse.
        </p>
      ) : null}
    </main>
  );
}
