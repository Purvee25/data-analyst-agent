// KPI stat tiles + a breakdown of what the cleaning step fixed vs. flagged.
// Reads the structured DataQualityReport so "fixed" (green) and "flagged"
// (amber, needs a human's eye) stay visually distinct — the same distinction
// the Python report makes.

import type { QualityReport } from "../types";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card card-lift relative overflow-hidden p-5">
      <span className="absolute inset-x-0 top-0 h-[3px] bg-accent/70" />
      <p className="kicker">{label}</p>
      <p className="mt-2 font-serif text-[2.5rem] font-medium leading-none tabular-nums text-ink">{value}</p>
      {hint && <p className="mt-1.5 text-xs text-ink-faint">{hint}</p>}
    </div>
  );
}

// A quiet one-line summary ("8 fixes applied") that expands to the full chip
// list on demand — keeps the dense detail available without paying for it up
// front. Uses a native <details> disclosure (accessible, no extra state).
function Disclosure({ label, items, tone }: { label: string; items: string[]; tone: "fix" | "flag" }) {
  if (items.length === 0) return null;
  const cls =
    tone === "fix"
      ? "border-approve/25 bg-approve/[0.06] text-approve"
      : "border-downgrade/30 bg-downgrade/[0.07] text-downgrade";
  const dot = tone === "fix" ? "bg-approve" : "bg-downgrade";
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-sm text-ink-soft">
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
        <span className="font-semibold text-ink">{items.length}</span> {label}
        <span className="text-ink-faint transition-transform group-open:rotate-90">›</span>
      </summary>
      <div className="mt-3 flex flex-wrap gap-2">
        {items.map((it) => (
          <span key={it} className={`rounded border px-2.5 py-1 text-xs ${cls}`}>
            {it}
          </span>
        ))}
      </div>
    </details>
  );
}

export default function DataQuality({ report }: { report: QualityReport }) {
  const anomalyCount = report.anomalies.length;
  const flaggedCols = Object.keys(report.missing_values_flagged).length;

  const fixes: string[] = [];
  report.date_columns_parsed.forEach((c) => fixes.push(`Parsed date: ${c}`));
  report.numeric_columns_coerced.forEach((c) => fixes.push(`Numeric: ${c}`));
  report.categorical_columns_normalized.forEach((c) => fixes.push(`Normalized: ${c}`));
  Object.entries(report.missing_values_filled).forEach(([c, n]) => fixes.push(`Filled ${c} (${n})`));

  const flags: string[] = [];
  Object.entries(report.missing_values_flagged).forEach(([c, n]) => flags.push(`Missing in ${c} (${n})`));
  Object.entries(report.unparseable_dates).forEach(([c, n]) => flags.push(`Bad dates in ${c} (${n})`));
  report.anomalies.forEach((a) => flags.push(a));

  return (
    <section className="space-y-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Rows" value={report.final_shape[0].toLocaleString()} hint={`from ${report.original_shape[0].toLocaleString()}`} />
        <Stat label="Columns" value={String(report.final_shape[1])} />
        <Stat label="Duplicates removed" value={String(report.duplicate_rows_removed)} />
        <Stat
          label="Anomalies flagged"
          value={String(anomalyCount + flaggedCols)}
          hint={anomalyCount + flaggedCols === 0 ? "clean" : "needs review"}
        />
      </div>

      <div className="card flex flex-wrap items-center gap-x-6 gap-y-3 px-6 py-4">
        <span className="kicker">Cleaning · {report.encoding_used}</span>
        <Disclosure label="fixes applied" items={fixes} tone="fix" />
        <Disclosure label="flagged for review" items={flags} tone="flag" />
        {fixes.length === 0 && flags.length === 0 && (
          <p className="text-sm text-ink-soft">No significant data-quality issues detected.</p>
        )}
      </div>
    </section>
  );
}
