// Renders a backend-computed chart (bar or line) with Recharts.
// The backend already did the aggregation and top-N capping; this only draws.

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartData } from "../types";

const AXIS = "#94a3b8";
const GRID = "rgba(148,163,184,0.12)";
const ACCENT = "#818cf8";

function compact(n: number): string {
  return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export default function Chart({ data }: { data: ChartData }) {
  const rows = data.points.map((p) => ({ name: p.label, value: p.value ?? 0 }));

  return (
    <div className="mt-3 rounded-xl bg-black/20 p-4">
      <p className="mb-3 text-sm font-medium text-slate-200">{data.title}</p>
      <ResponsiveContainer width="100%" height={260}>
        {data.kind === "line" ? (
          <LineChart data={rows} margin={{ top: 4, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="name" tick={{ fill: AXIS, fontSize: 11 }} tickMargin={8} />
            <YAxis tick={{ fill: AXIS, fontSize: 11 }} tickFormatter={compact} width={48} />
            <Tooltip
              contentStyle={{
                background: "#0f172a",
                border: "1px solid rgba(148,163,184,0.2)",
                borderRadius: 12,
                color: "#e2e8f0",
              }}
            />
            <Line type="monotone" dataKey="value" stroke={ACCENT} strokeWidth={2.5} dot={{ r: 2 }} />
          </LineChart>
        ) : (
          <BarChart data={rows} margin={{ top: 4, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fill: AXIS, fontSize: 11 }}
              tickMargin={8}
              interval={0}
              angle={rows.length > 5 ? -30 : 0}
              textAnchor={rows.length > 5 ? "end" : "middle"}
              height={rows.length > 5 ? 60 : 30}
            />
            <YAxis tick={{ fill: AXIS, fontSize: 11 }} tickFormatter={compact} width={48} />
            <Tooltip
              cursor={{ fill: "rgba(129,140,248,0.08)" }}
              contentStyle={{
                background: "#0f172a",
                border: "1px solid rgba(148,163,184,0.2)",
                borderRadius: 12,
                color: "#e2e8f0",
              }}
            />
            <Bar dataKey="value" fill={ACCENT} radius={[6, 6, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
