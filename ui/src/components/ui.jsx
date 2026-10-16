import React from "react";

export function Card({ id, className = "", children, dark = false }) {
  return (
    <section id={id} className={`${dark ? "rounded-bento shadow-card p-6 min-w-0 bg-sage-500 text-white" : "card"} fade-in scroll-mt-6 ${className}`}>
      {children}
    </section>
  );
}

export function CardHeader({ icon: Icon, title, subtitle, right }) {
  return (
    <div className="flex items-start justify-between gap-3 mb-4">
      <div className="flex items-start gap-3 min-w-0">
        {Icon && (
          <span className="grid place-items-center h-9 w-9 shrink-0 rounded-full bg-canvas text-sage-700">
            <Icon size={17} strokeWidth={2} aria-hidden />
          </span>
        )}
        <div className="min-w-0">
          <h2 className="card-title leading-tight">{title}</h2>
          {subtitle && <p className="text-[13px] muted mt-0.5 leading-snug">{subtitle}</p>}
        </div>
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  );
}

const TONES = {
  good: "bg-emerald-50 text-emerald-700",
  warn: "bg-amber-50 text-amber-700",
  bad: "bg-red-50 text-red-600",
  neutral: "bg-zinc-100 text-zinc-600",
  sage: "bg-sage-50 text-sage-700",
  dark: "bg-zinc-900 text-white",
};

export function Pill({ tone = "neutral", icon: Icon, children, className = "" }) {
  return (
    <span className={`pill ${TONES[tone]} ${className}`}>
      {Icon && <Icon size={12} strokeWidth={2.5} aria-hidden />}
      {children}
    </span>
  );
}

export function Segmented({ options, value, onChange, label }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-full bg-white p-1 shadow-card">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={`rounded-full px-3.5 py-1.5 text-[13px] font-semibold transition-colors ${
            o.value === value ? "bg-zinc-900 text-white" : "text-zinc-500 hover:text-zinc-900"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// Recharts tooltip in the dashboard's style
export function ChartTooltip({ active, payload, label, format = (v) => v, labelFormat = (l) => l }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-2xl bg-zinc-900/95 px-3.5 py-2.5 text-xs text-white shadow-lg">
      <div className="mb-1 font-semibold text-zinc-300">{labelFormat(label)} UTC</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 py-0.5">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color || p.stroke }} />
          <span className="text-zinc-300">{p.name}</span>
          <span className="ml-auto pl-3 font-semibold tabular-nums">{format(p.value, p.dataKey)}</span>
        </div>
      ))}
    </div>
  );
}

export function LogoMark({ size = 40 }) {
  // three nodes and their links: sources -> stream -> lake
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden>
      <rect width="40" height="40" rx="14" fill="#5C7862" />
      <path d="M20 11 L11.5 26 M20 11 L28.5 26 M11.5 26 H28.5" stroke="#DDE6DE" strokeWidth="2" strokeLinecap="round" />
      <circle cx="20" cy="11" r="4" fill="#fff" />
      <circle cx="11.5" cy="26.5" r="4" fill="#fff" />
      <circle cx="28.5" cy="26.5" r="4" fill="#B9E3C2" />
    </svg>
  );
}

export function Empty({ children }) {
  return <p className="py-6 text-center text-sm muted">{children}</p>;
}
