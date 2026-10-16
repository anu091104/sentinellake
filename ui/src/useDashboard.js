import { useCallback, useEffect, useRef, useState } from "react";
import { getJSON } from "./lib.js";

const REFRESH_MS = 30_000;

// Loads everything the dashboard shows and refreshes it every 30 s (live mode keeps moving).
export function useDashboard(minutes, service) {
  const [state, setState] = useState({ loading: true, error: null });
  const seq = useRef(0);

  const load = useCallback(async () => {
    const id = ++seq.current;
    try {
      const svcQ = service ? `&service=${encodeURIComponent(service)}` : "";
      const [overview, fleet, scoped, incidents, health, lake, endpoints] = await Promise.all([
        getJSON(`/api/overview?minutes=${minutes}`),
        getJSON(`/api/fleet?minutes=${minutes}`),
        service ? getJSON(`/api/fleet?minutes=${minutes}${svcQ}`) : null,
        getJSON(`/api/incidents?limit=100`),
        getJSON(`/health`),
        getJSON(`/api/lake`).catch(() => null),
        service ? getJSON(`/api/services/${encodeURIComponent(service)}/timeseries?minutes=${minutes}`) : null,
      ]);
      if (id !== seq.current) return; // a newer request won
      setState({ loading: false, error: null, overview, fleet, scoped: scoped || fleet, incidents, health, lake, endpoints, loadedAt: new Date() });
    } catch (e) {
      if (id === seq.current) setState((s) => ({ ...s, loading: false, error: e.message }));
    }
  }, [minutes, service]);

  useEffect(() => {
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [load]);

  return { ...state, reload: load };
}
