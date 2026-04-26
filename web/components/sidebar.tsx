"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  AlertTriangle,
  CalendarClock,
  Settings,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/teams", label: "Teams", icon: Users },
  { href: "/meetings", label: "Meetings", icon: CalendarClock },
  { href: "/conflicts", label: "Conflicts", icon: AlertTriangle },
  { href: "/setup", label: "Settings", icon: Settings },
] as const;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex fixed left-0 top-0 bottom-0 w-60 border-r border-rule bg-paper z-30 flex-col">
      <div className="px-5 h-16 flex items-center border-b border-rule shrink-0">
        <Link href="/" className="flex items-baseline gap-2.5">
          <span className="inline-flex items-center justify-center w-7 h-7 rounded bg-ink text-paper">
            <Activity size={15} strokeWidth={2.5} />
          </span>
          <span className="font-serif text-lead tracking-tight">SyncLayer</span>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-0.5">
        <div className="eyebrow px-3 mb-2">Workspace</div>
        {NAV.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded text-meta transition-colors",
                active
                  ? "bg-surface text-ink"
                  : "text-muted hover:text-ink hover:bg-surface"
              )}
            >
              <Icon
                size={16}
                strokeWidth={active ? 2.25 : 1.75}
                className={active ? "text-ink" : ""}
              />
              <span className={active ? "font-medium" : ""}>{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-rule p-4 text-eyebrow font-mono text-muted">
        SyncLayer · v0.3
      </div>
    </aside>
  );
}
