// Live "agent working" timeline. Reflects the SSE stages streamed from the
// backend so the two-agent pipeline is visible as it runs, not hidden behind a
// spinner. Each step animates from pending -> active -> complete.

export type Stage = "idle" | "summarizing" | "generating" | "critiquing" | "done" | "error";

const STEPS: { key: Stage; label: string }[] = [
  { key: "summarizing", label: "Summarise dataset" },
  { key: "generating", label: "Insight-finder — call #1" },
  { key: "critiquing", label: "Critic review — call #2" },
  { key: "done", label: "Vetted insights ready" },
];

const ORDER: Stage[] = ["summarizing", "generating", "critiquing", "done"];

function statusOf(step: Stage, current: Stage): "pending" | "active" | "complete" {
  if (current === "error") return step === "summarizing" ? "complete" : "pending";
  const ci = ORDER.indexOf(current);
  const si = ORDER.indexOf(step);
  if (ci < 0) return "pending";
  if (si < ci) return "complete";
  if (si === ci) return current === "done" ? "complete" : "active";
  return "pending";
}

export default function AgentActivity({ stage, note }: { stage: Stage; note?: string }) {
  return (
    <div className="card p-5">
      <div className="mb-4 flex items-center gap-2">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
        </span>
        <p className="kicker">Agents at work</p>
      </div>

      <ol className="space-y-3">
        {STEPS.map((s, i) => {
          const st = statusOf(s.key, stage);
          return (
            <li key={s.key} className="flex items-center gap-3">
              <span
                className={`grid h-7 w-7 place-items-center rounded-full border text-xs font-semibold tabular-nums transition
                  ${st === "complete" ? "border-approve/40 bg-approve/10 text-approve" : ""}
                  ${st === "active" ? "border-accent/50 bg-accent-soft text-accent" : ""}
                  ${st === "pending" ? "border-line bg-ink/[0.02] text-ink-faint" : ""}`}
              >
                {st === "complete" ? "✓" : st === "active" ? <Spinner /> : String(i + 1)}
              </span>
              <span
                className={`text-sm ${
                  st === "pending" ? "text-ink-faint" : st === "active" ? "font-medium text-ink" : "text-ink-soft"
                }`}
              >
                {s.label}
              </span>
            </li>
          );
        })}
      </ol>

      {note && <p className="mt-4 text-xs text-ink-soft">{note}</p>}
    </div>
  );
}

function Spinner() {
  return <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />;
}
