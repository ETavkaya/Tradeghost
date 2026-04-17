"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import type { Data, Layout, Shape } from "plotly.js";
import { AnalysisChart, BacktestMarker } from "@/lib/types";
import { premiumDarkPlotlyTemplate } from "@/lib/plotly-theme";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

type Props = {
  chart: AnalysisChart;
  title: string;
  markers?: BacktestMarker[];
  markerMode?: "trades" | "decision";
};

const markerStyle: Record<string, { color: string; symbol: string; name: string }> = {
  entry: { color: "#23D18B", symbol: "diamond", name: "Entry" },
  exit_stop: { color: "#F2545B", symbol: "x", name: "Stop Exit" },
  exit_target: { color: "#19D3F3", symbol: "triangle-up", name: "Target Exit" },
  exit_score: { color: "#F2B94B", symbol: "square", name: "Score Exit" },
  exit_timeout: { color: "#B9C4D7", symbol: "circle", name: "Timeout Exit" },
  exit_forced: { color: "#8FA1B8", symbol: "circle-open", name: "Forced Exit" },
  exit: { color: "#F2545B", symbol: "diamond-open", name: "Exit" },
  reference_stop: { color: "#F2545B", symbol: "circle-open", name: "Reference Stop" },
  reference_target: { color: "#23D18B", symbol: "triangle-down-open", name: "Reference Target" },
  threshold_fail: { color: "#98A2B3", symbol: "circle", name: "Threshold Fail" },
  regime_fail: { color: "#A277FF", symbol: "square", name: "Regime Fail" },
  location_fail: { color: "#FF9E44", symbol: "diamond", name: "Location Fail" },
  trigger_fail: { color: "#F2B94B", symbol: "triangle-up", name: "Trigger Fail" },
  watchlist: { color: "#47A3FF", symbol: "circle-open", name: "Watchlist" },
  actionable: { color: "#23D18B", symbol: "star", name: "Actionable" }
};

function buildMarkerTraces(markers: BacktestMarker[], candleCloseByDate: Record<string, number>, markerMode: "trades" | "decision"): Data[] {
  const grouped = new Map<string, BacktestMarker[]>();
  for (const marker of markers) {
    const key = marker.marker_type;
    if (!grouped.has(key)) {
      grouped.set(key, []);
    }
    grouped.get(key)!.push(marker);
  }

  const traces: Data[] = [];
  for (const [markerType, rows] of grouped.entries()) {
    const style = markerStyle[markerType] ?? { color: "#F2B94B", symbol: "diamond", name: markerType };
    traces.push({
      type: "scatter",
      mode: "markers",
      x: rows.map((m) => m.date),
      y: rows.map((m) => (m.price > 0 ? m.price : (candleCloseByDate[m.date] ?? 0))),
      name: style.name,
      marker: {
        size: 10,
        symbol: style.symbol,
        color: style.color,
        line: { color: "#070B16", width: 1.2 }
      },
      text: rows.map((m) => m.hover_text ?? m.label),
      hovertemplate: "%{text}<extra></extra>",
      legendgroup: markerMode === "decision" ? "decision_markers" : "trade_markers"
    });
  }
  return traces;
}

function buildLegendTrace(name: string, color: string, dash: "solid" | "dot" | "dash", x0: string, x1: string, sampleY: number): Data {
  return {
    type: "scatter",
    mode: "lines",
    x: [x0, x1],
    y: [sampleY, sampleY],
    name,
    line: { color, width: 2, dash },
    showlegend: true,
    opacity: 1,
    hoverinfo: "skip"
  };
}

export function UnifiedAnalysisChart({ chart, title, markers = [], markerMode = "trades" }: Props) {
  const [expanded, setExpanded] = useState(false);

  const x = chart.candles.map((c) => c.date);
  const candleCloseByDate = Object.fromEntries(chart.candles.map((c) => [c.date, c.close]));
  const candlestick: Data = {
    type: "candlestick",
    x,
    open: chart.candles.map((c) => c.open),
    high: chart.candles.map((c) => c.high),
    low: chart.candles.map((c) => c.low),
    close: chart.candles.map((c) => c.close),
    name: "Price",
    increasing: { line: { color: "#23D18B", width: 1.2 } },
    decreasing: { line: { color: "#F2545B", width: 1.2 } }
  };

  const ema20: Data = { type: "scatter", mode: "lines", x: chart.ema_20.map((p) => p.date), y: chart.ema_20.map((p) => p.value), name: "EMA 20", line: { color: "#19D3F3", width: 1.8 } };
  const ema50: Data = { type: "scatter", mode: "lines", x: chart.ema_50.map((p) => p.date), y: chart.ema_50.map((p) => p.value), name: "EMA 50", line: { color: "#9A8DFF", width: 1.8 } };
  const ema100: Data = { type: "scatter", mode: "lines", x: chart.ema_100.map((p) => p.date), y: chart.ema_100.map((p) => p.value), name: "EMA 100", line: { color: "#F2B94B", width: 1.7 } };
  const ema200: Data = { type: "scatter", mode: "lines", x: chart.ema_200.map((p) => p.date), y: chart.ema_200.map((p) => p.value), name: "EMA 200", line: { color: "#E06C9F", width: 1.7 } };

  const currentPoint: Data = {
    type: "scatter",
    mode: "text+markers",
    x: [x[x.length - 1]],
    y: [chart.current_price],
    name: "Current",
    text: ["Current"],
    textposition: "top right",
    marker: { size: 9, color: "#19D3F3", line: { color: "#070B16", width: 1.5 } }
  };

  const shapes: Partial<Shape>[] = [];
  const lineStyle = (color: string, dash: Shape["line"]["dash"] = "solid") => ({ color, width: 1.25, dash });

  for (const level of chart.support_levels) {
    shapes.push({ type: "line", x0: x[0], x1: x[x.length - 1], y0: level, y1: level, line: lineStyle("#23D18B", "dot") });
  }
  for (const level of chart.resistance_levels) {
    shapes.push({ type: "line", x0: x[0], x1: x[x.length - 1], y0: level, y1: level, line: lineStyle("#F2545B", "dot") });
  }
  for (const level of Object.values(chart.fibonacci_levels)) {
    shapes.push({ type: "line", x0: x[0], x1: x[x.length - 1], y0: level, y1: level, line: lineStyle("#F2B94B", "dash") });
  }

  if (chart.trade_plan_overlay) {
    const [entryLow, entryHigh] = chart.trade_plan_overlay.entry_zone;
    shapes.push({ type: "rect", x0: x[Math.max(0, x.length - 25)], x1: x[x.length - 1], y0: entryLow, y1: entryHigh, fillcolor: "rgba(25,211,243,0.10)", line: { color: "rgba(25,211,243,0.35)", width: 1 } });
    shapes.push({ type: "line", x0: x[Math.max(0, x.length - 25)], x1: x[x.length - 1], y0: chart.trade_plan_overlay.stop_loss, y1: chart.trade_plan_overlay.stop_loss, line: lineStyle("#F2545B") });
    shapes.push({ type: "line", x0: x[Math.max(0, x.length - 25)], x1: x[x.length - 1], y0: chart.trade_plan_overlay.take_profit_1, y1: chart.trade_plan_overlay.take_profit_1, line: lineStyle("#23D18B") });
    shapes.push({ type: "line", x0: x[Math.max(0, x.length - 25)], x1: x[x.length - 1], y0: chart.trade_plan_overlay.take_profit_2, y1: chart.trade_plan_overlay.take_profit_2, line: lineStyle("#23D18B", "dash") });
  }

  const legendOverlayTraces: Data[] = [
    buildLegendTrace("Support (dotted)", "#23D18B", "dot", x[0], x[x.length - 1], chart.current_price),
    buildLegendTrace("Resistance (dotted)", "#F2545B", "dot", x[0], x[x.length - 1], chart.current_price),
    buildLegendTrace("Reference/Fib (dashed)", "#F2B94B", "dash", x[0], x[x.length - 1], chart.current_price)
  ];

  if (chart.trade_plan_overlay) {
    legendOverlayTraces.push(buildLegendTrace("Trade Plan Stop", "#F2545B", "solid", x[0], x[x.length - 1], chart.current_price));
    legendOverlayTraces.push(buildLegendTrace("Trade Plan Target", "#23D18B", "solid", x[0], x[x.length - 1], chart.current_price));
  }

  const markerTraces = buildMarkerTraces(markers, candleCloseByDate, markerMode);
  const baseLayout: Partial<Layout> = {
    ...premiumDarkPlotlyTemplate,
    title: { text: title, font: { size: 14, color: "#DCE6FF" } },
    xaxis: { ...premiumDarkPlotlyTemplate.xaxis, rangeslider: { visible: false } },
    yaxis: { ...premiumDarkPlotlyTemplate.yaxis, tickprefix: "$" },
    shapes: shapes as Layout["shapes"],
    hovermode: "x unified",
    autosize: true,
    legend: { ...premiumDarkPlotlyTemplate.legend, orientation: "h", yanchor: "bottom", y: 1.02, x: 0 }
  };

  const renderPlot = (height: number) => (
    <Plot
      data={[candlestick, ema20, ema50, ema100, ema200, currentPoint, ...legendOverlayTraces, ...markerTraces]}
      layout={{ ...baseLayout, height }}
      config={{ displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d"] }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );

  return (
    <>
      <div className="overflow-hidden rounded-2xl border border-stroke bg-panel p-2 md:p-3">
        <div className="mb-2 flex items-center justify-end">
          <button type="button" onClick={() => setExpanded(true)} className="rounded-md border border-stroke px-3 py-1 text-xs text-slate-300 hover:text-cyan">
            Expand Chart
          </button>
        </div>
        {renderPlot(520)}
      </div>
      {expanded ? (
        <div className="fixed inset-0 z-50 bg-bg/95 p-4">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm text-slate-300">Expanded Chart View</p>
            <button type="button" onClick={() => setExpanded(false)} className="rounded-md border border-stroke px-3 py-1 text-xs text-slate-300 hover:text-cyan">
              Close
            </button>
          </div>
          <div className="h-[calc(100vh-70px)] rounded-xl border border-stroke bg-panel p-2">
            {renderPlot(900)}
          </div>
        </div>
      ) : null}
    </>
  );
}
