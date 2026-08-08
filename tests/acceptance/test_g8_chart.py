"""G8 — structure charts generated from the model, not drawn by hand."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from engine.structures.models import StructureKey

#: Anything that would make the SVG reach off the page. The namespace is the
#: one legitimate occurrence of a URL and is stripped before checking.
EXTERNAL = ("http://", "https://", "<script", "<image", "<foreignObject", "@import", "url(http")
NAMESPACE = "http://www.w3.org/2000/svg"


@pytest.fixture(params=list(StructureKey), ids=lambda k: k.value)
def chart(request):
    from chart import chart_for

    return chart_for(request.param)


@pytest.mark.gate("G8.1")
def test_a_chart_renders_for_every_structure(chart):
    svg = chart.to_svg()
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert chart.nodes and chart.edges


@pytest.mark.gate("G8.2")
def test_the_svg_is_well_formed_and_self_contained(chart):
    svg = chart.to_svg()
    ET.fromstring(svg)

    stripped = svg.replace(NAMESPACE, "")
    found = [token for token in EXTERNAL if token in stripped]
    assert not found, f"the chart reaches off the page: {found}"

    # Colour comes from the page, so the chart works in either theme.
    assert 'fill="currentColor"' in svg
    assert "#" not in svg.split("<title>")[0], "a hard-coded colour was emitted"


@pytest.mark.gate("G8.3")
def test_equity_edges_carry_ownership_and_the_rest_carry_direction(chart):
    from chart import EdgeKind

    for edge in chart.edges:
        if edge.kind is EdgeKind.EQUITY:
            assert edge.ownership_pct is not None
            assert 0.0 <= edge.ownership_pct <= 1.0
            assert f"{edge.ownership_pct:.0%}" in chart.to_svg()
        else:
            assert edge.label.strip(), f"{edge.source}->{edge.target} says nothing"
            assert any(
                word in edge.label.lower()
                for word in (" in", " out", "guarantee", "sold")
            ), f"{edge.source}->{edge.target}: '{edge.label}' gives no direction"


@pytest.mark.gate("G8.3")
def test_an_equity_edge_without_a_percentage_cannot_be_built():
    """An unlabelled ownership line is the commonest defect in a hand-drawn chart."""
    from chart import Edge, EdgeKind

    with pytest.raises(ValueError):
        Edge("a", "b", EdgeKind.EQUITY)
    with pytest.raises(ValueError):
        Edge("a", "b", EdgeKind.DEBT)  # no label
    assert Edge("a", "b", EdgeKind.EQUITY, ownership_pct=0.99)


@pytest.mark.gate("G8.4")
def test_every_node_is_referenced_and_every_edge_resolves(chart):
    """No decorative boxes, and no lines to nowhere."""
    ids = {node.id for node in chart.nodes}
    assert len(ids) == len(chart.nodes), "duplicate node ids"

    connected = set()
    for edge in chart.edges:
        assert edge.source in ids, f"edge from unknown node {edge.source}"
        assert edge.target in ids, f"edge to unknown node {edge.target}"
        connected.update((edge.source, edge.target))

    orphans = ids - connected
    assert not orphans, f"boxes with no flow attached: {sorted(orphans)}"


@pytest.mark.gate("G8.4")
def test_the_equipment_lease_chart_shows_the_guarantee_and_the_rent():
    """The two things that make this structure what it is have to be on it."""
    from chart import EdgeKind, chart_for

    chart = chart_for(
        StructureKey.EQUIPMENT_LEASE, guarantor="Broadcom", lessee="Anthropic"
    )
    labels = {e.label for e in chart.edges}
    assert any("guarantee" in label.lower() for label in labels)
    assert any("rent" in label.lower() for label in labels)

    guarantee = next(e for e in chart.edges if e.kind is EdgeKind.GUARANTEE)
    assert guarantee.source == "guar"

    svg = chart.to_svg()
    assert "Broadcom" in svg and "Anthropic" in svg
    assert "not debt service" in svg, (
        "the chart does not distinguish rent from debt service, which is the "
        "whole point of the structure"
    )
