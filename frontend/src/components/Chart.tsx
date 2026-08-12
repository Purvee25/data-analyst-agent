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

const AXIS = "#8a857a";
const GRID = "rgba(28,27,24,0.08)";
const ACCENT = "#9a3412";
const TOOLTIP_STYLE = {
  background: "#ffffff",
  border: "1px solid #e6e2d8",
  borderRadius: 8,
  color: "#1c1b18",
} as const;

function compact(n: number): string {
  return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export default function Chart({ data }: { data: ChartData }) {
  const rows = data.points.map((p) => ({ name: p.label, value: p.value ?? 0 }));

  return (
    <div className="mt-3 rounded-md border border-line bg-paper p-4">
      <p className="kicker mb-3">{data.title}</p>
      <ResponsiveContainer width="100%" height={260}>
        {data.kind === "line" ? (
          <LineChart data={rows} margin={{ top: 4, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="name" tick={{ fill: AXIS, fontSize: 11 }} tickMargin={8} />
            <YAxis tick={{ fill: AXIS, fontSize: 11 }} tickFormatter={compact} width={48} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Line type="monotone" dataKey="value" stroke={ACCENT} strokeWidth={2} dot={{ r: 2 }} />
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
            <Tooltip cursor={{ fill: "rgba(154,52,18,0.06)" }} contentStyle={TOOLTIP_STYLE} />
            <Bar dataKey="value" fill={ACCENT} radius={[3, 3, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
