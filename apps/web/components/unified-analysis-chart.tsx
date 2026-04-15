"use client";

import dynamic from "next/dynamic";
import type { Data, Layout, Shape } from "plotly.js";
import { AnalysisChart, BacktestMarker } from "@/lib/types";
import { premiumDarkPlotlyTemplate } from "@/lib/plotly-theme";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

type Props = {
  chart: AnalysisChart;
  title: string;
  markers?: BacktestMarker[];
};

const markerColor: Record<string, string> = {
  entry: "#23D18B",
  exit: "#F2545B",
  stop: "#F2545B",
  take_profit: "#19D3F3"
};

export function UnifiedAnalysisChart({ chart, title, markers = [] }: Props) {
  const x = chart.candles.map((c) => c.date);
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

  const ema20: Data = {
    type: "scatter",
    mode: "lines",
    x: chart.ema_20.map((p) => p.date),
    y: chart.ema_20.map((p) => p.value),
    name: "EMA 20",
    line: { color: "#19D3F3", width: 1.8 }
  };

  const ema50: Data = {
    type: "scatter",
    mode: "lines",
    x: chart.ema_50.map((p) => p.date),
    y: chart.ema_50.map((p) => p.value),
    name: "EMA 50",
    line: { color: "#8F7CFF", width: 1.8 }
  };

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

  const markerTrace: Data | null = markers.length
    ? {
        type: "scatter",
        mode: "markers",
        x: markers.map((m) => m.date),
        y: markers.map((m) => m.price),
        name: "Backtest Markers",
        marker: {
          size: 10,
          symbol: "diamond",
          color: markers.map((m) => markerColor[m.marker_type] ?? "#F2B94B"),
          line: { color: "#070B16", width: 1.2 }
        },
        text: markers.map((m) => m.label),
        hovertemplate: "%{text}<br>%{x}<br>$%{y:.2f}<extra></extra>"
      }
    : null;

  const shapes: Partial<Shape>[] = [];
  const lineStyle = (color: string, dash: Shape["line"]["dash"] = "solid") => ({ color, width: 1.25, dash });

  for (const level of chart.support_levels) {
    shapes.push({
      type: "line",
      x0: x[0],
      x1: x[x.length - 1],
      y0: level,
      y1: level,
      line: lineStyle("#23D18B", "dot")
    });
  }
  for (const level of chart.resistance_levels) {
    shapes.push({
      type: "line",
      x0: x[0],
      x1: x[x.length - 1],
      y0: level,
      y1: level,
      line: lineStyle("#F2545B", "dot")
    });
  }
  for (const level of Object.values(chart.fibonacci_levels)) {
    shapes.push({
      type: "line",
      x0: x[0],
      x1: x[x.length - 1],
      y0: level,
      y1: level,
      line: lineStyle("#F2B94B", "dash")
    });
  }

  if (chart.trade_plan_overlay) {
    const [entryLow, entryHigh] = chart.trade_plan_overlay.entry_zone;
    shapes.push({
      type: "rect",
      x0: x[Math.max(0, x.length - 25)],
      x1: x[x.length - 1],
      y0: entryLow,
      y1: entryHigh,
      fillcolor: "rgba(25,211,243,0.10)",
      line: { color: "rgba(25,211,243,0.35)", width: 1 }
    });

    shapes.push({
      type: "line",
      x0: x[Math.max(0, x.length - 25)],
      x1: x[x.length - 1],
      y0: chart.trade_plan_overlay.stop_loss,
      y1: chart.trade_plan_overlay.stop_loss,
      line: lineStyle("#F2545B")
    });
    shapes.push({
      type: "line",
      x0: x[Math.max(0, x.length - 25)],
      x1: x[x.length - 1],
      y0: chart.trade_plan_overlay.take_profit_1,
      y1: chart.trade_plan_overlay.take_profit_1,
      line: lineStyle("#23D18B")
    });
    shapes.push({
      type: "line",
      x0: x[Math.max(0, x.length - 25)],
      x1: x[x.length - 1],
      y0: chart.trade_plan_overlay.take_profit_2,
      y1: chart.trade_plan_overlay.take_profit_2,
      line: lineStyle("#23D18B", "dash")
    });
  }

  const layout: Partial<Layout> = {
    ...premiumDarkPlotlyTemplate,
    title: { text: title, font: { size: 14, color: "#DCE6FF" } },
    xaxis: { ...premiumDarkPlotlyTemplate.xaxis, rangeslider: { visible: false } },
    yaxis: { ...premiumDarkPlotlyTemplate.yaxis, tickprefix: "$" },
    shapes: shapes as Layout["shapes"],
    hovermode: "x unified",
    autosize: true,
    height: 520
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-stroke bg-panel p-2 md:p-3">
      <Plot
        data={markerTrace ? [candlestick, ema20, ema50, currentPoint, markerTrace] : [candlestick, ema20, ema50, currentPoint]}
        layout={layout}
        config={{ displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d"] }}
        style={{ width: "100%", height: "100%" }}
        useResizeHandler
      />
    </div>
  );
}
