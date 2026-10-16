import React from "react";
import { Search, Bell, RefreshCw, CircleCheck, CircleAlert } from "lucide-react";
import { LogoMark, Segmented } from "./ui.jsx";
import { RANGES, hhmm } from "../lib.js";

export default function Header({ query, setQuery, minutes, setMinutes, health, openCount, onRefresh, loading }) {
  const live = health?.backend && health.backend !== "local";
  const demo = health?.mode === "demo";
  const ok = health?.status === "ok";
  return (
    <header className="flex flex-col gap-4 2xl:flex-row 2xl:items-center 2xl:justify-between">
      <div className="flex items-center gap-4">
        <LogoMark size={48} />
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-900">Sentinel Lake Dashboard</h1>
          <p className="text-sm muted" title={health?.latest_window ? `Newest window: ${health.latest_window}` : undefined}>
            Real-time API observability & system health
            {health?.latest_window && <> · data up to <b className="font-semibold text-zinc-700">{hhmm(health.latest_window)} UTC</b></>}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="relative flex-1 min-w-[220px] lg:w-[280px] lg:flex-none">
          <span className="sr-only">Search</span>
          <Search size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search service, endpoint or incident…"
            className="w-full rounded-full bg-white py-2.5 pl-11 pr-5 text-sm shadow-card placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-sage-300"
          />
        </label>

        <span
          className={`pill py-2 px-3.5 text-[12.5px] shadow-card ${ok ? "bg-white text-sage-700" : "bg-red-50 text-red-600"}`}
          title={live ? "Reading Cassandra (metrics) and MongoDB (incidents)" : demo ? "Hosted demo: serving the output of a 6-hour replay through the Spark pipeline" : "Laptop mode: local files stand in for Kafka, Cassandra and MongoDB"}
        >
          {ok ? <CircleCheck size={14} /> : <CircleAlert size={14} />}
          {live ? "Cassandra + MongoDB · live" : demo ? "Demo · replayed 6-hour dataset" : "Spark pipeline · laptop mode"}
        </span>

        <Segmented
          label="Time range"
          value={minutes}
          onChange={setMinutes}
          options={RANGES.map((r) => ({ value: r.minutes, label: r.label }))}
        />

        <button
          type="button"
          onClick={onRefresh}
          aria-label="Refresh"
          title="Refresh (auto every 30 s)"
          className="grid h-10 w-10 place-items-center rounded-full bg-white text-zinc-600 shadow-card hover:text-zinc-900"
        >
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
        </button>
        <button
          type="button"
          onClick={() => document.getElementById("incidents")?.scrollIntoView({ behavior: "smooth" })}
          aria-label={`${openCount} open incidents`}
          title="Incidents"
          className="relative grid h-10 w-10 place-items-center rounded-full bg-white text-zinc-600 shadow-card hover:text-zinc-900"
        >
          <Bell size={16} />
          {openCount > 0 && (
            <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
              {openCount}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
