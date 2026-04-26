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

const SEVERITY_WEIGHT: Record<string, number> = {
  critical: 3,
  warning: 2,
  info: 1,
};

interface NodeRow {
  team: string;
  conflicts: number;
  color: string;
}

/** One drawable edge — uniquely identified by (pair, conflict_type). */
interface TypedEdge {
  pairKey: string;     // "a::b" sorted
  a: string;
  b: string;
  type: ConflictType;
  count: number;       // how many conflicts of this type in this pair
  severityWeight: number;
}

export function TeamConflictGraph({
  conflicts,
  teamColors,
  onSelectPair,
}: {
  conflicts: Conflict[];
  teamColors?: Record<string, string>;
  onSelectPair?: (a: string, b: string) => void;
}) {
  const [hoveredTeam, setHoveredTeam] = useState<string | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null);

  const { nodes, edges, edgesByPair } = useMemo(() => {
    const nodeMap = new Map<string, NodeRow>();
    const typedMap = new Map<string, TypedEdge>();

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
      const pairKey = `${x}::${y}`;
      const key = `${pairKey}::${c.conflict_type}`;
      let edge = typedMap.get(key);
      if (!edge) {
        edge = {
          pairKey,
          a: x,
          b: y,
          type: c.conflict_type,
          count: 0,
          severityWeight: 0,
        };
        typedMap.set(key, edge);
      }
      edge.count += 1;
      edge.severityWeight += SEVERITY_WEIGHT[c.severity] || 1;
    }

    // Group typed edges by pair so we can offset them perpendicularly
    // (multiple conflicts between the same two teams stack as parallel lines).
    const byPair = new Map<string, TypedEdge[]>();
    for (const edge of typedMap.values()) {
      const list = byPair.get(edge.pairKey) || [];
      list.push(edge);
      byPair.set(edge.pairKey, list);
    }
    // Stable color order so the visual doesn't jitter when re-rendering.
    const TYPE_ORDER: ConflictType[] = [
      "duplication",
      "contradiction",
      "dependency",
      "say_vs_do",
    ];
    for (const list of byPair.values()) {
      list.sort(
        (a, b) => TYPE_ORDER.indexOf(a.type) - TYPE_ORDER.indexOf(b.type)
      );
    }

    return {
      nodes: Array.from(nodeMap.values()).sort(
        (a, b) => b.conflicts - a.conflicts
      ),
      edges: Array.from(typedMap.values()),
      edgesByPair: byPair,
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

  // Offset spacing between parallel edges in the same pair (px, in viewBox units).
  const PARALLEL_SPACING = 7;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto"
        role="img"
        aria-label="Cross-team conflict graph"
      >
        {edges.map((e) => {
          const a = posByTeam.get(e.a)!;
          const b = posByTeam.get(e.b)!;
          // Perpendicular unit vector to the chord — used to offset parallel
          // edges between the same pair so they don't overlap.
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const len = Math.hypot(dx, dy) || 1;
          const perpX = -dy / len;
          const perpY = dx / len;

          const pairList = edgesByPair.get(e.pairKey) || [];
          const idxInPair = pairList.indexOf(e);
          const total = pairList.length;
          const offsetSteps = idxInPair - (total - 1) / 2;
          const offset = offsetSteps * PARALLEL_SPACING;

          // Slight outward bow so the line reads as a curve, not a chord
          // through dense node areas. Bow direction matches the offset side
          // so parallel edges fan out cleanly.
          const bow = total > 1 ? Math.sign(offsetSteps || 1) * 6 : 0;
          const totalOffset = offset + bow;

          const mx = (a.x + b.x) / 2 + perpX * totalOffset;
          const my = (a.y + b.y) / 2 + perpY * totalOffset;

          const id = `${e.pairKey}::${e.type}`;
          const involves =
            !hoveredTeam || e.a === hoveredTeam || e.b === hoveredTeam;
          const dim =
            (hoveredTeam && !involves) || (hoveredEdge && hoveredEdge !== id);

          const stroke = TYPE_COLORS[e.type] || "#71717A";
          const width = Math.min(5, 1.25 + e.severityWeight * 0.5);

          return (
            <path
              key={id}
              d={`M ${a.x} ${a.y} Q ${mx} ${my} ${b.x} ${b.y}`}
              fill="none"
              stroke={stroke}
              strokeWidth={width}
              strokeOpacity={dim ? 0.12 : 0.7}
              strokeLinecap="round"
              className={cn(
                "transition-opacity duration-150",
                onSelectPair && "cursor-pointer"
              )}
              onMouseEnter={() => setHoveredEdge(id)}
              onMouseLeave={() => setHoveredEdge(null)}
              onClick={() => onSelectPair?.(e.a, e.b)}
            >
              <title>
                {`${e.a} ↔ ${e.b}: ${e.count} ${TYPE_LABEL[e.type]}${
                  e.count === 1 ? "" : "s"
                }`}
              </title>
            </path>
          );
        })}

        {/* Nodes */}
        {positions.map((p) => {
          const r = radius(p);
          const dim = hoveredTeam && p.team !== hoveredTeam;
          const lx = p.x + Math.cos(p.angle) * (r + 14);
          const ly = p.y + Math.sin(p.angle) * (r + 14);
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
                className="font-sans fill-ink"
                fontSize={13}
                fontWeight={500}
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
          Node size = conflicts involving the team · Line weight = severity
        </span>
      </div>
    </div>
  );
}
