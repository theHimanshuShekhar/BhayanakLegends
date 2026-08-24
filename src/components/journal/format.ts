export function signed(n: number | null | undefined): string {
  if (n == null) return "—";
  const abs = Math.abs(n).toLocaleString("en-US");
  return n < 0 ? `-${abs}` : `+${abs}`;
}

export function fmtDuration(total_s: number | null | undefined): string {
  if (total_s == null) return "—";
  const m = Math.floor(total_s / 60);
  const s = Math.floor(total_s % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function patchOrder(patch: string): number {
  const [major = 0, minor = 0] = patch.split(".").map((x) => Number(x));
  return major * 1000 + minor;
}

export function fmtClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
