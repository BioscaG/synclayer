"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CompanyConfig } from "@/lib/types";

export default function SettingsPage() {
  const [cfg, setCfg] = useState<CompanyConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = () => {
    setLoading(true);
    api
      .getConfig()
      .then(setCfg)
      .finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const renameCompany = async (newName: string) => {
    if (!cfg) return;
    setBusy("company");
    try {
      await api.setConfig({ ...cfg, name: newName });
      refresh();
      window.dispatchEvent(new CustomEvent("synclayer:config-changed"));
    } finally {
      setBusy(null);
    }
  };

  if (loading || !cfg)
    return <p className="text-meta text-muted">Loading…</p>;

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <div className="eyebrow mb-2">Workspace</div>
        <h1 className="display text-h2">Settings</h1>
        <p className="text-body text-slate mt-2">
          Workspace-level configuration. Team management lives in{" "}
          <span className="font-mono">Teams</span> and meeting ingest in{" "}
          <span className="font-mono">Meetings</span>.
        </p>
      </div>

      <section className="panel p-6">
        <header className="mb-4">
          <div className="eyebrow mb-1">Company</div>
          <h3 className="display text-h3">Identity</h3>
        </header>
        <label className="block max-w-md">
          <div className="eyebrow mb-2">Company name</div>
          <input
            defaultValue={cfg.name}
            onBlur={(e) => {
              if (e.target.value !== cfg.name) renameCompany(e.target.value);
            }}
            disabled={busy === "company"}
            className="input"
            placeholder="My Company"
          />
          <p className="text-meta text-muted font-mono mt-2">
            Shown in the workspace header. Saved when the field loses focus.
          </p>
        </label>
      </section>
    </div>
  );
}
