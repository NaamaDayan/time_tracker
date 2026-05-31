import type { ActivityWindow } from "./types";

export function windowOpacity(win: ActivityWindow): number {
  if (win.confirmed_by_user) return 1.0;
  if (win.confidence >= 0.8) return 1.0;
  if (win.confidence >= 0.5) return 0.85;
  return 0.7;
}

export function showConfidenceDot(win: ActivityWindow): boolean {
  return !win.confirmed_by_user && win.confidence < 0.8;
}

export function confidenceDotPulse(win: ActivityWindow): boolean {
  return win.confidence < 0.5;
}

export function confidenceLabel(win: ActivityWindow): string {
  if (win.confidence >= 0.8) return "high";
  if (win.confidence >= 0.5) return "medium";
  return "low — please check";
}
