import React, { useState } from "react";
import { Siren, OctagonAlert, TriangleAlert, CircleCheck, Clock3 } from "lucide-react";
import { Card, CardHeader, Empty, Pill, Segmented } from "./ui.jsx";
import { hhmm, INCIDENT_TITLES, toMs } from "../lib.js";

export default function Incidents({ incidents, backend }) {
  const [filter, setFilter] = useState("all");
  const list = (incidents || []).filter((i) => filter === "all" || i.status === "open");
  return (
    <Card id="incidents">
      <CardHeader
        icon={Siren}
        title="Incidents"
        subtitle={backend === "local" ? "Raised by the anomaly detector" : "MongoDB · incidents collection"}
        right={<Segmented label="Filter incidents" value={filter} onChange={setFilter} options={[{ value: "all", label: "All" }, { value: "open", label: "Open" }]} />}
      />
      {list.length === 0 && <Empty>{filter === "open" ? "No open incidents. All clear." : "No incidents match."}</Empty>}
      <ol className="relative space-y-3">
        {list.map((i) => {
          const crit = i.severity === "critical";
          const detectedAfter = i.detected_at ? Math.round((toMs(i.detected_at) - toMs(i.opened_at)) / 60000) : null;
          return (
            <li key={i.id} className="rounded-3xl bg-canvas/60 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Pill tone={crit ? "bad" : "warn"} icon={crit ? OctagonAlert : TriangleAlert}>{i.severity}</Pill>
                  {i.status === "open" ? (
                    <Pill tone="dark"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-400" /> open</Pill>
                  ) : (
                    <Pill tone="good" icon={CircleCheck}>resolved</Pill>
                  )}
                </div>
                <span className="whitespace-nowrap text-xs font-semibold muted">{hhmm(i.opened_at)} UTC</span>
              </div>
              <h3 className="mt-2 text-sm font-bold text-zinc-900">{INCIDENT_TITLES[i.type] || i.type}</h3>
              <p className="mt-0.5 text-[13px] leading-snug text-zinc-600">{i.reason}</p>
              <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                <span className="font-semibold text-zinc-800">{i.service}</span>
                <code className="rounded-md bg-white px-1.5 py-0.5 font-mono text-[11px] text-zinc-600">{i.endpoint}</code>
                <span className="inline-flex items-center gap-1 muted">
                  <Clock3 size={12} /> detected in {detectedAfter ?? "–"} min · lasted {i.duration_min} min
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
