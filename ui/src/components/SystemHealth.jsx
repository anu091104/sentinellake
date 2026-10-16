import React, { useState } from "react";
import { HeartPulse, CircleCheck, CircleAlert, Loader2, Stethoscope } from "lucide-react";
import { Card, CardHeader } from "./ui.jsx";
import { getJSON, hhmm } from "../lib.js";

export default function SystemHealth({ health, lake, openCount, onReload }) {
  const [diag, setDiag] = useState(null);
  const [busy, setBusy] = useState(false);
  const local = health?.backend === "local";

  async function run() {
    setBusy(true);
    const t0 = performance.now();
    try {
      const h = await getJSON("/health");
      const ms = Math.round(performance.now() - t0);
      await onReload();
      setDiag({ ok: h.status === "ok", ms, at: new Date().toLocaleTimeString() });
    } catch (e) {
      setDiag({ ok: false, error: e.message, at: new Date().toLocaleTimeString() });
    } finally {
      setBusy(false);
    }
  }

  const checks = [
    { name: "API server", detail: diag?.ms != null ? `answered in ${diag.ms} ms` : "FastAPI · /health", ok: health?.status === "ok" },
    { name: "Stream processing", detail: health?.latest_window ? `last window ${hhmm(health.latest_window)} UTC` : "no windows yet", ok: !!health?.latest_window },
    { name: local ? "Serving store" : "Cassandra + MongoDB", detail: health?.mode === "demo" ? "demo dataset (replay)" : local ? "local files (laptop mode)" : "connected", ok: health?.status === "ok" },
    { name: "Data lake", detail: lake?.available ? `${lake.zones.filter((z) => z.files).length} zones${lake.snapshot ? " (snapshot)" : " with data"}` : "HDFS (cluster mode)", ok: lake ? (lake.available ? lake.zones.some((z) => z.files) : true) : false },
  ];
  const allOk = checks.every((c) => c.ok);

  return (
    <Card>
      <CardHeader icon={HeartPulse} title="System health" subtitle="Pipeline components and their last signal" />
      <div className="flex items-center gap-3 rounded-3xl bg-canvas/60 p-4">
        {allOk ? <CircleCheck size={28} className="text-emerald-600" /> : <CircleAlert size={28} className="text-red-600" />}
        <div>
          <div className="text-sm font-bold text-zinc-900">{allOk ? "All systems operational" : "Attention needed"}</div>
          <div className="text-xs muted">{openCount ? `${openCount} open incident${openCount > 1 ? "s" : ""}` : "No open incidents"}</div>
        </div>
      </div>
      <ul className="mt-4 space-y-2.5">
        {checks.map((c) => (
          <li key={c.name} className="flex items-center gap-2.5 text-sm">
            {c.ok ? <CircleCheck size={16} className="shrink-0 text-emerald-600" /> : <CircleAlert size={16} className="shrink-0 text-red-600" />}
            <span className="font-semibold text-zinc-800">{c.name}</span>
            <span className="ml-auto truncate text-xs muted">{c.detail}</span>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={run}
        disabled={busy}
        className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-full bg-sage-500 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-sage-600 disabled:opacity-70"
      >
        {busy ? <Loader2 size={16} className="animate-spin" /> : <Stethoscope size={16} />} Run diagnostic check
      </button>
      {diag && (
        <p className={`mt-2 text-center text-xs ${diag.ok ? "muted" : "text-red-600"}`}>
          {diag.ok ? `Checked at ${diag.at}: healthy` : `Check failed at ${diag.at}: ${diag.error}`}
        </p>
      )}
    </Card>
  );
}
