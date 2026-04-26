"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import type { Conflict } from "@/lib/types";
import { ConflictCard } from "@/components/conflict-card";

export interface NewConflictsResult {
  team: string;
  new_conflicts: Conflict[];
  extracted: number;
  triggered: boolean;
}

export function NewConflictsBanner({
  result,
  onDismiss,
}: {
  result: NewConflictsResult;
  onDismiss: () => void;
}) {
  const params = useParams<{ wsId: string }>();
  const wsId = params?.wsId || "";
  const dupes = result.new_conflicts.filter(
    (c) => c.conflict_type === "duplication"
  );
  const others = result.new_conflicts.filter(
    (c) => c.conflict_type !== "duplication"
  );
  return (
    <div className="panel border-critical/40 bg-critical/5 p-6">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <div className="eyebrow text-critical">Meeting just analysed</div>
          <h3 className="display text-h3 mt-1">
            {result.new_conflicts.length} new conflict
            {result.new_conflicts.length === 1 ? "" : "s"} detected
          </h3>
          <p className="text-body text-slate mt-2 max-w-2xl">
            {result.team} ingested {result.extracted} new entities. SyncLayer
            recompared everything in memory and found{" "}
            {dupes.length > 0 ? (
              <strong className="text-ink">
                {dupes.length} duplication{dupes.length === 1 ? "" : "s"}
              </strong>
            ) : (
              "no duplications"
            )}
            {others.length > 0
              ? ` and ${others.length} other issue${others.length === 1 ? "" : "s"}`
              : ""}{" "}
            across teams.
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <Link href={`/w/${wsId}/conflicts`} className="btn btn-primary">
            View all conflicts
          </Link>
          <button onClick={onDismiss} className="btn">
            Dismiss
          </button>
        </div>
      </div>
      <div className="space-y-3">
        {result.new_conflicts.slice(0, 3).map((c) => (
          <ConflictCard key={c.id} conflict={c} compact />
        ))}
        {result.new_conflicts.length > 3 && (
          <p className="text-meta text-muted font-mono">
            …and {result.new_conflicts.length - 3} more — view the full list in
            Conflicts.
          </p>
        )}
      </div>
    </div>
  );
}
