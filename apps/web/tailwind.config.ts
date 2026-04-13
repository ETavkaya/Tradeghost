import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#070B16",
        panel: "#0E1425",
        panelSoft: "#121C33",
        stroke: "#1E2C4D",
        cyan: "#19D3F3",
        violet: "#8F7CFF",
        green: "#23D18B",
        amber: "#F2B94B",
        red: "#F2545B"
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(25, 211, 243, 0.2), 0 10px 30px rgba(0, 0, 0, 0.35)"
      }
    }
  },
  plugins: []
};

export default config;

