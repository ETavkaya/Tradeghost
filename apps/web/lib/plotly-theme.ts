import { Layout } from "plotly.js";

export const premiumDarkPlotlyTemplate: Partial<Layout> = {
  paper_bgcolor: "#0E1425",
  plot_bgcolor: "#070B16",
  font: { color: "#DCE6FF", family: "Inter, ui-sans-serif, system-ui" },
  xaxis: {
    showgrid: true,
    gridcolor: "rgba(30,44,77,0.45)",
    linecolor: "#1E2C4D",
    tickfont: { color: "#9FB0D0" }
  },
  yaxis: {
    showgrid: true,
    gridcolor: "rgba(30,44,77,0.45)",
    linecolor: "#1E2C4D",
    tickfont: { color: "#9FB0D0" }
  },
  margin: { l: 50, r: 24, t: 26, b: 40 },
  legend: {
    orientation: "h",
    y: 1.02,
    x: 0,
    bgcolor: "rgba(0,0,0,0)",
    font: { color: "#C7D5F4" }
  }
};
