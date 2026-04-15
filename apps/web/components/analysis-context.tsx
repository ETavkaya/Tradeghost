"use client";

import { createContext, ReactNode, useContext, useMemo, useState } from "react";
import { CombinedAnalysisResponse } from "@/lib/types";

type AnalysisContextValue = {
  analysis: CombinedAnalysisResponse | null;
  setAnalysis: (value: CombinedAnalysisResponse | null) => void;
};

const AnalysisContext = createContext<AnalysisContextValue | undefined>(undefined);

export function AnalysisContextProvider({ children }: { children: ReactNode }) {
  const [analysis, setAnalysis] = useState<CombinedAnalysisResponse | null>(null);
  const value = useMemo(() => ({ analysis, setAnalysis }), [analysis]);
  return <AnalysisContext.Provider value={value}>{children}</AnalysisContext.Provider>;
}

export function useAnalysisContext() {
  const ctx = useContext(AnalysisContext);
  if (!ctx) {
    throw new Error("useAnalysisContext must be used inside AnalysisContextProvider");
  }
  return ctx;
}
