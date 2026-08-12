// Simple collapsible section used for the data-quality report and preview,
// so the dashboard defaults to a clean view and details expand on demand.

import { useState, type ReactNode } from "react";

export default function Section({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-5 py-4 text-left text-sm font-semibold text-ink transition hover:bg-ink/[0.02]"
      >
        <span>{title}</span>
        <span className={`text-ink-faint transition-transform ${open ? "rotate-90" : ""}`}>›</span>
      </button>
      {open && <div className="border-t border-line p-5">{children}</div>}
    </div>
  );
}
