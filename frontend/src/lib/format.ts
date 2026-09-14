export function humanize(value: string): string {
  return value.toLowerCase().replaceAll("_", " ");
}

export function money(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { style: "currency", currency: "USD" }) : value;
}

export function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function ago(iso: string): string {
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds} second${seconds === 1 ? "" : "s"} ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  return `${hours} hour${hours === 1 ? "" : "s"} ago`;
}

// Event payloads are small objects; show them as "key: value" pairs
// rather than raw JSON.
export function describe(data: Record<string, unknown>): string {
  return Object.entries(data)
    .map(([k, v]) => `${humanize(k)}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
}

// A date-only value ("2026-09-01") has no time zone; `new Date` would read
// it as UTC midnight and show the previous day west of Greenwich.
export function shortDate(value: string | null | undefined): string {
  if (!value) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(value);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function sentence(value: string): string {
  const text = humanize(value);
  return text.charAt(0).toUpperCase() + text.slice(1);
}
