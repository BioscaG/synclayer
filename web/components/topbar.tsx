"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronDown } from "lucide-react";
import { workspaceApi } from "@/lib/api";
import type { WorkspaceSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Topbar() {
  const params = useParams<{ wsId: string }>();
  const wsId = params?.wsId || "";

  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [open, setOpen] = useState(false);

  const loadWorkspaces = () => {
    workspaceApi
      .list()
      .then(setWorkspaces)
      .catch(() => {});
  };

  useEffect(() => {
    loadWorkspaces();
    const id = setInterval(loadWorkspaces, 8000);
    const onChange = () => loadWorkspaces();
    window.addEventListener("synclayer:config-changed", onChange);
    return () => {
      clearInterval(id);
      window.removeEventListener("synclayer:config-changed", onChange);
    };
  }, []);

  const current = workspaces.find((w) => w.id === wsId);

  return (
    <header className="sticky top-0 z-20 bg-paper/85 backdrop-blur border-b border-rule">
      <div className="h-14 flex items-center justify-between gap-6 px-6 lg:px-8">
        <div className="relative">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-2 min-w-0 hover:bg-surface rounded px-2 py-1 -mx-2 transition-colors"
          >
            {current && (
              <span
                className="inline-block w-1.5 h-1.5 rounded-sm shrink-0"
                style={{ backgroundColor: current.color }}
              />
            )}
            <span className="text-body font-semibold truncate">
              {current?.name || "—"}
            </span>
            <ChevronDown
              size={13}
              className={cn(
                "text-muted transition-transform shrink-0",
                open && "rotate-180"
              )}
            />
          </button>
          {open && (
            <>
              <button
                aria-hidden
                tabIndex={-1}
                onClick={() => setOpen(false)}
                className="fixed inset-0 z-10 cursor-default"
              />
              <div className="absolute left-0 top-full mt-1.5 z-20 panel min-w-[280px] py-1 max-h-[60vh] overflow-y-auto">
                <div className="px-3 py-1.5 eyebrow">Switch workspace</div>
                {workspaces.map((w) => (
                  <Link
                    key={w.id}
                    href={`/w/${w.id}`}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "flex items-center gap-2.5 px-3 py-2 hover:bg-surface transition-colors",
                      w.id === wsId && "bg-surface"
                    )}
                  >
                    <span
                      className="inline-block w-1.5 h-1.5 rounded-sm shrink-0"
                      style={{ backgroundColor: w.color }}
                    />
                    <span className="text-body truncate flex-1">{w.name}</span>
                    <span className="data-mono text-eyebrow text-muted shrink-0">
                      {w.entities}
                    </span>
                  </Link>
                ))}
                <div className="border-t border-rule mt-1 pt-1">
                  <Link
                    href="/"
                    onClick={() => setOpen(false)}
                    className="block px-3 py-2 text-meta text-accent hover:bg-surface transition-colors"
                  >
                    + new workspace
                  </Link>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
