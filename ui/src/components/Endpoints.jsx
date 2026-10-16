import React from "react";
import { Zap } from "lucide-react";
import { Card, CardHeader, Empty, Pill } from "./ui.jsx";
import { compact, latencyTone, pct } from "../lib.js";

const METHOD = { GET: "bg-sky-50 text-sky-700", POST: "bg-violet-50 text-violet-700", PUT: "bg-amber-50 text-amber-700", DELETE: "bg-red-50 text-red-600" };

export default function Endpoints({ endpoints, onSelect }) {
  const rows = (endpoints || []).slice(0, 8);
  return (
    <Card>
      <CardHeader icon={Zap} title="Slowest endpoints" subtitle="Ranked by p95 latency in the selected range" right={<Pill tone="neutral">SLO &lt; 800 ms</Pill>} />
      {rows.length === 0 && <Empty>No endpoints match your search.</Empty>}
      <ul className="divide-y divide-zinc-100">
        {rows.map((e) => {
          const [method, path] = e.endpoint.split(" ");
          return (
            <li key={`${e.service} ${e.endpoint}`}>
              <button type="button" onClick={() => onSelect(e.service)} className="flex w-full items-center gap-3 py-2.5 text-left hover:bg-zinc-50/70">
                <span className={`w-12 shrink-0 rounded-md py-0.5 text-center text-[10px] font-bold ${METHOD[method] || "bg-zinc-100"}`}>{method}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-mono text-[12.5px] text-zinc-900">{path}</span>
                  <span className="block text-[11px] muted">
                    {e.service} · {compact(e.requests)} req · {pct(e.error_rate)} 5xx
                  </span>
                </span>
                <Pill tone={latencyTone(e.p95_ms)} className="w-[70px] justify-center">{Math.round(e.p95_ms)} ms</Pill>
              </button>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
