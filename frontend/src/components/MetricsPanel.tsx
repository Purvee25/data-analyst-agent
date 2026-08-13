// Observability panel (USP #3): turns the structured request log into live
// agent-quality metrics — requests logged, success rate, avg latency, and a
// confidence trend sparkline. Reads GET /api/metrics, which aggregates the same
// logs/requests.csv the pipeline appends to. Refetches whenever `refreshKey`
// changes so it updates right after an insight run completes.

import { useEffect, useState } from "react";
import { getMetrics } from "../api";
import type { Metrics } from "../types";

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const w = 220;
  const h = 44;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / span) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-1 h-11 w-full" preserveAspectRatio="none">
      <polyline
        points={pts}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-accent"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line px-4 py-3">
      <p className="kicker">{label}</p>
      <p className="mt-1 font-serif text-2xl font-medium tabular-nums text-ink">{value}</p>
    </div>
  );
}

export default function MetricsPanel({ refreshKey }: { refreshKey: number }) {
  const [m, setM] = useState<Metrics | null>(null);

  useEffect(() => {
    getMetrics()
      .then(setM)
      .catch(() => setM(null));
  }, [refreshKey]);

  if (!m || m.total === 0) {
    return (
      <p className="text-sm text-ink-soft">
        No requests logged yet — generate insights or ask a question and this panel populates from the
        structured request log.
      </p>
    );
  }

  return (
    <div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Requests logged" value={m.total.toLocaleString()} />
        <Stat label="Success rate" value={m.success_rate != null ? `${m.success_rate}%` : "—"} />
        <Stat label="Avg latency" value={m.avg_latency != null ? `${m.avg_latency}s` : "—"} />
        <Stat label="Avg confidence" value={m.avg_confidence != null ? m.avg_confidence.toFixed(2) : "—"} />
      </div>
      {m.confidence_series.length >= 2 && (
        <div className="mt-4 rounded-md border border-line px-4 py-3">
          <p className="kicker">Confidence trend — recent insights</p>
          <Sparkline values={m.confidence_series} />
        </div>
      )}
    </div>
  );
}
