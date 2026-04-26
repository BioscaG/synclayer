"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { api as apiFactory } from "@/lib/api";
import type { CompanyConfig, Conflict } from "@/lib/types";
import { ConflictCard } from "@/components/conflict-card";
import { CONFLICT_LABEL, SEVERITY_LABEL, cn } from "@/lib/utils";
import { Empty } from "@/components/empty";
import { TeamConflictGraph } from "@/components/team-conflict-graph";

const SEVERITIES = ["critical", "warning"] as const;

export default function ConflictsPage() {
  const params = useParams<{ wsId: string }>();
  const wsId = params?.wsId || "";
  const api = useMemo(() => apiFactory(wsId), [wsId]);

  const [all, setAll] = useState<Conflict[]>([]);
  const [cfg, setCfg] = useState<CompanyConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [sev, setSev] = useState<Set<string>>(new Set(SEVERITIES));
  const [type, setType] = useState<Set<string>>(new Set());
  const [pairFilter, setPairFilter] = useState<[string, string] | null>(null);

  const refresh = () => {
    Promise.all([api.conflicts(), api.getConfig()])
      .then(([c, k]) => {
        setAll(c);
        setCfg(k);
        setType(new Set(c.map((x) => x.conflict_type)));
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
    // The poller may add new entities at any time; meetings re-run analysis
    // and rewrite conflicts. Poll lightly so the page never goes stale.
    const id = setInterval(() => {
      api.conflicts().then(setAll).catch(() => {});
    }, 12000);
    return () => clearInterval(id);
  }, [api]);

  const teamColors = useMemo(() => {
    const out: Record<string, string> = {};
    for (const [name, t] of Object.entries(cfg?.teams || {})) {
      if (t.color) out[name] = t.color;
    }
    return out;
  }, [cfg]);

  const filtered = useMemo(
    () =>
      all.filter((c) => {
        if (!sev.has(c.severity)) return false;
        if (!type.has(c.conflict_type)) return false;
        if (pairFilter) {
          const [a, b] = pairFilter;
          const ta = c.entity_a.team;
          const tb = c.entity_b.team;
          const inPair =
            (ta === a && tb === b) || (ta === b && tb === a);
          if (!inPair) return false;
        }
        return true;
      }),
    [all, sev, type, pairFilter]
  );

  const counts = SEVERITIES.reduce<Record<string, number>>(
    (acc, s) => ({ ...acc, [s]: filtered.filter((c) => c.severity === s).length }),
    {}
  );

  const types = Array.from(new Set(all.map((c) => c.conflict_type)));

  const toggle = (set: Set<string>, val: string, setter: (s: Set<string>) => void) => {
    const next = new Set(set);
    if (next.has(val)) next.delete(val);
    else next.add(val);
    setter(next);
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="eyebrow mb-2">Cross-team intelligence</div>
        <h1 className="display text-h2">Conflicts</h1>
        <p className="text-body text-slate mt-2 max-w-2xl">
          Every duplication, contradiction and hidden dependency uncovered by
          the most recent meeting analysis. Click two teams in the map to
          drill down to that pair.
        </p>
      </div>

      {loading ? (
        <p className="text-meta text-muted">Loading…</p>
      ) : all.length === 0 ? (
        <Empty
          title="No conflicts on record"
          description="Connect sources and ingest a meeting in Meetings — the next analysis will populate this view."
        />
      ) : (
        <>
          <div className="grid lg:grid-cols-[1.4fr_1fr] gap-4">
            {/* Filters + list */}
            <section className="space-y-4">
              <div className="panel-soft p-3 flex flex-wrap items-center gap-x-5 gap-y-2">
                <div className="flex items-center gap-2">
                  <span className="eyebrow">Severity</span>
                  {SEVERITIES.map((s) => (
                    <button
                      key={s}
                      onClick={() => toggle(sev, s, setSev)}
                      className={cn(
                        "tag transition-colors",
                        sev.has(s) ? "border-ink text-ink" : "opacity-50"
                      )}
                    >
                      {SEVERITY_LABEL[s]} · {counts[s] ?? 0}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="eyebrow">Type</span>
                  {types.map((t) => (
                    <button
                      key={t}
                      onClick={() => toggle(type, t, setType)}
                      className={cn(
                        "tag transition-colors",
                        type.has(t) ? "border-ink text-ink" : "opacity-50"
                      )}
                    >
                      {CONFLICT_LABEL[t] || t}
                    </button>
                  ))}
                </div>
                {pairFilter && (
                  <button
                    onClick={() => setPairFilter(null)}
                    className="tag tag-accent ml-auto"
                  >
                    {pairFilter[0]} ↔ {pairFilter[1]} · clear
                  </button>
                )}
              </div>

              {filtered.length === 0 ? (
                <p className="text-meta text-muted">
                  Nothing matches the active filters.
                </p>
              ) : (
                <div>
                  {filtered.map((c) => (
                    <ConflictCard key={c.id} conflict={c} />
                  ))}
                </div>
              )}
            </section>

            {/* Graph */}
            <aside className="lg:sticky lg:top-24 self-start">
              <section className="panel p-5">
                <header className="mb-3">
                  <div className="eyebrow mb-1">Map</div>
                  <h3 className="display text-h3">Cross-team friction</h3>
                  <p className="text-meta text-muted font-mono mt-1">
                    {all.length} conflict{all.length === 1 ? "" : "s"} across{" "}
                    {new Set(
                      all.flatMap((c) => [c.entity_a.team, c.entity_b.team])
                    ).size}{" "}
                    teams
                  </p>
                </header>
                <TeamConflictGraph
                  conflicts={all}
                  teamColors={teamColors}
                  onSelectPair={(a, b) => setPairFilter([a, b])}
                />
              </section>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
