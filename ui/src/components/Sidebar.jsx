import React from "react";
import { LayoutGrid, Radio, BarChart3, Database, Siren, FileCode2 } from "lucide-react";

export const NAV = [
  { id: "overview", label: "Overview", icon: LayoutGrid },
  { id: "streams", label: "Live traffic (Kafka → Spark)", icon: Radio },
  { id: "services", label: "Service health", icon: BarChart3 },
  { id: "lakehouse", label: "Lakehouse (HDFS / Hive)", icon: Database },
  { id: "incidents", label: "Incidents (MongoDB)", icon: Siren },
];

function go(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export default function Sidebar({ active, healthy }) {
  return (
    <nav
      aria-label="Sections"
      className="fixed left-5 top-1/2 z-20 hidden -translate-y-1/2 flex-col items-center gap-2 rounded-full bg-white px-3 py-6 shadow-card lg:flex"
    >
      {NAV.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          type="button"
          title={label}
          aria-label={label}
          aria-current={active === id ? "true" : undefined}
          onClick={() => go(id)}
          className={`grid h-11 w-11 place-items-center rounded-full transition-colors ${
            active === id ? "bg-zinc-900 text-white" : "text-zinc-500 hover:bg-canvas hover:text-zinc-900"
          }`}
        >
          <Icon size={19} strokeWidth={1.9} />
        </button>
      ))}
      <a
        href="/docs"
        target="_blank"
        rel="noreferrer"
        title="API reference (OpenAPI)"
        aria-label="API reference"
        className="grid h-11 w-11 place-items-center rounded-full text-zinc-500 hover:bg-canvas hover:text-zinc-900"
      >
        <FileCode2 size={19} strokeWidth={1.9} />
      </a>

      <div className="mt-10 flex flex-col items-center gap-4">
        <span
          title={healthy ? "Pipeline healthy" : "Attention needed"}
          className="relative grid h-11 w-11 place-items-center rounded-full bg-canvas"
        >
          <span className={`h-2.5 w-2.5 rounded-full ${healthy ? "bg-emerald-500" : "bg-red-500"}`} />
          <span className={`absolute h-2.5 w-2.5 animate-ping rounded-full opacity-60 ${healthy ? "bg-emerald-400" : "bg-red-400"}`} />
        </span>
        <span
          title="Anushka Srivastava"
          className="grid h-11 w-11 place-items-center rounded-full bg-slate-ink text-[13px] font-bold text-white"
        >
          AS
        </span>
      </div>
    </nav>
  );
}
