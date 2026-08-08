'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LAW_VERIFIED_ON } from '../lib/mockData';

const NAV = [
  { href: '/', label: 'Analyse a project' },
  { href: '/library', label: 'Transaction library' },
  { href: '/current-law', label: 'Current law' },
  { href: '/methods', label: 'Methods & limits' },
];

export function TopBar() {
  const path = usePathname();
  return (
    <div className="topbar">
      <div className="topbar-inner">
        <Link className="brand" href="/">
          <span className="dot" />
          Structura
          <small>energy project finance · structuring engine</small>
        </Link>
        <nav className="nav">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className={path === n.href ? 'on' : ''}>
              {n.label}
            </Link>
          ))}
        </nav>
        <span className="spacer" />
        <span className="verified">
          law verified <b>{LAW_VERIFIED_ON}</b>
        </span>
      </div>
    </div>
  );
}

export function Footer() {
  return (
    <footer className="foot">
      <span className="disclaimer">
        Illustrative modelling tool. Not tax, legal, accounting or investment advice.
      </span>
      <span>MIT licence. Public sources only — no deal data, no PII, no accounts.</span>
      <span>
        Market benchmarks: Norton Rose Fulbright, <i>Cost of Capital: 2026 Outlook</i> (2026-01-29);
        Crux 2025 transferability data. Cost anchors: NLR Annual Technology Baseline 2024 v4.0.0
        (CC-BY 4.0).
      </span>
    </footer>
  );
}
