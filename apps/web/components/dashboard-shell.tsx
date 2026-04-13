"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import type { ReactNode } from "react";

const tabs = [
  { label: "QuantEdge", href: "/quantedge" },
  { label: "SwingPulse", href: "/swingpulse" },
  { label: "Temel Analiz", href: "/temel-analiz" },
  { label: "QE Backtest", href: "/qe-backtest" },
  { label: "SP Backtest", href: "/sp-backtest" }
];

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen bg-bg text-slate-100">
      <div className="mx-auto max-w-7xl px-4 py-6 md:px-8">
        <header className="mb-6 rounded-2xl border border-stroke bg-gradient-to-r from-panel to-panelSoft p-4 shadow-glow">
          <div className="mb-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-cyan/20 ring-1 ring-cyan/40" />
            <div>
              <p className="text-sm text-slate-400">Rule-Based Swing Engine</p>
              <h1 className="text-xl font-semibold tracking-tight">TradeGhost Dashboard</h1>
            </div>
          </div>
          <nav className="flex flex-wrap gap-2">
            {tabs.map((tab) => (
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
            ))}
          </nav>
        </header>
        {children}
      </div>
    </div>
  );
}
