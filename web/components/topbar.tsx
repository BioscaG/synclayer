"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function Topbar() {
  const [companyName, setCompanyName] = useState<string>("");

  const loadConfig = () => {
    api
      .getConfig()
      .then((cfg) => setCompanyName(cfg.name || "My Company"))
      .catch(() => {});
  };

  useEffect(() => {
    loadConfig();
    const id = setInterval(loadConfig, 8000);
    // Pages that mutate company config dispatch this so the topbar updates
    // instantly instead of waiting for the next poll tick.
    const onConfigChange = () => loadConfig();
    window.addEventListener("synclayer:config-changed", onConfigChange);
    return () => {
      clearInterval(id);
      window.removeEventListener("synclayer:config-changed", onConfigChange);
    };
  }, []);

  return (
    <header className="sticky top-0 z-20 bg-paper/85 backdrop-blur border-b border-rule">
      <div className="h-16 flex items-center gap-6 px-6 lg:px-8">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-meta text-muted hidden sm:inline">
            Workspace
          </span>
          <span className="text-meta text-muted">/</span>
          <span className="text-lead font-semibold truncate">
            {companyName || "—"}
          </span>
        </div>
      </div>
    </header>
  );
}
