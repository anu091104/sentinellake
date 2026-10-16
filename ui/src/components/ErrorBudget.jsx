import React from "react";
import { Target } from "lucide-react";
import { Card, CardHeader } from "./ui.jsx";
import { compact, int, SLO } from "../lib.js";

function SemiGauge({ value }) {
  // value: fraction of budget used (can exceed 1)
  const v = Math.max(0, Math.min(1, value));
  const r = 80, cx = 100, cy = 96;
  const arc = (f) => {
    const a = Math.PI * (1 - f);
    return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
  };
  const [x, y] = arc(v);
  const color = value >= 1 ? "#DC2626" : value >= 0.5 ? "#D97706" : "#5C7862";
  return (
    <svg viewBox="0 0 200 110" className="w-full max-w-[260px]" role="img" aria-label={`${Math.round(value * 100)}% of error budget used`}>
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke="#EEF2EE" strokeWidth="18" strokeLinecap="round" />
      {v > 0 && <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${x} ${y}`} fill="none" stroke={color} strokeWidth="18" strokeLinecap="round" />}
      <text x={cx} y={cy - 18} textAnchor="middle" className="fill-zinc-900" style={{ font: "700 30px 'Plus Jakarta Sans Variable', sans-serif" }}>
        {Math.round(value * 100)}%
      </text>
      <text x={cx} y={cy + 2} textAnchor="middle" className="fill-zinc-500" style={{ font: "500 11px 'Plus Jakarta Sans Variable', sans-serif" }}>
        of error budget used
      </text>
    </svg>
  );
}

export default function ErrorBudget({ fleet, services }) {
  const cur = fleet?.current;
  const allowed = cur ? cur.requests * (1 - SLO.availability) : 0;
  const used = allowed ? cur.errors / allowed : 0;
  const total = services.reduce((s, x) => s + x.requests, 0) || 1;
  const share = [...services].sort((a, b) => b.requests - a.requests);
  const max = share[0]?.requests || 1;
  return (
    <Card>
      <CardHeader icon={Target} title="SLO error budget" subtitle="99% availability target: 1% of requests may fail" />
      <div className="flex justify-center">
        <SemiGauge value={used} />
      </div>
      <p className="mt-1 text-center text-xs muted">
        {int(cur?.errors)} failed of {int(allowed)} allowed
      </p>
      <div className="mt-5 text-xs font-semibold muted">Traffic by service</div>
      <ul className="mt-2 space-y-2">
        {share.map((s) => (
          <li key={s.service} className="grid grid-cols-[76px_minmax(0,1fr)_44px] items-center gap-2 text-xs">
            <span className="truncate font-semibold text-zinc-700">{s.service}</span>
            <span className="h-2 rounded-full bg-zinc-100">
              <span className="block h-2 rounded-full bg-sage-500" style={{ width: `${(s.requests / max) * 100}%` }} />
            </span>
            <span className="text-right tabular-nums muted" title={`${int(s.requests)} requests`}>
              {Math.round((s.requests / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[11px] muted">{compact(total)} requests in range</p>
    </Card>
  );
}
