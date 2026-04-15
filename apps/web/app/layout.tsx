import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { DashboardShell } from "@/components/dashboard-shell";
import { AnalysisContextProvider } from "@/components/analysis-context";

export const metadata: Metadata = {
  title: "TradeGhost",
  description: "Rule-based swing trading analysis dashboard"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AnalysisContextProvider>
          <DashboardShell>{children}</DashboardShell>
        </AnalysisContextProvider>
      </body>
    </html>
  );
}
