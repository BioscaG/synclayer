"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  AlertTriangle,
  CalendarClock,
  Settings,
  Activity,
  ArrowLeft,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { slug: "", label: "Overview", icon: LayoutDashboard },
  { slug: "teams", label: "Teams", icon: Users },
  { slug: "meetings", label: "Meetings", icon: CalendarClock },
  { slug: "conflicts", label: "Conflicts", icon: AlertTriangle },
  { slug: "setup", label: "Settings", icon: Settings },
] as const;

export function Sidebar() {
  const params = useParams<{ wsId: string }>();
  const wsId = params?.wsId || "";
  const pathname = usePathname();
  const base = `/w/${wsId}`;

  return (
    <aside className="hidden md:flex fixed left-0 top-0 bottom-0 w-60 border-r border-rule bg-paper z-30 flex-col">
      <div className="px-5 h-16 flex items-center border-b border-rule shrink-0">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="inline-flex items-center justify-center w-7 h-7 rounded-md bg-ink text-paper">
            <Activity size={14} strokeWidth={2.5} />
          </span>
          <span className="text-lead font-semibold tracking-tight">SyncLayer</span>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto py-4 px-3">
        <Link
          href="/"
          className="flex items-center gap-2.5 px-3 py-1.5 mb-3 rounded text-meta text-muted hover:text-ink hover:bg-surface transition-colors"
        >
          <ArrowLeft size={13} strokeWidth={1.75} />
          <span>All workspaces</span>
        </Link>

        <div className="px-3 pt-2 pb-2 eyebrow">Workspace</div>
        <div className="space-y-px">
          {NAV.map(({ slug, label, icon: Icon }) => {
            const href = slug ? `${base}/${slug}` : base;
            const active =
              slug === ""
                ? pathname === base || pathname === `${base}/`
                : pathname.startsWith(`${base}/${slug}`);
            return (
              <Link
                key={slug || "overview"}
                href={href}
                className={cn(
                  "relative flex items-center gap-3 pl-3 pr-3 py-1.5 rounded text-meta transition-colors",
                  active
                    ? "text-ink bg-surface"
                    : "text-slate hover:text-ink hover:bg-surface/60"
                )}
              >
                {/* Left-edge indicator on active */}
                {active && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 bg-ink rounded-r" />
                )}
                <Icon
                  size={15}
                  strokeWidth={active ? 2 : 1.5}
                  className={active ? "text-ink" : ""}
                />
                <span className={active ? "font-medium" : ""}>{label}</span>
              </Link>
            );
          })}
        </div>
      </nav>

      <div className="border-t border-rule px-4 py-3 text-eyebrow text-muted flex items-baseline justify-between">
        <span>SyncLayer</span>
        <span className="data-mono text-dim">v0.4</span>
      </div>
    </aside>
  );
}
