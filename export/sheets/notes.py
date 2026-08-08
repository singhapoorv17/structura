"""Notes - methodology, conventions, what is solver-derived, and the disclaimer.

A model without a methods page is not auditable, and a model that is not
auditable is worthless to a credit committee (SPEC.md §4.2). This sheet states
plainly what the workbook does, what it deliberately does not do, which single
cell came out of Python rather than out of Excel, and where the market defaults
come from.
"""

from __future__ import annotations

from export import styles
from export.model import DISCLAIMER, ModelBundle
from export.workbook import (
    ITERATE_COUNT,
    ITERATE_DELTA,
    WorkbookBuilder,
)

__all__ = ["SHEET_NAME", "build"]

SHEET_NAME = "Notes"


def build(wb: WorkbookBuilder, model: ModelBundle) -> None:
    """Write the Notes / Methodology sheet."""
    sw = wb.create_sheet(SHEET_NAME, n_periods=0)
    sw.hide_gridlines()
    sw.ws.column_dimensions["A"].width = 44
    sw.ws.column_dimensions["B"].width = 110

    sw.title_block(
        "Notes and methodology",
        f"Structura - open-source energy project-finance structuring engine. "
        f"Workbook generated {model.generated_on.isoformat()}.",
    )

    _section(sw, "How to use this workbook")
    _item(
        sw,
        "Change the blue cells",
        "Every driver of the model is a blue input on the Inputs sheet, and "
        "every one of them carries a named range. Black cells are formulas "
        "calculated on their own sheet; green cells are links pulling a value "
        "in from another sheet. Change a blue cell and the entire model - debt "
        "quantum, sculpted profile, waterfall, returns - recalculates.",
    )
    _item(
        sw,
        "Iterative calculation is required",
        "This workbook contains deliberate circular references (see below). It "
        "is written with iterative calculation switched on: "
        f"maximum {ITERATE_COUNT} iterations, maximum change {ITERATE_DELTA}. "
        "Excel enables this automatically when it opens the file. If you see a "
        "circular-reference warning, switch it on manually at File > Options > "
        "Formulas > Enable iterative calculation, then press F9.",
    )
    _item(
        sw,
        "Everything recalculates on open",
        "The file is written with fullCalcOnLoad set, because the generator "
        "writes formulas without cached results. The first thing Excel does on "
        "opening is calculate the whole workbook. That is expected.",
    )
    _item(
        sw,
        "Check rows must read zero",
        "Four integrity checks are wired into the model: the CFADS identity "
        "(Operations), convergence of the construction circularity "
        "(Construction), full amortisation at maturity (Debt) and cash "
        "conservation in every period (Waterfall). They are repeated on the "
        "Summary sheet. If any is non-zero, do not rely on the output.",
    )
    sw.skip()

    _section(sw, "The circularity, and why it is deliberate")
    _item(
        sw,
        "Where it is",
        "Total project cost = capex + upfront fee + commitment fee + interest "
        "during construction + initial DSRA. Every term after capex depends on "
        "the size of the debt, and the debt depends on total project cost "
        "through the gearing cap. That is a genuine fixed point, not a "
        "modelling error.",
    )
    _item(
        sw,
        "How it is closed",
        "Debt-funded capex is defined as the facility less its own fees and "
        "capitalised interest. IDC and the commitment fee come out of the "
        "monthly construction grid, which that figure drives. Excel iterates "
        "the loop to convergence.",
    )
    _item(
        sw,
        "Cross-check",
        "Structura's Python engine solves the identical fixed point "
        "deterministically with Brent's method, and the test suite asserts "
        "that the workbook's formula chain and the Python solver agree to a "
        "documented tolerance. Neither path depends on the other.",
    )
    _item(
        sw,
        "A second circularity, only if tax treatment 3 is selected",
        "Interest is tax-deductible, so cash tax depends on the debt schedule, "
        "which depends on CFADS, which depends on cash tax. Switched off under "
        "the default treatment (1), where CFADS is pre-tax - the market "
        "convention for debt sizing, because tax attributes normally sit in a "
        "structure modelled above the project.",
    )
    sw.skip()

    _section(sw, "Solver-derived versus formula-derived")
    _item(
        sw,
        "Formula-derived (almost everything)",
        "The debt quantum, the sculpted service profile, the interest and "
        "principal split, the closing balance, DSCR, LLCR, PLCR, the DSRA "
        "target, IDC, fees, total project cost, the whole waterfall, and every "
        "return metric are live Excel formulas over the Inputs sheet. None of "
        "them is a pasted number.",
    )
    _item(
        sw,
        "Solver-derived: the applied grace period (amber, Inputs section 10)",
        "A pure present-value sculpt can imply debt service below the interest "
        "accruing in the early periods when CFADS ramps steeply at a high "
        "rate - negative amortisation, which no term facility permits. "
        "Structura lengthens the interest-only holiday one period at a time "
        "until every period amortises non-negatively. That is a search, not an "
        "expression, so Excel cannot re-derive it. The value is carried across "
        "as an input and flagged amber. Everything downstream of it is live. "
        f"For this deal the requested grace period was "
        f"{model.terms.grace_periods(model.periods_per_year)} period(s) and "
        f"the applied grace period is "
        f"{model.solution.sizing.debt.grace_periods} period(s).",
    )
    _item(
        sw,
        "Inputs that are shapes, not scalars",
        "The construction capex S-curve is a row of blue weights on the "
        "Construction sheet, normalised live. A time-varying DSCR target, if "
        "one is used, is a blue row on the Debt sheet. Both are inputs, not "
        "solver output.",
    )
    sw.skip()

    _section(sw, "Conventions")
    _convention(
        sw,
        "Interest",
        "Nominal annual rate divided by the number of periods per year "
        "(money-market style), which is how a credit agreement quotes a margin "
        "over a periodic index. Exact day counts (30/360, act/360) are not "
        "modelled.",
    )
    _convention(
        sw,
        "Construction draws",
        "Drawn at the start of the month, with interest accruing on the "
        "post-draw balance. This is the lender's convention and is "
        "conservative by roughly half a month of IDC.",
    )
    _convention(
        sw,
        "Grace period",
        "Interest-paid, not interest-capitalised. PIK interest during "
        "operations is not modelled.",
    )
    _convention(
        sw,
        "DSRA",
        "Forward-looking: the reserve holds cover for the debt service about "
        "to fall due, consuming future periods pro rata. Released in full at "
        "final maturity.",
    )
    _convention(
        sw,
        "Cash sweep",
        "Applied in inverse order of maturity - it retires the back of the "
        "amortisation schedule first, shortening the loan without disturbing "
        "the near-term profile the deal was sculpted to. No make-whole or "
        "prepayment penalty is modelled.",
    )
    _convention(
        sw,
        "Distribution lock-up",
        "Modelled as a 100% sweep in the affected period. A real agreement "
        "traps the cash in a blocked account and releases it after a cure "
        "period; this treatment is simpler and more conservative.",
    )
    _convention(
        sw,
        "Operating cost sign",
        "Costs are shown as positive numbers and subtracted, rather than shown "
        "negative and added. EBITDA = revenue less operating expenditure.",
    )
    _convention(
        sw,
        "Equity timing",
        "The whole equity contribution is treated as a single outflow at COD "
        "for the IRR. Equity is in practice drawn across construction, often "
        "ahead of debt, which lowers the true equity IRR slightly. The monthly "
        "equity draw is shown on the Construction sheet.",
    )
    _convention(
        sw,
        "Escalation and degradation",
        "Compound on an operating-year basis and apply uniformly to every "
        "sub-period of a year. No seasonality.",
    )
    _convention(
        sw,
        "Terms",
        "CFADS = cash flow available for debt service. DSCR = CFADS / debt "
        "service. LLCR / PLCR = PV of CFADS to loan maturity / to end of "
        "project life, at the debt rate, over debt outstanding. DSRA = debt "
        "service reserve account. MRA = maintenance reserve account. IDC = "
        "interest during construction. Gearing = debt / total funded project "
        "cost. Tail = project life less debt tenor.",
    )
    sw.skip()

    _section(sw, "What this workbook deliberately does not do")
    _item(
        sw,
        "No tax structure",
        "Section 48E / 45Y eligibility and phase-down, FEOC and the material "
        "assistance cost ratio, the domestic content adder, the begin-"
        "construction fork, MACRS and bonus depreciation, and the 50% ITC "
        "basis reduction are not in this workbook. They arrive on a dedicated "
        "Tax sheet in a later release.",
    )
    _item(
        sw,
        "No structure comparison",
        "Partnership flip, T-flip, preferred equity, direct transfer under "
        "section 6418 and sale-leaseback are not modelled here. A Structures "
        "sheet comparing them arrives in a later release. Section 704(b) "
        "capital accounts, deficit restoration obligations and outside basis "
        "are part of that work.",
    )
    _item(
        sw,
        "One senior tranche",
        "No mezzanine, no multi-tranche facility, no refinancing, no "
        "back-leverage. The waterfall exposes a subordinated debt service row "
        "as a blue input but does not size a junior tranche.",
    )
    _item(
        sw,
        "No scenarios in the workbook",
        "P50 / P90 / P99, merchant-share and rate-shock grids are run in the "
        "engine, not in the sheet. Re-export to change case.",
    )
    _item(
        sw,
        "No default mechanics",
        "A shortfall beyond the DSRA is reported and the model keeps running. "
        "It does not accelerate, restructure or enforce.",
    )
    _item(
        sw,
        "Grid width is fixed at generation",
        "Rows extend over the project life and construction period as they "
        "stood when the file was written. Shortening either is handled live by "
        "the masking formulas; lengthening beyond the built grid requires a "
        "re-export.",
    )
    sw.skip()

    _section(sw, "Sources and attribution")
    _item(
        sw,
        "Market defaults",
        "Minimum DSCR by technology and revenue-risk profile, debt pricing, "
        "merchant-exposure adders and ITC bridge advance rates are taken from "
        "Norton Rose Fulbright, 'Cost of Capital: 2026 Outlook', published "
        "2026-01-29. Gearing caps, DSRA cover, tail requirements and fee "
        "levels reflect standard non-recourse credit-agreement practice.",
    )
    _item(
        sw,
        "Tax rate",
        "Federal corporate rate of 21%, IRC section 11(b). Federal only; no "
        "state tax is modelled.",
    )
    _item(
        sw,
        "Reference rates",
        "Structura ships no rates feed. The all-in interest rate is a user "
        "input and must be set from a live fixing plus the applicable margin.",
    )
    _item(
        sw,
        "PPA and merchant prices",
        "No free source of forward PPA or merchant curves exists; both are "
        "user inputs. Sanity-check them against a published LCOE benchmark.",
    )
    _item(
        sw,
        "No transaction data",
        "Nothing in this workbook is derived from a real transaction or from "
        "any employer's data. Every default is a published, dated market "
        "benchmark.",
    )
    _item(
        sw,
        "Honest positioning",
        "None of the mathematics here is novel. Debt sculpting, LLCR/PLCR and "
        "the IDC circularity are decades-old practice, and free spreadsheet "
        "implementations exist. What Structura contributes is packaging, "
        "currency, reproducibility and auditability: a tested, typed, "
        "versioned, MIT-licensed implementation in which every default carries "
        "a citation and a date, and every check is asserted rather than "
        "assumed.",
    )
    sw.skip()

    _section(sw, "Disclaimer")
    sw.write(1, sw.row, "", styles.LABEL)
    sw.write(2, sw.row, DISCLAIMER, styles.SUBHEAD)
    sw.row += 2
    _item(
        sw,
        "Licence",
        "Structura is released under the MIT licence. This workbook may be "
        "freely copied, modified and distributed. It carries no warranty of "
        "any kind.",
    )
    _item(
        sw,
        "No personal data",
        "This workbook contains no personal data, no account identifiers and "
        "no confidential transaction information. It is generated entirely "
        "from the assumptions on the Inputs sheet.",
    )
    sw.freeze("A5")


# ---------------------------------------------------------------------------


def _section(sw, label: str) -> None:
    sw.write(1, sw.row, label, styles.SECTION)
    sw.write(2, sw.row, "", styles.SECTION)
    sw.row += 1


def _item(sw, heading: str, body: str) -> None:
    sw.write(1, sw.row, heading, styles.SUBHEAD)
    cell = sw.write(2, sw.row, body, styles.LABEL)
    cell.alignment = _wrapped(cell.alignment)
    sw.ws.row_dimensions[sw.row].height = max(15, 13 * (1 + len(body) // 110))
    sw.row += 1


def _convention(sw, heading: str, body: str) -> None:
    _item(sw, heading, body)


def _wrapped(alignment):
    from openpyxl.styles import Alignment

    return Alignment(
        horizontal="left", vertical="top", wrap_text=True
    )
