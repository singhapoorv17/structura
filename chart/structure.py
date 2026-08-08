"""Structure charts, generated from the model rather than drawn by hand.

Every box on the chart is a party the model actually carries, and every line
is a flow the model actually computes. Nothing decorative: if a box appears,
something in the engine produced it, and the chart is regenerated when the
deal changes rather than redrawn.

Output is a self-contained SVG. No external fonts, no images, no scripts, and
colours expressed through ``currentColor`` so the chart inherits the page's
theme instead of fighting it.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from engine.structures.models import StructureKey

__all__ = ["Edge", "EdgeKind", "Node", "NodeKind", "StructureChart", "chart_for"]


class NodeKind(str, Enum):
    SPONSOR = "sponsor"
    INVESTOR = "investor"
    VEHICLE = "vehicle"
    PROJECT = "project"
    LENDER = "lender"
    COUNTERPARTY = "counterparty"


class EdgeKind(str, Enum):
    EQUITY = "equity"
    DEBT = "debt"
    CASH = "cash"
    CONTRACT = "contract"
    GUARANTEE = "guarantee"


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    label: str
    kind: NodeKind
    sublabel: str = ""
    row: int = 0
    col: int = 0


@dataclass(frozen=True, slots=True)
class Edge:
    source: str
    target: str
    kind: EdgeKind
    label: str = ""
    #: Required on an equity edge: an ownership line with no percentage on it
    #: is the single most common defect in a hand-drawn structure chart.
    ownership_pct: float | None = None

    def __post_init__(self) -> None:
        if self.kind is EdgeKind.EQUITY and self.ownership_pct is None:
            raise ValueError(
                f"{self.source}->{self.target}: an equity edge must carry an "
                "ownership percentage"
            )
        if self.kind is not EdgeKind.EQUITY and not self.label:
            raise ValueError(
                f"{self.source}->{self.target}: a non-equity edge must say what "
                "flows along it and in which direction"
            )


@dataclass(frozen=True, slots=True)
class StructureChart:
    structure: StructureKey
    title: str
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    footnote: str = ""

    def node(self, node_id: str) -> Node:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(node_id)

    def to_svg(self, *, width: int = 780) -> str:
        return _render(self, width=width)


# ---------------------------------------------------------------------------
# The graphs
# ---------------------------------------------------------------------------

BOX_W, BOX_H = 172, 54
COL_GAP, ROW_GAP = 92, 96
PAD = 24


def _n(node_id, label, kind, row, col, sublabel=""):
    return Node(id=node_id, label=label, kind=kind, sublabel=sublabel, row=row, col=col)


def chart_for(
    structure: StructureKey,
    *,
    sponsor_share: float = 0.01,
    investor_share: float = 0.99,
    offtaker: str = "Offtaker",
    lender: str = "Senior lenders",
    guarantor: str = "Guarantor",
    lessee: str = "Lessee",
    tranches: Iterable[str] = (),
) -> StructureChart:
    """Build the chart for a structure, using the parties the deal carries."""
    K = StructureKey

    if structure is K.PARTNERSHIP_FLIP:
        nodes = (
            _n("sponsor", "Sponsor", NodeKind.SPONSOR, 0, 0),
            _n("te", "Tax equity investor", NodeKind.INVESTOR, 0, 1),
            _n("hold", "Tax equity partnership", NodeKind.VEHICLE, 1, 0, "Holding company"),
            _n("proj", "Project company", NodeKind.PROJECT, 2, 0),
            _n("lender", lender, NodeKind.LENDER, 2, 1),
            _n("off", offtaker, NodeKind.COUNTERPARTY, 3, 0),
        )
        edges = (
            Edge("sponsor", "hold", EdgeKind.EQUITY, ownership_pct=sponsor_share),
            Edge("te", "hold", EdgeKind.EQUITY, ownership_pct=investor_share),
            Edge("hold", "proj", EdgeKind.EQUITY, ownership_pct=1.0),
            Edge("lender", "proj", EdgeKind.DEBT, "Senior debt in"),
            Edge("off", "proj", EdgeKind.CONTRACT, "Offtake payments in"),
        )
        foot = (
            "Allocations flip to the sponsor once the investor reaches its "
            "target yield."
        )

    elif structure is K.T_FLIP:
        nodes = (
            _n("sponsor", "Sponsor", NodeKind.SPONSOR, 0, 0),
            _n("te", "Tax equity investor", NodeKind.INVESTOR, 0, 1),
            _n("buyer", "Credit transferee", NodeKind.INVESTOR, 0, 2),
            _n("hold", "Tax equity partnership", NodeKind.VEHICLE, 1, 0, "Holding company"),
            _n("proj", "Project company", NodeKind.PROJECT, 2, 0),
            _n("lender", lender, NodeKind.LENDER, 2, 1),
            _n("off", offtaker, NodeKind.COUNTERPARTY, 3, 0),
        )
        edges = (
            Edge("sponsor", "hold", EdgeKind.EQUITY, ownership_pct=sponsor_share),
            Edge("te", "hold", EdgeKind.EQUITY, ownership_pct=investor_share),
            Edge("hold", "proj", EdgeKind.EQUITY, ownership_pct=1.0),
            Edge("buyer", "hold", EdgeKind.CASH, "Credit purchase price in"),
            Edge("hold", "buyer", EdgeKind.CONTRACT, "§6418 credit out"),
            Edge("lender", "proj", EdgeKind.DEBT, "Senior debt in"),
            Edge("off", "proj", EdgeKind.CONTRACT, "Offtake payments in"),
        )
        foot = "A flip with the credit sold on rather than allocated."

    elif structure is K.PREFERRED_EQUITY:
        nodes = (
            _n("sponsor", "Sponsor", NodeKind.SPONSOR, 0, 0),
            _n("pref", "Preferred investor", NodeKind.INVESTOR, 0, 1),
            _n("hold", "Holding company", NodeKind.VEHICLE, 1, 0),
            _n("proj", "Project company", NodeKind.PROJECT, 2, 0),
            _n("lender", lender, NodeKind.LENDER, 2, 1),
            _n("off", offtaker, NodeKind.COUNTERPARTY, 3, 0),
        )
        edges = (
            Edge("sponsor", "hold", EdgeKind.EQUITY, ownership_pct=sponsor_share),
            Edge("pref", "hold", EdgeKind.EQUITY, ownership_pct=investor_share),
            Edge("hold", "pref", EdgeKind.CASH, "Priority return out"),
            Edge("hold", "proj", EdgeKind.EQUITY, ownership_pct=1.0),
            Edge("lender", "proj", EdgeKind.DEBT, "Senior debt in"),
            Edge("off", "proj", EdgeKind.CONTRACT, "Offtake payments in"),
        )
        foot = "The preferred is redeemed before common cash resumes."

    elif structure is K.DIRECT_TRANSFER:
        nodes = (
            _n("sponsor", "Sponsor", NodeKind.SPONSOR, 0, 0),
            _n("buyer", "Credit transferee", NodeKind.INVESTOR, 0, 1),
            _n("proj", "Project company", NodeKind.PROJECT, 1, 0),
            _n("lender", lender, NodeKind.LENDER, 1, 1),
            _n("off", offtaker, NodeKind.COUNTERPARTY, 2, 0),
        )
        edges = (
            Edge("sponsor", "proj", EdgeKind.EQUITY, ownership_pct=1.0),
            Edge("buyer", "proj", EdgeKind.CASH, "Credit purchase price in"),
            Edge("proj", "buyer", EdgeKind.CONTRACT, "§6418 credit out"),
            Edge("lender", "proj", EdgeKind.DEBT, "Senior debt in"),
            Edge("off", "proj", EdgeKind.CONTRACT, "Offtake payments in"),
        )
        foot = "No partnership. The credit is sold and the sponsor keeps the asset."

    elif structure is K.SALE_LEASEBACK:
        nodes = (
            _n("sponsor", "Sponsor, as lessee", NodeKind.SPONSOR, 0, 0),
            _n("lessor", "Lessor", NodeKind.INVESTOR, 0, 1, "Owns the asset"),
            _n("proj", "Project", NodeKind.PROJECT, 1, 0),
            _n("lender", lender, NodeKind.LENDER, 1, 1),
            _n("off", offtaker, NodeKind.COUNTERPARTY, 2, 0),
        )
        edges = (
            Edge("sponsor", "lessor", EdgeKind.CONTRACT, "Asset sold at fair market value"),
            Edge("lessor", "sponsor", EdgeKind.CASH, "Sale proceeds in"),
            Edge("sponsor", "lessor", EdgeKind.CASH, "Rent out"),
            Edge("lender", "lessor", EdgeKind.DEBT, "Senior debt in"),
            Edge("off", "proj", EdgeKind.CONTRACT, "Offtake payments in"),
        )
        foot = (
            "The lessor takes the credit and the depreciation; the lessee "
            "deducts rent."
        )

    elif structure is K.EQUIPMENT_LEASE:
        names = tuple(tranches) or ("Class A1", "Class A2", "Class B")
        nodes = [
            _n("equity", "Vehicle sponsor", NodeKind.SPONSOR, 0, 0, "Equity"),
            _n("notes", "Noteholders", NodeKind.INVESTOR, 0, 1, ", ".join(names)),
            _n("guar", guarantor, NodeKind.COUNTERPARTY, 0, 2, "Residual value guarantee"),
            _n("spv", "Owning SPV", NodeKind.VEHICLE, 1, 0, "Bankruptcy remote"),
            _n("asset", "Equipment", NodeKind.PROJECT, 2, 0),
            _n("lessee", lessee, NodeKind.COUNTERPARTY, 2, 1, "Operator"),
        ]
        edges = (
            Edge("equity", "spv", EdgeKind.EQUITY, ownership_pct=1.0),
            Edge("notes", "spv", EdgeKind.DEBT, "Note proceeds in"),
            Edge("spv", "notes", EdgeKind.CASH, "Interest and principal out"),
            Edge("guar", "notes", EdgeKind.GUARANTEE, "Residual guarantee on senior notes"),
            Edge("spv", "asset", EdgeKind.CASH, "Purchase price out"),
            Edge("lessee", "spv", EdgeKind.CONTRACT, "Rent in, not debt service"),
        )
        nodes = tuple(nodes)
        foot = (
            "The operator never owns the equipment: it pays rent, and the "
            "assets stay off its balance sheet."
        )

    else:  # pragma: no cover - the enum is closed
        raise ValueError(f"no chart defined for {structure}")

    return StructureChart(
        structure=structure,
        title=structure.label,
        nodes=nodes,
        edges=edges,
        footnote=foot,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

FILL = {
    NodeKind.SPONSOR: "0.06",
    NodeKind.INVESTOR: "0.10",
    NodeKind.VEHICLE: "0.14",
    NodeKind.PROJECT: "0.10",
    NodeKind.LENDER: "0.06",
    NodeKind.COUNTERPARTY: "0.04",
}

DASH = {
    EdgeKind.EQUITY: "",
    EdgeKind.DEBT: "",
    EdgeKind.CASH: "4 3",
    EdgeKind.CONTRACT: "1 4",
    EdgeKind.GUARANTEE: "8 4",
}


def _positions(chart: StructureChart) -> dict[str, tuple[int, int]]:
    out = {}
    for node in chart.nodes:
        x = PAD + node.col * (BOX_W + COL_GAP)
        y = PAD + node.row * (BOX_H + ROW_GAP)
        out[node.id] = (x, y)
    return out


def _render(chart: StructureChart, *, width: int) -> str:
    pos = _positions(chart)
    max_x = max(x for x, _ in pos.values()) + BOX_W + PAD
    max_y = max(y for _, y in pos.values()) + BOX_H + PAD + 34
    e = html.escape

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {max_x} {max_y}" '
        f'width="{width}" role="img" aria-label="{e(chart.title)}" '
        'font-family="ui-sans-serif, system-ui, sans-serif" fill="currentColor">',
        f"<title>{e(chart.title)}</title>",
        '<defs><marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor"/></marker></defs>',
    ]

    # Parallel edges between the same pair have to separate, and the offset
    # must be perpendicular to the edge or it does nothing: three horizontal
    # lines nudged sideways still land their labels on the same point.
    pairs: dict[tuple[str, str], int] = {}
    for edge in chart.edges:
        pairs[tuple(sorted((edge.source, edge.target)))] = (
            pairs.get(tuple(sorted((edge.source, edge.target))), 0) + 1
        )
    drawn: dict[tuple[str, str], int] = {}

    for edge in chart.edges:
        key = tuple(sorted((edge.source, edge.target)))
        total = pairs[key]
        nth = drawn.get(key, 0)
        drawn[key] = nth + 1
        # Centre the fan: one edge sits on the axis, two straddle it, and so on.
        spread = (nth - (total - 1) / 2) if total > 1 else 0

        x1, y1 = pos[edge.source]
        x2, y2 = pos[edge.target]
        horizontal = y1 == y2

        if horizontal:
            sx, tx = (x1 + BOX_W, x2) if x2 > x1 else (x1, x2 + BOX_W)
            sy = ty = y1 + BOX_H / 2 + spread * 18
        elif y2 > y1:
            sx = x1 + BOX_W / 2 + spread * 22
            tx = x2 + BOX_W / 2 + spread * 22
            sy, ty = y1 + BOX_H, y2
        else:
            sx = x1 + BOX_W / 2 + spread * 22
            tx = x2 + BOX_W / 2 + spread * 22
            sy, ty = y1, y2 + BOX_H

        dash = DASH[edge.kind]
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<path d="M {sx:.0f} {sy:.0f} L {tx:.0f} {ty:.0f}" stroke="currentColor" '
            f'stroke-width="1.25" fill="none" opacity="0.55"{dash_attr} '
            'marker-end="url(#arw)"/>'
        )

        label = (
            f"{edge.ownership_pct:.0%}"
            if edge.kind is EdgeKind.EQUITY
            else edge.label
        )
        mx, my = (sx + tx) / 2, (sy + ty) / 2
        # On a horizontal run the label sits above its own line; on a vertical
        # run the lines are already apart, so it only needs lifting off.
        label_y = my - 5 if horizontal else my - 4
        parts.append(
            f'<text x="{mx:.0f}" y="{label_y:.0f}" text-anchor="middle" '
            f'font-size="10.5" opacity="0.75">'
            f'<tspan class="edge-label">{e(label)}</tspan></text>'
        )

    for node in chart.nodes:
        x, y = pos[node.id]
        parts.append(
            f'<rect x="{x}" y="{y}" width="{BOX_W}" height="{BOX_H}" rx="7" '
            f'fill="currentColor" fill-opacity="{FILL[node.kind]}" '
            'stroke="currentColor" stroke-opacity="0.35" stroke-width="1"/>'
        )
        ty = y + (BOX_H / 2 + 4 if not node.sublabel else BOX_H / 2 - 4)
        parts.append(
            f'<text x="{x + BOX_W / 2:.0f}" y="{ty:.0f}" text-anchor="middle" '
            f'font-size="12.5" font-weight="500">{e(node.label)}</text>'
        )
        if node.sublabel:
            parts.append(
                f'<text x="{x + BOX_W / 2:.0f}" y="{y + BOX_H / 2 + 12:.0f}" '
                'text-anchor="middle" font-size="10" opacity="0.65">'
                f"{e(node.sublabel)}</text>"
            )

    if chart.footnote:
        parts.append(
            f'<text x="{PAD}" y="{max_y - 12}" font-size="11" opacity="0.7">'
            f"{e(chart.footnote)}</text>"
        )

    parts.append("</svg>")
    return "\n".join(parts)
