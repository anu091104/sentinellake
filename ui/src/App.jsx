import React, { useEffect, useMemo, useState } from "react";
import { CircleAlert } from "lucide-react";
import Sidebar, { NAV } from "./components/Sidebar.jsx";
import Header from "./components/Header.jsx";
import KpiCards from "./components/KpiCards.jsx";
import TrafficCard from "./components/TrafficCard.jsx";
import ServiceHealth from "./components/ServiceHealth.jsx";
import Incidents from "./components/Incidents.jsx";
import ErrorBudget from "./components/ErrorBudget.jsx";
import Lakehouse from "./components/Lakehouse.jsx";
import Endpoints from "./components/Endpoints.jsx";
import SystemHealth from "./components/SystemHealth.jsx";
import { useDashboard } from "./useDashboard.js";

function useActiveSection() {
  const [active, setActive] = useState("overview");
  useEffect(() => {
    const els = NAV.map((n) => document.getElementById(n.id)).filter(Boolean);
    if (!els.length) return;
    const io = new IntersectionObserver(
      (entries) => {
        const top = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (top) setActive(top.target.id);
      },
      { rootMargin: "-10% 0px -55% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  });
  return active;
}

export default function App() {
  const [minutes, setMinutes] = useState(360);
  const [service, setService] = useState(null);
  const [query, setQuery] = useState("");
  const d = useDashboard(minutes, service);
  const active = useActiveSection();

  const q = query.trim().toLowerCase();
  const match = (...fields) => !q || fields.some((f) => f && String(f).toLowerCase().includes(q));
  const services = useMemo(() => (d.overview?.services || []).filter((s) => match(s.service)), [d.overview, q]);
  const endpoints = useMemo(() => (d.fleet?.endpoints || []).filter((e) => match(e.service, e.endpoint)), [d.fleet, q]);
  const incidents = useMemo(
    () => (d.incidents || []).filter((i) => match(i.service, i.endpoint, i.type, i.reason, i.id)),
    [d.incidents, q],
  );
  const openCount = d.overview?.totals?.open_incidents ?? 0;
  const empty = d.overview && d.overview.as_of == null;

  return (
    <div className="min-h-screen pb-10">
      <Sidebar active={active} healthy={d.health?.status === "ok" && openCount === 0} />
      <main className="mx-auto max-w-[1600px] space-y-5 px-4 pt-6 sm:px-6 lg:pl-[120px] lg:pr-8">
        <Header
          query={query}
          setQuery={setQuery}
          minutes={minutes}
          setMinutes={setMinutes}
          health={d.health}
          openCount={openCount}
          onRefresh={d.reload}
          loading={d.loading}
        />

        {d.error && (
          <div role="alert" className="flex items-center gap-2 rounded-3xl bg-red-50 px-5 py-3 text-sm text-red-700">
            <CircleAlert size={16} /> Could not reach the API ({d.error}). Is <code>.\sl serve</code> running?
          </div>
        )}
        {empty && (
          <div className="card text-sm">
            No metrics yet. Run <code className="font-mono">.\sl replay</code> then <code className="font-mono">.\sl stream</code>, or start the cluster.
          </div>
        )}

        {!d.overview && !d.error ? (
          <Skeleton />
        ) : (
          <>
            <KpiCards fleet={d.fleet} overview={d.overview} incidents={d.incidents} minutes={minutes} />
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
              <div className="flex min-w-0 flex-col gap-5 xl:col-span-5">
                <TrafficCard
                  services={d.overview?.services || []}
                  service={service}
                  setService={setService}
                  scoped={d.scoped}
                  endpoints={d.endpoints}
                  incidents={d.incidents}
                />
                <Lakehouse lake={d.lake} />
              </div>
              <div className="flex min-w-0 flex-col gap-5 xl:col-span-4">
                <ServiceHealth services={services} selected={service} onSelect={setService} />
                <Endpoints endpoints={endpoints} onSelect={setService} />
                <SystemHealth health={d.health} lake={d.lake} openCount={openCount} onReload={d.reload} />
              </div>
              <div className="flex min-w-0 flex-col gap-5 xl:col-span-3">
                <Incidents incidents={incidents} backend={d.health?.backend} />
                <ErrorBudget fleet={d.fleet} services={d.overview?.services || []} />
              </div>
            </div>
          </>
        )}
        <footer className="pt-2 text-center text-xs muted">
          SentinelLake · Kafka → Spark Structured Streaming → HDFS / Cassandra / MongoDB ·{" "}
          <a className="underline hover:text-zinc-900" href="/classic">classic console</a> ·{" "}
          <a className="underline hover:text-zinc-900" href="/docs">API</a>
        </footer>
      </main>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="grid animate-pulse grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4" aria-label="Loading">
      {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-32 rounded-bento bg-white/70" />)}
    </div>
  );
}
