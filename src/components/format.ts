const INTEGER_FORMAT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function formatUnavailable(reason: string): string {
  const normalized = reason.trim();
  return `Unavailable: ${normalized || "value unavailable"}`;
}

export function formatRate(value: number | null | undefined, unavailableReason = "value unavailable"): string {
  return value == null ? formatUnavailable(unavailableReason) : `${(value * 100).toFixed(1)}%`;
}

export function formatPercentagePoints(value: number | null | undefined, unavailableReason = "value unavailable"): string {
  return value == null ? formatUnavailable(unavailableReason) : `${value >= 0 ? "+" : ""}${value.toFixed(1)} pp`;
}

export function formatGold(value: number | null | undefined, unavailableReason = "value unavailable"): string {
  if (value == null) return formatUnavailable(unavailableReason);
  const rounded = Math.round(value);
  const sign = rounded < 0 ? "-" : "+";
  return `${sign}${INTEGER_FORMAT.format(Math.abs(rounded))}g`;
}

export function formatCount(value: number | null | undefined, noun: string, unavailableReason = `${noun} unavailable`): string {
  return value == null ? formatUnavailable(unavailableReason) : `${INTEGER_FORMAT.format(Math.max(0, Math.round(value)))} ${noun}`;
}

export function formatItemQuantity(value: number | null | undefined, unavailableReason = "item quantity unavailable"): string {
  return value == null ? formatUnavailable(unavailableReason) : `×${INTEGER_FORMAT.format(Math.max(0, Math.round(value)))}`;
}

export function formatClock(totalSeconds: number | null | undefined, unavailableReason = "clock unavailable"): string {
  if (totalSeconds == null) return formatUnavailable(unavailableReason);
  const seconds = Number.isFinite(totalSeconds) ? Math.max(0, Math.floor(totalSeconds)) : 0;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = String(seconds % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${remainder}` : `${minutes}:${remainder}`;
}

export function formatDuration(totalSeconds: number | null | undefined, unavailableReason = "duration unavailable"): string {
  return totalSeconds == null ? formatUnavailable(unavailableReason) : formatClock(totalSeconds);
}

export function formatInitials(value: string | null | undefined, unavailableReason = "initials unavailable"): string {
  if (value == null) return formatUnavailable(unavailableReason);
  const letters = value.replace(/[^\p{L}\p{N}]/gu, "");
  return letters ? letters.slice(0, 2).toUpperCase() : formatUnavailable(unavailableReason);
}
