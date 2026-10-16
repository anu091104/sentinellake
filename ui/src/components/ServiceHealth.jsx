import React from "react";
import { BarChart3, CircleCheck, TriangleAlert, OctagonAlert } from "lucide-react";
import { Card, CardHeader, Empty, Pill } from "./ui.jsx";
import { hhmm, latencyTone, pct } from "../lib.js";

const BEAT = { ok: "bg-[#C9D8CC]", degraded: "bg-amber-400", down: "bg-red-500", nodata: "bg-zinc-200" };
const STATUS = {
  healthy: { icon: CircleCheck, cls: "text-emerald-600", label: "Healthy" },
  degraded: { icon: TriangleAlert, cls: "text-amber-600", label: "Degraded" },
  down: { icon: OctagonAlert, cls: "text-red-600", label: "Critical incident open" },
};

const RANK = { nodata: 0, ok: 1, degraded: 2, down: 3 };
const MAX_CELLS = 60;

// one cell per minute for short ranges; for longer ones each cell covers a few minutes and shows the worst
function cells(beats) {
  const size = Math.max(1, Math.ceil(beats.length / MAX_CELLS));
  const out = [];
  for (let i = 0; i < beats.length; i += size) {
    const chunk = beats.slice(i, i + size);
    const worst = chunk.reduce((a, b) => (RANK[b.state] > RANK[a.state] ? b : a));
    const req = chunk.reduce((s, b) => s + b.requests, 0);
    out.push({ t: chunk[0].t, end: chunk[chunk.length - 1].t, state: worst.state, requests: req, minutes: chunk.length,
               rate: Math.max(...chunk.map((b) => b.error_rate ?? 0)) });
  }
  return out;
}

export default function ServiceHealth({ services, selected, onSelect }) {
  return (
    <Card id="services">
      <CardHeader icon={BarChart3} title="Service health, minute by minute" subtitle={`Each tick is ${services[0] && services[0].heartbeat.length > MAX_CELLS ? `${Math.ceil(services[0].heartbeat.length / MAX_CELLS)} minutes (worst minute shown)` : "one minute"}. Select a service to drill in.`} />
      {services.length === 0 && <Empty>No services match your search.</Empty>}
      <ul className="-mx-3 space-y-0.5">
        {services.map((s) => {
          const st = STATUS[s.status] || STATUS.healthy;
          const Icon = st.icon;
          const isSel = selected === s.service;
          return (
            <li key={s.service}>
              <button
                type="button"
                onClick={() => onSelect(isSel ? null : s.service)}
                aria-pressed={isSel}
                className={`w-full rounded-2xl px-3 py-2.5 text-left transition-colors ${isSel ? "bg-canvas" : "hover:bg-zinc-50"}`}
              >
                <span className="flex items-center gap-2.5">
                  <Icon size={16} className={st.cls} aria-label={st.label} />
                  <span className="truncate text-sm font-semibold text-zinc-900">{s.service}</span>
                  <span className="ml-auto flex items-center gap-2">
                    <Pill tone={s.error_rate >= 0.01 ? "bad" : "good"}>{pct(s.error_rate)}</Pill>
                    <Pill tone={latencyTone(s.p95_ms)} className="w-[68px] justify-center">
                      {s.p95_ms == null ? "–" : `${Math.round(s.p95_ms)} ms`}
                    </Pill>
                  </span>
                </span>
                <span className="mt-2 flex h-5 items-stretch gap-[2px]" aria-hidden>
                  {cells(s.heartbeat).map((b) => (
                    <i
                      key={b.t}
                      title={`${hhmm(b.t)}${b.minutes > 1 ? `–${hhmm(b.end)}` : ""} UTC · ${b.requests} req · worst minute ${pct(b.rate)} 5xx`}
                      className={`min-w-0 flex-1 rounded-[2px] ${BEAT[b.state]}`}
                    />
                  ))}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs muted">
        <Legend cls="bg-[#C9D8CC]" label="Normal" />
        <Legend cls="bg-amber-400" label="Incident active" />
        <Legend cls="bg-red-500" label="5xx above 5%" />
        <Legend cls="bg-zinc-200" label="No data" />
        <span className="ml-auto">pills: 5xx rate · p95</span>
      </div>
    </Card>
  );
}

function Legend({ cls, label }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-2.5 w-2.5 rounded-sm ${cls}`} /> {label}
    </span>
  );
}
