import Link from 'next/link';

export const metadata = {
  title: 'Methods & limits — Structura',
  description:
    'How Structura computes, what is solver-derived versus live formula in the Excel, and how it compares against SAM and Edward Bodmer\u2019s models.',
};

const SAM_ROWS = [
  {
    axis: 'DSCR-based debt sizing and sculpting',
    sam: 'Yes — and it is the default. Debt sized as PV of cash available for debt service ÷ DSCR, with debt-fraction floors and caps, DSRA reserve months, and level-payment vs fixed-principal amortisation. Extended to all front-of-meter models in 2024.',
    structura:
      'Yes. Same spine, plus LLCR, PLCR, tail tests and explicit binding-constraint reporting.',
    verdict: 'parity',
  },
  {
    axis: 'Partnership flip structures',
    sam: 'Yes — PPA Leveraged Partnership Flip, All-Equity Partnership Flip and Sale-Leaseback all ship, with an IRR-triggered flip date and an iterative PPA-price solve to a target flip percentage.',
    structura: 'Yes, plus T-flip and preferred equity, ranked side by side against one debt sizing.',
    verdict: 'parity',
  },
  {
    axis: 'Partnership tax rigor',
    sam: 'No. Grepping all three finance modules for capital_account, deficit_restoration, outside_basis, 704(b) and suspended_loss returns zero hits. The flip is a stylised fixed pre/post-flip percentage split.',
    structura:
      '§704(b) capital accounts with the alternate test for economic effect, DRO caps with pro-rata reallocation, minimum gain as a deemed DRO, §705/§752 outside basis, the §704(d) limitation with FIFO suspended-loss release, §731(a)(1) gain, and the §50(c)(3) 50% basis reduction. The integrity invariant is asserted every period, for every partner, inside the engine — not in a test hook.',
    verdict: 'structura',
  },
  {
    axis: '2025–26 tax currency',
    sam: 'No. A full release-note and issue search for OBBBA, "One Big Beautiful Bill", transferability, domestic content, energy community, ITC/PTC phase-out and FEOC returns zero mentions across all versions.',
    structura:
      'The OBBBA bifurcation, the 2026-07-04 wind/solar cliff and 2027-12-31 backstop, storage’s runway to 2033, FEOC/MACR as a pass-fail gate, the 2026 50% domestic content threshold, §6418 and §70512(h), and the begin-construction litigation as a toggle. Each with an authority and a verified-on date.',
    verdict: 'structura',
  },
  {
    axis: 'Live-formula Excel for flip structures',
    sam: '"Send to Excel with Equations" exists, but is Windows-only, is available only for Residential, Commercial and Single Owner — explicitly not partnership flip or sale-leaseback — and is documented to approximate the calculations.',
    structura:
      'openpyxl workbook with live formulas and iterative calculation enabled, for every structure, on every platform.',
    verdict: 'structura',
  },
  {
    axis: 'Reach and packaging',
    sam: 'Desktop-first. No hosted API, no web version. PySAM ships compiled wheels that run headless but lag the desktop release.',
    structura: 'Browser. No install, no account, no key.',
    verdict: 'structura',
  },
  {
    axis: 'Physical modelling — resource, yield, dispatch, degradation',
    sam: 'Decades of validated performance modelling across every technology.',
    structura: 'None. Production is an input; Structura is not a substitute for a performance model.',
    verdict: 'sam',
  },
  {
    axis: 'Track record and validation',
    sam: 'A national-laboratory tool with a long publication record and a large user base.',
    structura: 'A 2026 build with golden-case tests and a published limits file.',
    verdict: 'sam',
  },
];

export default function MethodsPage() {
  return (
    <main>
      <div className="pagehead">
        <div className="kicker">methods · limits · comparison</div>
        <h1>How this computes, and what it does not do</h1>
        <p>
          The limits on this page are the ones recorded in the repository&rsquo;s{' '}
          <code>LIMITS.md</code>, <code>LIMITS_STRUCTURES.md</code> and{' '}
          <code>UNVERIFIED.md</code>.
        </p>
      </div>

      {/* ---------------- scope ---------------- */}
      <section className="panel">
        <header>
          <h2>Scope</h2>
        </header>
        <div className="body prose">
          <p>
            Structura sizes non-recourse debt to a target DSCR, models five capital structures
            against that single sizing under 2026 US federal tax law, and exports a workbook whose
            arithmetic recalculates in Excel. Every tax rule carries an authority and a verified-on
            date.
          </p>
          <p>
            The mathematics is standard project finance. Partnership flips, sale-leasebacks and
            DSCR-sized debt are all modelled elsewhere, including in free tools; the comparison
            tables below set out what each does and does not cover.
          </p>
        </div>
      </section>

      {/* ---------------- computation ---------------- */}
      <section className="panel">
        <header>
          <h2>What is computed, and how</h2>
        </header>
        <div className="body prose">
          <h3>The spine</h3>
          <p>
            Debt service is sculpted to a target DSCR profile against CFADS, then tested against
            minimum DSCR, LLCR, PLCR, a maximum debt fraction, maximum tenor and a tail requirement.
            The engine reports <strong>which test binds</strong>, because that is the first thing a
            credit officer asks. Reserves cover DSRA (months-based and forward-looking), MRA and O&amp;M.
          </p>

          <h3>Circularity — solved twice</h3>
          <p>
            Interest during construction depends on the debt size, which depends on fees, which
            depend on the debt size, and the DSRA sizes off debt service. Two independent solutions
            are produced and are required to agree:
          </p>
          <ul>
            <li>
              <strong>Server-side, solver-derived.</strong> A numerical root find on an explicit
              iteration schedule, so the Python model never needs Excel-style iteration to produce a
              number.
            </li>
            <li>
              <strong>In the workbook, as live formulas.</strong> The same relationships are written
              as circular formulas with iterative calculation enabled — iteration on, 100 iterations,
              delta 0.0001, full calculation on load — so Excel re-solves natively when you change an
              input.
            </li>
          </ul>
          <p>
            Both paths must agree within a documented tolerance, and the test suite asserts it.
            Without iterative calculation enabled, a workbook containing these relationships opens
            with circular-reference warnings and does not resolve.
          </p>

          <h3>What is a live formula in the Excel, and what is a value</h3>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Workbook area</th>
                  <th>Live formula</th>
                  <th>Written as a value</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>
                    <span className="sname">Inputs / Assumptions</span>
                  </td>
                  <td>—</td>
                  <td>Named ranges on every driver. These are the cells you change.</td>
                </tr>
                <tr>
                  <td>
                    <span className="sname">Construction, Operations, Debt, Waterfall</span>
                  </td>
                  <td>
                    Fully formula-driven off the named ranges, including the IDC ↔ debt ↔ fees ↔ DSRA
                    circularity.
                  </td>
                  <td>—</td>
                </tr>
                <tr>
                  <td>
                    <span className="sname">Tax</span>
                  </td>
                  <td>
                    Depreciation schedules, basis reduction, credit computation and the allocation
                    arithmetic.
                  </td>
                  <td>
                    Eligibility, MACR pass/fail and the applicable rate — these are legal
                    determinations resolved by the engine and stamped in, not recomputed by Excel.
                  </td>
                </tr>
                <tr>
                  <td>
                    <span className="sname">Structure / Returns</span>
                  </td>
                  <td>Cash splits, IRR and NPV.</td>
                  <td>
                    The <strong>solver outputs</strong>: the flip point from the yield-based root
                    find, the sized tax-equity commitment, and the sculpted principal profile.
                    Excel&rsquo;s Goal Seek is not a substitute for a bounded root find, so the solved
                    values are stamped and the dependent arithmetic stays live.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p>
            The practical consequence: change the DSCR, an interest rate, a price or a cost and the
            workbook recalculates end to end. Change something that <em>moves the flip point</em> and
            the workbook stays arithmetically consistent, but the flip year is the one the server
            solved — re-run here to re-solve it.
          </p>
        </div>
      </section>

      {/* ---------------- ranking / IRR guard ---------------- */}
      <section className="panel">
        <header>
          <h2>Ranking, and why an IRR is sometimes refused</h2>
        </header>
        <div className="body prose">
          <p>
            Structures are ranked on sponsor after-tax IRR — <strong>but only where that rate is
            meaningful.</strong> IRR is a rate on an equity base; shrink the base far enough and the
            rate describes the base rather than the deal. A sale-leaseback that returns the whole
            construction equity at closing can print 41% on a residual base of a few hundred
            thousand dollars.
          </p>
          <p>The rate is refused on four grounds:</p>
          <ul>
            <li>no net sponsor investment;</li>
            <li>sponsor equity below 10% of the funding requirement;</li>
            <li>payback inside one year;</li>
            <li>a rate above 40%, against a market range of roughly 8–15% levered after tax.</li>
          </ul>
          <p>
            These four thresholds are <strong>Structura&rsquo;s own reporting guards, not market
            data.</strong> They change no computed number and decide only which rate is shown as
            the headline. A
            refused structure is ranked on sponsor NPV, behind every structure with a real rate, and
            carries its reason on the row. Effective cost of capital is unaffected and is displayed
            alongside as the cross-check.
          </p>
          <p>
            <strong>Effective cost of capital is a defined quantity, not a market convention:</strong>{' '}
            the IRR of third-party capital in, against everything paid or surrendered to those
            providers, with tax attributes valued at what the <em>recipient</em> realises. A
            different but equally defensible definition would value the attributes at what the
            sponsor gives up, and would rank differently for a sponsor with no tax appetite.
          </p>
        </div>
      </section>

      {/* ---------------- SAM ---------------- */}
      <section className="panel">
        <header>
          <h2>How this differs from SAM</h2>
          <span className="sub">
            System Advisor Model 2026.7.3 / SSC 308 · BSD-3-Clause · free
          </span>
        </header>
        <div className="body">
          <p style={{ color: 'var(--text-dim)', marginTop: 0, maxWidth: '86ch' }}>
            The findings below come from reading <code>cmod_levpartflip.cpp</code>,{' '}
            <code>cmod_singleowner.cpp</code> and <code>common.cpp</code> in source, not from
            documentation.
          </p>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Axis</th>
                  <th>SAM</th>
                  <th>Structura</th>
                  <th className="r">Edge</th>
                </tr>
              </thead>
              <tbody>
                {SAM_ROWS.map((r) => (
                  <tr key={r.axis}>
                    <td style={{ minWidth: 170 }}>
                      <span className="sname" style={{ whiteSpace: 'normal' }}>
                        {r.axis}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-dim)', minWidth: 280 }}>{r.sam}</td>
                    <td style={{ color: 'var(--text-dim)', minWidth: 280 }}>{r.structura}</td>
                    <td className="r">
                      {r.verdict === 'structura' ? (
                        <span className="badge win">Structura</span>
                      ) : r.verdict === 'sam' ? (
                        <span className="badge warn">SAM</span>
                      ) : (
                        <span className="badge">parity</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="callout info" style={{ marginTop: 12 }}>
            <div className="ct">A note on names and URLs</div>
            The laboratory that publishes SAM was renamed, and the old hostnames no longer serve —
            they still resolve in DNS, which will mislead a <code>dig</code> check, but an actual
            HTTP request fails. Any hard-coded reference to the old domain is broken.
          </div>
        </div>
      </section>

      {/* ---------------- Bodmer ---------------- */}
      <section className="panel">
        <header>
          <h2>How this differs from Edward Bodmer&rsquo;s models</h2>
          <span className="sub">a free, ungated Excel model library</span>
        </header>
        <div className="body prose">
          <p>
            <code>edbodmer.com</code> gives away, ungated, hundreds of Excel models plus video
            walkthroughs covering debt sizing, sculpting with grace periods and multiple tranches,
            circularity-free formulations, DSRA/LLCR/PLCR, IDC and equity bridge, refinancing, Monte
            Carlo, and a complete A–Z tax-equity track: fixed and yield-based flips, §704(b) capital
            accounts, outside basis, DROs, minimum gain, PAYGO wind, back-leverage, sale-leaseback and
            inverted lease.
          </p>
          <p>Row by row:</p>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>&nbsp;</th>
                  <th>Bodmer</th>
                  <th>Structura</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>
                    <span className="sname">Coverage of the math</span>
                  </td>
                  <td style={{ color: 'var(--text-dim)' }}>
                    Broader than this tool, and free. Includes several things Structura does not model
                    at all — PAYGO, back-leverage, inverted lease, refinancing, Monte Carlo.
                  </td>
                  <td style={{ color: 'var(--text-dim)' }}>Narrower.</td>
                </tr>
                <tr>
                  <td>
                    <span className="sname">Current law</span>
                  </td>
                  <td style={{ color: 'var(--text-dim)' }}>
                    No evidence of OBBBA or FEOC updates.
                  </td>
                  <td style={{ color: 'var(--text-dim)' }}>
                    Dated citations, a verified-on stamp, and a{' '}
                    <Link href="/current-law">changelog page</Link>.
                  </td>
                </tr>
                <tr>
                  <td>
                    <span className="sname">Version control, tests, audit trail</span>
                  </td>
                  <td style={{ color: 'var(--text-dim)' }}>
                    None. No consistent structure, hard to navigate, licence unclear.
                  </td>
                  <td style={{ color: 'var(--text-dim)' }}>
                    Git, golden-case fixtures with hand-checked answers, an assertion that the Python
                    and Excel paths agree, MIT licence.
                  </td>
                </tr>
                <tr>
                  <td>
                    <span className="sname">Reproducibility</span>
                  </td>
                  <td style={{ color: 'var(--text-dim)' }}>
                    A downloaded spreadsheet with no version history.
                  </td>
                  <td style={{ color: 'var(--text-dim)' }}>
                    <code>make test</code> reruns every golden case.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ---------------- limits ---------------- */}
      <section className="panel">
        <header>
          <h2>What this does not do</h2>
          <span className="sub">the full list is in the repository&rsquo;s limits files</span>
        </header>
        <div className="body prose">
          <h3>Partnership tax — simplified and declared</h3>
          <ul>
            <li>
              <strong>§704(c) is not implemented.</strong> Book and tax ledgers are kept separately
              and a supplied book/tax difference is honoured, but no forward or reverse layer is
              computed. Harmless for cash-funded property where book basis equals tax basis; it
              matters where a partner contributes appreciated property or a development fee is
              capitalised.
            </li>
            <li>
              <strong>Qualified income offset is not implemented.</strong> The DRO-cap floor prevents
              the deficits an <em>allocation</em> could create, but a <em>distribution</em> can still
              drive a capital account below its floor. Structura reports that as a structured breach
              — every period, the worst breach, and a risk flag — rather than curing it.
            </li>
            <li>
              Minimum gain is pooled rather than tracked property by property; the chargeback omits
              the §1.704-2(f)(2)–(5) exceptions, the §1.704-2(j) ordering rules and the partner
              nonrecourse debt regime.
            </li>
            <li>
              §465 at-risk and §469 passive activity limits are not modelled; only §704(d) restricts a
              loss. Fine for a corporate tax-equity investor, wrong for an individual.
            </li>
            <li>
              No capital account revaluations, no HLBV reporting, and no liquidating distribution —
              the model ends at the last operating year with no hypothetical sale, so terminal value
              is out of scope.
            </li>
          </ul>

          <h3>Structures</h3>
          <ul>
            <li>
              <strong>Back-leverage at the sponsor holdco is not modelled.</strong> This is the most
              consequential omission. An ITC-eligible project cannot simultaneously carry maximum
              DSCR-sized senior debt and monetise its credit — a 30% credit is a source, not a return,
              and it displaces equity. So the reference deals set the senior gearing cap to close the
              stack at 100% and come out <em>gearing-bound with coverage well above the market
              floor</em>. In the real market that headroom is taken as holdco debt.
            </li>
            <li>
              <strong>No ITC bridge loan.</strong> A §6418 credit does not exist until the property is
              placed in service, so its sale cannot fund construction. Proceeds arrive in the
              settlement year, undiscounted and unbridged, and are reported as post-COD monetisation
              — deliberately excluded from every source total.
            </li>
            <li>
              PAYGO, sponsor call options at the flip, preferred coupon step-ups and forced-sale
              remedies, stepped rents and §467, and option-value analysis on the lease purchase option
              are all absent. Rev. Proc. 2001-28 is applied as a pass/fail screen and reported as one —
              it sets advance-ruling guidelines, not substantive law.
            </li>
            <li>
              <strong>Recapture is flagged, never modelled.</strong> No §50(a) event is simulated in
              any structure.
            </li>
          </ul>

          <h3>Scope</h3>
          <ul>
            <li>
              <strong>One debt sizing serves all five structures.</strong> A lender would size a
              sale-leaseback differently from a flip; re-sizing per structure would make the
              comparison meaningless, so the simplification is deliberate.
            </li>
            <li>
              <strong>Annual periods.</strong> Sub-annual periods are summed into tax years and a
              trailing part-year is treated as a whole year. Correct for the tax ledger, lossy for
              intra-year cash timing.
            </li>
            <li>
              <strong>Federal tax only.</strong> No state tax anywhere, and no state or local credits.
            </li>
            <li>
              <strong>One scenario per run.</strong> P50/P90/P99, merchant share and rate shocks are
              not swept; the litigation fork and the FEOC-fail case are exercised through the inputs.
            </li>
            <li>
              <strong>No physical modelling.</strong> Production is an input, not a simulation.
            </li>
          </ul>

          <h3>Numbers that are placeholders, not data</h3>
          <p>
            Tax-equity and lease pricing is quoted deal by deal, and no free source of PPA prices
            exists. So the tax-equity target yield, the preferred return and term, the lessor target
            yield, the sale-leaseback residual, the pre/post-flip sharing splits, every capex-per-kW
            figure and every offtake price ship as <strong>labelled placeholders</strong>, surface as
            a warning on every result that consumed one, and are expected to be overridden. The full
            register is on the <Link href="/current-law">current-law page</Link>.
          </p>
          <p>
            What <em>is</em> sourced: the DSCR floors, debt spreads, ITC bridge advance rates and
            gearing convention, from Norton Rose Fulbright&rsquo;s <i>Cost of Capital: 2026
            Outlook</i> (2026-01-29); market shares from Crux; and every tax rule, with its own
            citation.
          </p>
        </div>
      </section>

      <div className="callout blocking" style={{ marginTop: 14 }}>
        <div className="ct">Not advice</div>
        Illustrative modelling tool. <strong>Not tax, legal, accounting or investment advice.</strong>{' '}
        Public sources only — no real transaction&rsquo;s assumptions, no employer data, no PII, no
        accounts. Do not put a deal in front of a credit committee on the strength of this alone.
      </div>
    </main>
  );
}
