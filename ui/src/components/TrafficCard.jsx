import React, { useMemo, useState } from "react";
import { Radio, ChevronDown } from "lucide-react";
import {
  Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Card, CardHeader, ChartTooltip, Pill, Segmented } from "./ui.jsx";
import { compact, int, pct, SLO, toMs } from "../lib.js";

// validated categorical pair (CVD-safe, see docs) for the 1-2 endpoints of a service
const SERIES = ["#2A78D6", "#EB6834"];
const SAGE = "#5C7862";
const tickTime = (v) => new Date(v).toISOString().slice(11, 16);
const axis = { stroke: "#A1A1AA", fontSize: 11, tickLine: false, axisLine: false };

export default function TrafficCard({ services, service, setService, scoped, endpoints, incidents }) {
  const [metric, setMetric] = useState("p95");
  const series = scoped?.series ?? [];
  const cur = scoped?.current;

  const volume = useMemo(() => series.map((p) => ({ x: toMs(p.t), requests: p.requests || null })), [series]);

  // second chart: per endpoint when a service is picked, the whole fleet otherwise
  const { rows, lines } = useMemo(() => {
    const eps = service && endpoints?.endpoints ? Object.keys(endpoints.endpoints).sort() : [];
    if (eps.length) {
      const byX = new Map();
      eps.forEach((ep, i) =>
        endpoints.endpoints[ep].forEach((p) => {
          const x = toMs(p.t);
          const row = byX.get(x) || { x };
          row[`e${i}`] = metric === "p95" ? p.p95_ms : p.error_rate * 100;
          byX.set(x, row);
        }),
      );
      return { rows: [...byX.values()].sort((a, b) => a.x - b.x), lines: eps.map((ep, i) => ({ key: `e${i}`, name: ep, color: SERIES[i % 2] })) };
    }
    return {
      rows: series.map((p) => ({ x: toMs(p.t), all: !p.requests ? null : metric === "p95" ? p.p95_ms : p.error_rate * 100 })),
      lines: [{ key: "all", name: service || "All services", color: SAGE }],
    };
  }, [series, endpoints, service, metric]);

  const first = volume[0]?.x;
  const last = volume[volume.length - 1]?.x;
  const shaded = (incidents || [])
    .filter((i) => !service || i.service === service)
    .map((i) => ({ id: i.id, x1: Math.max(first, toMs(i.opened_at)), x2: Math.min(last, toMs(i.last_seen) + 60_000) }))
    .filter((r) => first != null && r.x1 < r.x2);

  const fmt = metric === "p95" ? (v) => `${Math.round(v)} ms` : (v) => `${v.toFixed(2)}%`;

  return (
    <Card id="streams">
      <CardHeader
        icon={Radio}
        title="Live traffic & latency"
        subtitle="1-minute event-time windows from Spark Structured Streaming"
        right={
          <label className="relative inline-flex items-center">
            <span className="sr-only">Service</span>
            <select
              value={service || ""}
              onChange={(e) => setService(e.target.value || null)}
              className="appearance-none rounded-full bg-canvas py-2 pl-4 pr-9 text-[13px] font-semibold text-zinc-800 focus:outline-none focus:ring-2 focus:ring-sage-300"
            >
              <option value="">All services</option>
              {services.map((s) => (
                <option key={s.service} value={s.service}>{s.service}</option>
              ))}
            </select>
            <ChevronDown size={15} className="pointer-events-none absolute right-3 text-zinc-500" />
          </label>
        }
      />

      <div className="mb-4 flex flex-wrap gap-x-8 gap-y-2">
        <Metric label="Requests" value={int(cur?.requests)} />
        <Metric label="p95 latency" value={cur?.p95_ms == null ? "–" : `${Math.round(cur.p95_ms)} ms`} />
        <Metric label="5xx errors" value={pct(cur?.error_rate)} tone={cur?.error_rate > 1 - SLO.availability ? "text-red-600" : ""} />
        <div className="flex items-center">
          <Pill tone="sage"><span className="h-1.5 w-1.5 rounded-full bg-sage-500" /> Spark streaming</Pill>
        </div>
      </div>

      <div className="text-xs font-semibold muted mb-1">Requests per minute</div>
      <div className="h-32">
        <ResponsiveContainer>
          <AreaChart data={volume} syncId="traffic" margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
            <defs>
              <linearGradient id="vol" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={SAGE} stopOpacity={0.28} />
                <stop offset="100%" stopColor={SAGE} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="#F1F1EF" />
            {shaded.map((r) => <ReferenceArea key={r.id} x1={r.x1} x2={r.x2} fill="#F5C26B" fillOpacity={0.18} ifOverflow="hidden" />)}
            <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} hide />
            <YAxis {...axis} tickFormatter={compact} width={48} />
            <Tooltip content={<ChartTooltip format={(v) => int(v)} labelFormat={tickTime} />} />
            <Area type="monotone" connectNulls={false} dataKey="requests" name="Requests" stroke={SAGE} strokeWidth={2} fill="url(#vol)" isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 mb-1 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          {lines.map((l) => (
            <span key={l.key} className="inline-flex items-center gap-1.5 font-semibold text-zinc-600">
              <span className="h-[3px] w-4 rounded-full" style={{ background: l.color }} /> {l.name}
            </span>
          ))}
          {shaded.length > 0 && (
            <span className="inline-flex items-center gap-1.5 text-zinc-500">
              <span className="h-3 w-4 rounded-sm bg-amber-200/70" /> incident window
            </span>
          )}
        </div>
        <Segmented
          label="Metric"
          value={metric}
          onChange={setMetric}
          options={[{ value: "p95", label: "p95 latency" }, { value: "err", label: "5xx rate" }]}
        />
      </div>
      <div className="h-48">
        <ResponsiveContainer>
          <LineChart data={rows} syncId="traffic" margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid vertical={false} stroke="#F1F1EF" />
            {shaded.map((r) => <ReferenceArea key={r.id} x1={r.x1} x2={r.x2} fill="#F5C26B" fillOpacity={0.18} ifOverflow="hidden" />)}
            {metric === "p95" && <ReferenceLine y={SLO.p95} stroke="#EF4444" strokeDasharray="4 4" strokeOpacity={0.6} label={{ value: "SLO 800 ms", position: "insideTopRight", fill: "#EF4444", fontSize: 10 }} ifOverflow="extendDomain" />}
            <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} {...axis} tickFormatter={tickTime} minTickGap={40} />
            <YAxis {...axis} width={48} tickFormatter={metric === "p95" ? (v) => `${v}` : (v) => `${v}%`} />
            <Tooltip content={<ChartTooltip format={fmt} labelFormat={tickTime} />} />
            {lines.map((l) => (
              <Line key={l.key} type="monotone" dataKey={l.key} name={l.name} stroke={l.color} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

function Metric({ label, value, tone = "" }) {
  return (
    <div>
      <div className="text-xs muted">{label}</div>
      <div className={`text-lg font-bold tracking-tight text-zinc-900 ${tone}`}>{value}</div>
    </div>
  );
}
