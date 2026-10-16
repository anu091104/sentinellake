import React from "react";
import { Activity, ServerCrash, Gauge, ShieldCheck, ShieldAlert, ArrowDownRight, ArrowUpRight } from "lucide-react";
import { Area, AreaChart, Line, LineChart, ResponsiveContainer, YAxis } from "recharts";
import { bucket, compact, pct, smooth, RANGES } from "../lib.js";

function Kpi({ icon: Icon, label, children, className = "" }) {
  return (
    <div className={`card flex flex-col justify-between gap-3 !p-5 ${className}`}>
      <div className="flex items-center gap-2 text-[13px] font-medium muted">
        <Icon size={15} aria-hidden /> {label}
      </div>
      {children}
    </div>
  );
}

function Delta({ now, before, format, lowerIsBetter = true }) {
  if (now == null || before == null) return null;
  const d = now - before;
  const good = lowerIsBetter ? d <= 0 : d >= 0;
  const Arrow = d <= 0 ? ArrowDownRight : ArrowUpRight;
  return (
    <span className={`pill ${good ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>
      <Arrow size={12} strokeWidth={2.5} />
      {d >= 0 ? "+" : "−"}
      {format(Math.abs(d))}
    </span>
  );
}

export default function KpiCards({ fleet, overview, incidents, minutes }) {
  const range = RANGES.find((r) => r.minutes === minutes)?.label ?? `${minutes} min`;
  const cur = fleet?.current;
  const prev = fleet?.previous;
  const series = fleet?.series ?? [];
  const perMin = cur ? cur.requests / Math.max(1, series.filter((p) => p.requests).length) : null;
  const bars = bucket(series, 16);
  const maxBar = Math.max(1, ...bars.map((b) => b.value));
  const errLine = series.map((p) => ({ t: p.t, v: p.requests ? p.error_rate * 100 : null }));
  const open = overview?.totals?.open_incidents ?? 0;
  const inRange = overview?.totals?.incidents_in_range ?? 0;
  const wave = smooth(series.map((p) => p.error_rate), 6).map((v, i) => ({ i, v }));

  return (
    <div id="overview" className="grid grid-cols-1 gap-5 scroll-mt-6 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi icon={Activity} label="Ingestion throughput">
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="whitespace-nowrap text-[28px] font-bold leading-none tracking-tight text-zinc-900">
              {compact(perMin)} <span className="text-base font-semibold muted">req/min</span>
            </div>
            <div className="mt-2 text-xs muted">{compact(cur?.requests)} requests in the last {range}</div>
          </div>
          <div className="flex h-12 items-end gap-[3px]" aria-hidden>
            {bars.map((b, i) => (
              <span
                key={b.t}
                className={`w-[5px] rounded-full ${i === bars.length - 1 ? "bg-slate-ink" : "bg-sage-500"}`}
                style={{ height: `${Math.max(12, (b.value / maxBar) * 100)}%`, opacity: i === bars.length - 1 ? 1 : 0.35 + (0.5 * i) / bars.length }}
              />
            ))}
          </div>
        </div>
      </Kpi>

      <Kpi icon={ServerCrash} label="Server errors (5xx)">
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="text-[28px] font-bold leading-none tracking-tight text-zinc-900">{pct(cur?.error_rate)}</div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs muted">
              <Delta now={cur?.error_rate} before={prev?.error_rate} format={(v) => pct(v)} />
              {prev ? "vs previous period" : `SLO allows ${pct(1 - 0.99, 0)}`}
            </div>
          </div>
          <div className="h-12 w-28" aria-hidden>
            <ResponsiveContainer>
              <LineChart data={errLine} margin={{ top: 4, bottom: 4, left: 0, right: 0 }}>
                <YAxis hide domain={[0, "dataMax"]} />
                <Line type="monotone" dataKey="v" stroke="#5C7862" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </Kpi>

      <Kpi icon={Gauge} label="p95 latency (request-weighted)">
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="text-[28px] font-bold leading-none tracking-tight text-zinc-900">
              {cur?.p95_ms == null ? "–" : Math.round(cur.p95_ms)} <span className="text-base font-semibold muted">ms</span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs muted">
              <Delta now={cur?.p95_ms} before={prev?.p95_ms} format={(v) => `${Math.round(v)} ms`} />
              {prev ? "vs previous period" : "SLO target < 800 ms"}
            </div>
          </div>
          <span className="grid h-12 w-12 place-items-center rounded-2xl bg-canvas text-sage-700" aria-hidden>
            <Gauge size={22} />
          </span>
        </div>
      </Kpi>

      <div className="relative flex flex-col justify-between gap-3 overflow-hidden rounded-bento bg-sage-500 p-5 text-white shadow-card fade-in">
        <div className="flex items-center gap-2 text-[13px] font-medium text-sage-100">
          {open ? <ShieldAlert size={15} /> : <ShieldCheck size={15} />} Incident status
        </div>
        <div className="relative z-10">
          <div className="text-[28px] font-bold leading-none tracking-tight">
            {open} <span className="text-base font-semibold text-sage-100">open {open === 1 ? "incident" : "incidents"}</span>
          </div>
          <div className="mt-2 text-xs text-sage-100">
            {inRange} detected in the last {range}
          </div>
        </div>
        <div className="glow pointer-events-none absolute right-0 top-3 h-14 w-[46%] opacity-90" aria-hidden>
          <ResponsiveContainer>
            <AreaChart data={wave} margin={{ top: 0, bottom: 0, left: 0, right: 0 }}>
              <defs>
                <linearGradient id="waveFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#B9E3C2" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#B9E3C2" stopOpacity={0} />
                </linearGradient>
              </defs>
              <YAxis hide domain={[0, "dataMax"]} />
              <Area type="monotone" dataKey="v" stroke="#C8F0D0" strokeWidth={2.2} fill="url(#waveFill)" isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
