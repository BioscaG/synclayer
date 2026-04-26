"use client";

import { useMemo, useState } from "react";
import type { Conflict, ConflictType } from "@/lib/types";
import { cn, teamColor } from "@/lib/utils";

const TYPE_COLORS: Record<ConflictType, string> = {
  duplication: "#DC2626",
  contradiction: "#D97706",
  dependency: "#7C3AED",
  say_vs_do: "#0891B2",
};

const TYPE_LABEL: Record<ConflictType, string> = {
  duplication: "Duplication",
  contradiction: "Contradiction",
  dependency: "Hidden dependency",
  say_vs_do: "Say vs do",
};

// Severity-driven thickness — critical conflicts read as the heaviest line.
const SEVERITY_WEIGHT: Record<string, number> = {
  critical: 3,
  warning: 2,
  info: 1,
};

interface Edge {
  a: string;
  b: string;
  count: number;
  byType: Map<ConflictType, number>;
  severityWeight: number;
  dominantType: ConflictType;
  conflicts: Conflict[];
}

interface NodeRow {
  team: string;
  conflicts: number;
  color: string;
}

export function TeamConflictGraph({
  conflicts,
  teamColors,
  onSelectPair,
}: {
  conflicts: Conflict[];
  /** Optional team→color map. Falls back to deterministic palette. */
  teamColors?: Record<string, string>;
  /** Called when an edge is clicked. */
  onSelectPair?: (a: string, b: string) => void;
}) {
  const [hoveredTeam, setHoveredTeam] = useState<string | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null);

  const { nodes, edges } = useMemo(() => {
    const nodeMap = new Map<string, NodeRow>();
    const edgeMap = new Map<string, Edge>();

    for (const c of conflicts) {
      const ta = c.entity_a.team;
      const tb = c.entity_b.team;
      if (!ta || !tb || ta === tb) continue;

      for (const t of [ta, tb]) {
        if (!nodeMap.has(t)) {
          nodeMap.set(t, {
            team: t,
            conflicts: 0,
            color: teamColors?.[t] || teamColor(t),
          });
        }
        nodeMap.get(t)!.conflicts += 1;
      }

      const [x, y] = [ta, tb].sort();
      const key = `${x}::${y}`;
      let edge = edgeMap.get(key);
      if (!edge) {
        edge = {
          a: x,
          b: y,
          count: 0,
          byType: new Map(),
          severityWeight: 0,
          dominantType: c.conflict_type,
          conflicts: [],
        };
        edgeMap.set(key, edge);
      }
      edge.count += 1;
      edge.byType.set(
        c.conflict_type,
        (edge.byType.get(c.conflict_type) || 0) + 1
      );
      edge.severityWeight += SEVERITY_WEIGHT[c.severity] || 1;
      edge.conflicts.push(c);
    }

    // Resolve dominant type per edge (most common conflict type on that pair).
    for (const edge of edgeMap.values()) {
      let max = 0;
      for (const [t, n] of edge.byType) {
        if (n > max) {
          max = n;
          edge.dominantType = t;
        }
      }
    }

    return {
      nodes: Array.from(nodeMap.values()).sort(
        (a, b) => b.conflicts - a.conflicts
      ),
      edges: Array.from(edgeMap.values()),
    };
  }, [conflicts, teamColors]);

  if (nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[400px] text-center text-meta text-muted">
        <p className="font-mono">No cross-team conflicts yet.</p>
        <p className="mt-2 max-w-xs">
          Conflicts are detected when a meeting is ingested and entities from
          different teams overlap semantically.
        </p>
      </div>
    );
  }

  // Geometry
  const W = 560;
  const H = 480;
  const cx = W / 2;
  const cy = H / 2;
  const R = Math.min(W, H) / 2 - 70;

  const positions = nodes.map((n, i) => {
    const angle = (i / nodes.length) * 2 * Math.PI - Math.PI / 2;
    return {
      ...n,
      x: cx + R * Math.cos(angle),
      y: cy + R * Math.sin(angle),
      angle,
    };
  });

  const posByTeam = new Map(positions.map((p) => [p.team, p]));

  const maxConflicts = Math.max(1, ...nodes.map((n) => n.conflicts));
  const radius = (n: NodeRow) =>
    8 + 14 * Math.sqrt(n.conflicts / maxConflicts);

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto"
        role="img"
        aria-label="Cross-team conflict graph"
      >
        {/* edges first, so nodes render on top */}
        {edges.map((e) => {
          const a = posByTeam.get(e.a)!;
          const b = posByTeam.get(e.b)!;
          const id = `${e.a}::${e.b}`;
          const involves =
            !hoveredTeam || e.a === hoveredTeam || e.b === hoveredTeam;
          const dim = (hoveredTeam && !involves) || (hoveredEdge && hoveredEdge !== id);
          const stroke = TYPE_COLORS[e.dominantType] || "#4A4A4A";
          const width = Math.min(7, 1.5 + e.severityWeight * 0.6);
          // Curve toward the center for a less spaghetti look
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          const tx = (cx - mx) * 0.2;
          const ty = (cy - my) * 0.2;
          const px = mx + tx;
          const py = my + ty;
          return (
            <path
              key={id}
              d={`M ${a.x} ${a.y} Q ${px} ${py} ${b.x} ${b.y}`}
              fill="none"
              stroke={stroke}
              strokeWidth={width}
              strokeOpacity={dim ? 0.12 : 0.55}
              strokeLinecap="round"
              className={cn(
                "transition-opacity duration-200",
                onSelectPair && "cursor-pointer"
              )}
              onMouseEnter={() => setHoveredEdge(id)}
              onMouseLeave={() => setHoveredEdge(null)}
              onClick={() => onSelectPair?.(e.a, e.b)}
            >
              <title>
                {`${e.a} ↔ ${e.b}: ${e.count} conflict${
                  e.count === 1 ? "" : "s"
                } (dominant: ${TYPE_LABEL[e.dominantType]})`}
              </title>
            </path>
          );
        })}

        {/* Nodes */}
        {positions.map((p) => {
          const r = radius(p);
          const dim = hoveredTeam && p.team !== hoveredTeam;
          // Push label outward along the angle so it doesn't sit on the node.
          const lx = p.x + Math.cos(p.angle) * (r + 14);
          const ly = p.y + Math.sin(p.angle) * (r + 14);
          // Anchor based on which side of the circle we're on
          const anchor =
            Math.abs(Math.cos(p.angle)) < 0.3
              ? "middle"
              : Math.cos(p.angle) > 0
              ? "start"
              : "end";
          const baseline =
            Math.abs(Math.sin(p.angle)) < 0.3
              ? "middle"
              : Math.sin(p.angle) > 0
              ? "hanging"
              : "auto";
          return (
            <g
              key={p.team}
              className={cn(
                "transition-opacity duration-200",
                dim ? "opacity-30" : "opacity-100"
              )}
              onMouseEnter={() => setHoveredTeam(p.team)}
              onMouseLeave={() => setHoveredTeam(null)}
              style={{ cursor: "pointer" }}
            >
              <circle
                cx={p.x}
                cy={p.y}
                r={r + 4}
                fill={p.color}
                fillOpacity={0.12}
              />
              <circle
                cx={p.x}
                cy={p.y}
                r={r}
                fill={p.color}
                stroke="#FFFFFF"
                strokeWidth={2}
              />
              <text
                x={lx}
                y={ly}
                textAnchor={anchor}
                dominantBaseline={baseline}
                className="font-serif fill-ink"
                fontSize={14}
              >
                {p.team}
              </text>
              <text
                x={lx}
                y={ly + 14}
                textAnchor={anchor}
                dominantBaseline={baseline}
                className="font-mono fill-muted"
                fontSize={11}
              >
                {p.conflicts} conflict{p.conflicts === 1 ? "" : "s"}
              </text>
              <title>
                {`${p.team} — ${p.conflicts} conflict${
                  p.conflicts === 1 ? "" : "s"
                }`}
              </title>
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-2 mt-3 text-meta font-mono text-muted">
        {(Object.entries(TYPE_LABEL) as [ConflictType, string][]).map(
          ([t, label]) => (
            <span key={t} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block w-3 h-[3px] rounded"
                style={{ backgroundColor: TYPE_COLORS[t] }}
              />
              {label}
            </span>
          )
        )}
        <span className="ml-auto text-eyebrow">
          Node size = conflicts involving the team · Edge weight = severity sum
        </span>
      </div>
    </div>
  );
}
