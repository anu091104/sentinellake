// Data access + formatting. Every number on the dashboard comes from the FastAPI endpoints below.

export async function getJSON(path) {
  const r = await fetch(path, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${path} -> HTTP ${r.status}`);
  return r.json();
}

export const RANGES = [
  { minutes: 60, label: "1 hour", short: "1h" },
  { minutes: 180, label: "3 hours", short: "3h" },
  { minutes: 360, label: "6 hours", short: "6h" },
];

const compactFmt = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 });
const intFmt = new Intl.NumberFormat("en-US");

export const compact = (n) => (n == null ? "–" : compactFmt.format(n));
export const int = (n) => (n == null ? "–" : intFmt.format(Math.round(n)));
export const pct = (x, digits = 2) => (x == null ? "–" : `${(x * 100).toFixed(digits)}%`);
export const ms = (x) => (x == null ? "–" : `${Math.round(x)} ms`);
export const mb = (bytes) =>
  bytes == null ? "–" : bytes >= 1e9 ? `${(bytes / 1e9).toFixed(2)} GB` : bytes >= 1e6 ? `${(bytes / 1e6).toFixed(1)} MB` : `${(bytes / 1e3).toFixed(1)} KB`;

// timestamps from the API are UTC; show them as UTC so they match the logs and incident ids
export const hhmm = (iso) => (iso ? iso.slice(11, 16) : "–");
export const toMs = (iso) => Date.parse(iso);

export const INCIDENT_TITLES = {
  ERROR_BURST: "Burst of server errors",
  LATENCY_SPIKE: "Sudden latency spike",
  LATENCY_DRIFT: "Latency slowly degrading",
  TRAFFIC_DROP: "Traffic dropped sharply",
};

// SLO used across the project (Hive Q1, docs): 99% of requests succeed, p95 under 800 ms
export const SLO = { availability: 0.99, p95: 800 };

export function latencyTone(p95) {
  if (p95 == null) return "neutral";
  if (p95 >= SLO.p95) return "bad";
  if (p95 >= 400) return "warn";
  return "good";
}

// bucket a minute series into n bars (sum of requests per bucket)
export function bucket(series, n, key = "requests") {
  if (!series?.length) return [];
  const size = Math.ceil(series.length / n);
  const out = [];
  for (let i = 0; i < series.length; i += size) {
    const chunk = series.slice(i, i + size);
    out.push({ t: chunk[0].t, value: chunk.reduce((s, p) => s + (p[key] || 0), 0) / chunk.length });
  }
  return out;
}

// moving average, for the decorative wave on the incident card
export function smooth(values, w = 5) {
  return values.map((_, i) => {
    const s = values.slice(Math.max(0, i - w), i + w + 1).filter((v) => v != null);
    return s.length ? s.reduce((a, b) => a + b, 0) / s.length : 0;
  });
}
