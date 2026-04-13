import clsx from "clsx";
import type { ReactNode } from "react";

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={clsx("rounded-2xl border border-stroke bg-panel p-4 md:p-5", className)}>{children}</section>;
}

export function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Panel className="bg-panelSoft">
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
    </Panel>
  );
}

export function Pill({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={clsx("inline-flex rounded-full border px-2.5 py-1 text-xs font-medium tracking-wide", className)}>
      {children}
    </span>
  );
}

export function SectionTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-lg font-semibold">{title}</h2>
      {subtitle ? <p className="text-sm text-slate-400">{subtitle}</p> : null}
    </div>
  );
}
