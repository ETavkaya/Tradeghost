"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useAnalysisContext } from "@/components/analysis-context";
import { api } from "@/lib/api";

const tabs = [
  { label: "Scanner", href: "/scanner" },
  { label: "Analysis", href: "/analysis" },
  { label: "Backtest", href: "/backtest" },
  { label: "Monitor", href: "/monitor" },
  { label: "Intelligence", href: "/intelligence" },
  { label: "Logic", href: "/logic" },
  { label: "Logs", href: "/logs" }
];

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { analysis } = useAnalysisContext();
  const [watchlistCount, setWatchlistCount] = useState(0);
  const [activeRulesCount, setActiveRulesCount] = useState(0);

  useEffect(() => {
    const load = async () => {
      try {
        const [watchlists, alerts] = await Promise.all([
          api.listWatchlists(),
          api.listAlertRules(),
        ]);
        setWatchlistCount(watchlists.length);
        setActiveRulesCount(alerts.filter((row) => row.is_enabled).length);
      } catch {
        setWatchlistCount(0);
        setActiveRulesCount(0);
      }
    };
    load();
  }, [pathname]);

  return (
    <div className="min-h-screen bg-bg text-slate-100">
      <div className="mx-auto max-w-7xl px-4 py-6 md:px-8">
        <header className="mb-6 rounded-2xl border border-stroke bg-gradient-to-r from-panel to-panelSoft p-4 shadow-glow">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-xl bg-cyan/20 ring-1 ring-cyan/40" />
              <div>
                <p className="text-sm text-slate-400">Rule-Based Swing Engine</p>
                <h1 className="text-xl font-semibold tracking-tight">TradeGhost Dashboard</h1>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              <span className="rounded-md border border-stroke bg-panel/70 px-2 py-1 text-slate-300">Watchlists: {watchlistCount}</span>
              <span className="rounded-md border border-stroke bg-panel/70 px-2 py-1 text-slate-300">Active Rules: {activeRulesCount}</span>
            </div>
          </div>
          <nav className="flex flex-wrap gap-2">
            {tabs.map((tab) => (
              tab.href === "/backtest" && !analysis ? (
                <span
                  key={tab.href}
                  className="cursor-not-allowed rounded-lg border border-stroke bg-panel/70 px-4 py-2 text-sm font-medium text-slate-500"
                  title="Run analysis first to unlock backtest."
                >
                  {tab.label}
                </span>
              ) : (
                <Link
                  key={tab.href}
                  href={tab.href}
                  className={clsx(
                    "rounded-lg border px-4 py-2 text-sm font-medium transition",
                    pathname === tab.href
                      ? "border-cyan/50 bg-cyan/15 text-cyan"
                      : "border-stroke bg-panel/80 text-slate-300 hover:border-cyan/30 hover:text-cyan"
                  )}
                >
                  {tab.label}
                </Link>
              )
            ))}
          </nav>
        </header>
        {children}
      </div>
    </div>
  );
}
