export function fmtNumber(value: number | undefined, digits = 2): string {
  if (value === undefined || Number.isNaN(value)) return "N/A";
  return value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function decisionFromScore(score: number): "Strong Candidate" | "Watchlist" | "Avoid" {
  if (score >= 75) return "Strong Candidate";
  if (score >= 55) return "Watchlist";
  return "Avoid";
}

export function decisionBadgeClass(score: number): string {
  if (score >= 75) return "bg-green/20 text-green border-green/40";
  if (score >= 55) return "bg-amber/20 text-amber border-amber/40";
  return "bg-red/20 text-red border-red/40";
}

