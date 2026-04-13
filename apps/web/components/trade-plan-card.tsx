import { fmtNumber } from "@/lib/format";
import { TradePlan } from "@/lib/types";
import { Panel, SectionTitle } from "@/components/ui";

export function TradePlanCard({ plan, title = "Trade Plan Preview" }: { plan: TradePlan; title?: string }) {
  return (
    <Panel>
      <SectionTitle title={title} subtitle="Rule-based planning from score and ATR context" />
      <div className="grid gap-3 md:grid-cols-2">
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Bias</p>
          <p className="mt-1 text-lg font-semibold capitalize">{plan.bias}</p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Entry Zone</p>
          <p className="mt-1 text-lg font-semibold">
            ${fmtNumber(plan.entry_zone[0])} - ${fmtNumber(plan.entry_zone[1])}
          </p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Stop Loss</p>
          <p className="mt-1 text-lg font-semibold text-red">${fmtNumber(plan.stop_loss)}</p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Take Profit 1</p>
          <p className="mt-1 text-lg font-semibold text-green">${fmtNumber(plan.take_profit_1)}</p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Take Profit 2</p>
          <p className="mt-1 text-lg font-semibold text-green">${fmtNumber(plan.take_profit_2)}</p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Risk / Reward</p>
          <p className="mt-1 text-lg font-semibold">{fmtNumber(plan.risk_reward, 2)}</p>
        </Panel>
      </div>
      <Panel className="mt-3 bg-bg">
        <p className="text-xs text-slate-400">Invalidation</p>
        <p className="mt-1 text-sm text-slate-200">{plan.invalidation_note}</p>
      </Panel>
    </Panel>
  );
}

