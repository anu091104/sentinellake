import React, { useState } from "react";
import { Database, Copy, Check, Terminal } from "lucide-react";
import { Card, CardHeader, Pill } from "./ui.jsx";
import { mb } from "../lib.js";

function Layer({ y, fill, side, label, sub, dark }) {
  const cx = 120, w = 78, h = 34, t = 12;
  return (
    <g>
      <path d={`M ${cx - w} ${y} L ${cx} ${y + h} L ${cx + w} ${y} L ${cx + w} ${y + t} L ${cx} ${y + h + t} L ${cx - w} ${y + t} Z`} fill={side} />
      <path d={`M ${cx} ${y - h} L ${cx + w} ${y} L ${cx} ${y + h} L ${cx - w} ${y} Z`} fill={fill} stroke="rgba(255,255,255,.35)" />
      <text x={cx} y={y - 1} textAnchor="middle" style={{ font: "700 12px 'Plus Jakarta Sans Variable', sans-serif", letterSpacing: ".06em" }} fill={dark ? "#fff" : "#1E2923"}>
        {label}
      </text>
      <text x={cx} y={y + 13} textAnchor="middle" style={{ font: "500 9.5px 'Plus Jakarta Sans Variable', sans-serif" }} fill={dark ? "rgba(255,255,255,.75)" : "#52525B"}>
        {sub}
      </text>
    </g>
  );
}

const reduceMotion = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function Stack() {
  return (
    <svg viewBox="0 0 240 250" className="mx-auto w-full max-w-[250px]" role="img" aria-label="Pipeline: Kafka feeds Spark, which writes the HDFS lake and the Cassandra and MongoDB serving stores">
      <path d="M120 78 V 112 M120 156 V 190" stroke="#A9BCAC" strokeWidth="2" strokeDasharray="3 4" />
      {!reduceMotion && (
        <circle r="3.5" fill="#5C7862">
          <animateMotion dur="2.4s" repeatCount="indefinite" path="M120 78 V 112 M120 156 V 190" />
        </circle>
      )}
      <Layer y={196} fill="#EAE8E1" side="#D6D3C8" label="STORAGE" sub="HDFS · Cassandra · MongoDB" />
      <Layer y={128} fill="#5C7862" side="#4F6A55" label="SPARK" sub="windows · detector" dark />
      <Layer y={60} fill="#1E2923" side="#121915" label="KAFKA" sub="topic api-logs" dark />
    </svg>
  );
}

function Cmd({ cmd }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={() => navigator.clipboard?.writeText(cmd).then(() => { setDone(true); setTimeout(() => setDone(false), 1500); })}
      className="inline-flex items-center gap-2 rounded-full bg-slate-ink py-2 pl-3.5 pr-3 font-mono text-xs text-white hover:bg-black"
      title="Copy command"
    >
      <Terminal size={13} /> {cmd} {done ? <Check size={13} className="text-emerald-300" /> : <Copy size={13} className="text-zinc-400" />}
    </button>
  );
}

export default function Lakehouse({ lake }) {
  const z = Object.fromEntries((lake?.zones || []).map((x) => [x.zone, x]));
  const ratio = z.raw?.bytes && z.curated?.bytes ? z.raw.bytes / z.curated.bytes : null;
  return (
    <Card id="lakehouse">
      <CardHeader icon={Database} title="Data lake pipeline" subtitle="Lambda architecture: speed layer above, batch layer on the lake" />
      <div className="grid gap-6 sm:grid-cols-[minmax(0,1fr)_minmax(0,220px)] sm:items-center">
        <div className="min-w-0">
          {lake?.available ? (
            <>
              <div className="text-3xl font-bold tracking-tight text-zinc-900">{mb(z.curated?.bytes)}</div>
              <p className="text-sm muted">
                curated Parquet across {z.curated?.partitions ?? 0} hourly partitions{lake.snapshot && " (from the replay run)"}
                {ratio && <> · <b className="font-semibold text-sage-700">{ratio.toFixed(1)}× smaller</b> than raw JSON</>}
              </p>
              <dl className="mt-4 divide-y divide-zinc-100 rounded-2xl bg-canvas/60 px-4">
                {["raw", "quarantine", "serving"].map((k) => z[k] && (
                  <div key={k} className="flex items-baseline justify-between gap-3 py-2.5">
                    <dt className="min-w-0">
                      <span className="block text-[13px] font-semibold text-zinc-800">{z[k].name}</span>
                      <span className="block truncate text-[11px] muted">{z[k].description}</span>
                    </dt>
                    <dd className="text-sm font-bold tabular-nums text-zinc-900">{mb(z[k].bytes)}</dd>
                  </div>
                ))}
              </dl>
            </>
          ) : (
            <p className="text-sm muted">
              In cluster mode the lake lives in HDFS. Browse it in the NameNode UI on port <b>9870</b>.
            </p>
          )}
          <div className="mt-5 text-xs font-semibold muted">Batch layer: run on the lake</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <Cmd cmd=".\sl mapreduce" />
            <Cmd cmd=".\sl hive" />
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <Pill tone="sage">Hadoop Streaming</Pill>
            <Pill tone="sage">HiveQL · SerDe · UDF</Pill>
          </div>
        </div>
        <Stack />
      </div>
    </Card>
  );
}
