"""Conflict graph helpers for demos and the Streamlit dashboard."""
from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path
from typing import Iterable

import networkx as nx

from backend.models.schemas import Conflict, Entity


TEAM_COLORS = [
    "#3B82F6",
    "#10B981",
    "#F59E0B",
    "#8B5CF6",
    "#EC4899",
    "#06B6D4",
    "#F97316",
    "#84CC16",
    "#A855F7",
    "#14B8A6",
]

TYPE_COLORS = {
    "duplication": "#EF4444",
    "contradiction": "#F97316",
    "dependency": "#8B5CF6",
    "say_vs_do": "#06B6D4",
}

SEVERITY_WIDTH = {
    "critical": 5,
    "warning": 3,
    "info": 1.5,
}


def _team_color(team: str) -> str:
    digest = hashlib.sha1(team.encode("utf-8")).hexdigest()
    return TEAM_COLORS[int(digest[:8], 16) % len(TEAM_COLORS)]


def _short_label(value: str, limit: int = 34) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1]}..."


def _entity_title(entity: Entity) -> str:
    return (
        f"<b>{escape(entity.name)}</b><br>"
        f"Team: {escape(entity.team)}<br>"
        f"Source: {escape(entity.source_type.value)}<br>"
        f"Type: {escape(entity.decision_type.value)}<br><br>"
        f"{escape(entity.description)}"
    )


def _add_entity_node(graph: nx.Graph, entity: Entity) -> None:
    if graph.has_node(entity.id):
        return
    graph.add_node(
        entity.id,
        label=_short_label(entity.name),
        title=_entity_title(entity),
        team=entity.team,
        source_type=entity.source_type.value,
        decision_type=entity.decision_type.value,
        color=_team_color(entity.team),
        size=18,
        shape="dot",
    )


def build_graph(conflicts: Iterable[Conflict]) -> nx.Graph:
    """Build a NetworkX graph where entities are nodes and conflicts are edges."""
    graph = nx.Graph()
    for conflict in conflicts:
        a = conflict.entity_a
        b = conflict.entity_b
        _add_entity_node(graph, a)
        _add_entity_node(graph, b)

        conflict_type = conflict.conflict_type.value
        severity = conflict.severity.value
        graph.add_edge(
            a.id,
            b.id,
            conflict_id=conflict.id,
            conflict_type=conflict_type,
            severity=severity,
            similarity=float(conflict.similarity_score),
            label=conflict_type.replace("_", " "),
            title=(
                f"<b>{escape(conflict_type.replace('_', ' ').title())}</b><br>"
                f"Severity: {escape(severity)}<br>"
                f"Similarity: {conflict.similarity_score:.2f}<br><br>"
                f"{escape(conflict.explanation)}"
            ),
            color=TYPE_COLORS.get(conflict_type, "#64748B"),
            width=SEVERITY_WIDTH.get(severity, 1.5),
        )
    return graph


def graph_stats(graph: nx.Graph) -> dict:
    """Return compact stats used by the CLI demo."""
    teams = sorted(
        {
            data.get("team")
            for _node, data in graph.nodes(data=True)
            if data.get("team")
        }
    )
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for _a, _b, data in graph.edges(data=True):
        conflict_type = str(data.get("conflict_type", "unknown"))
        severity = str(data.get("severity", "unknown"))
        by_type[conflict_type] = by_type.get(conflict_type, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1
    return {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "teams": teams,
        "by_type": by_type,
        "by_severity": by_severity,
    }


def export_to_html(graph: nx.Graph, output_path: str | Path | None = None) -> str:
    """Export an interactive PyVis graph and return the written HTML path."""
    from pyvis.network import Network

    path = Path(output_path) if output_path else Path("data/store/conflict_graph.html")
    path.parent.mkdir(parents=True, exist_ok=True)

    net = Network(
        height="560px",
        width="100%",
        bgcolor="#0A0E1A",
        font_color="#F1F5F9",
        cdn_resources="in_line",
    )
    net.barnes_hut(gravity=-3200, central_gravity=0.25, spring_length=180)

    for node_id, data in graph.nodes(data=True):
        net.add_node(
            node_id,
            label=data.get("label", str(node_id)),
            title=data.get("title", ""),
            color=data.get("color", "#3B82F6"),
            size=data.get("size", 18),
            shape=data.get("shape", "dot"),
        )

    for source, target, data in graph.edges(data=True):
        net.add_edge(
            source,
            target,
            label=data.get("label", ""),
            title=data.get("title", ""),
            color=data.get("color", "#64748B"),
            width=data.get("width", 1.5),
        )

    net.set_options(
        """
        {
          "nodes": {
            "font": {"size": 15, "face": "Inter", "color": "#F1F5F9"},
            "borderWidth": 2
          },
          "edges": {
            "font": {"size": 12, "align": "middle", "color": "#CBD5E1"},
            "smooth": {"type": "dynamic"},
            "selectionWidth": 2
          },
          "interaction": {
            "hover": true,
            "tooltipDelay": 120,
            "navigationButtons": true
          },
          "physics": {
            "stabilization": {"iterations": 120}
          }
        }
        """
    )
    net.write_html(str(path), notebook=False, open_browser=False)
    return str(path)
