// Scrollable preview of the first rows of the cleaned dataset.

import type { Preview } from "../types";

export default function PreviewTable({ preview }: { preview: Preview }) {
  return (
    <div className="overflow-hidden rounded-md border border-line">
      <div className="max-h-80 overflow-auto">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="sticky top-0 bg-paper">
            <tr>
              {preview.columns.map((c) => (
                <th
                  key={c}
                  className="kicker whitespace-nowrap border-b border-line px-3 py-2.5"
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.rows.map((row, i) => (
              <tr key={i} className="border-b border-line/60 last:border-0 hover:bg-ink/[0.02]">
                {preview.columns.map((c) => (
                  <td key={c} className="whitespace-nowrap px-3 py-2 tabular-nums text-ink-soft">
                    {row[c] === null || row[c] === undefined ? (
                      <span className="text-ink-faint">—</span>
                    ) : (
                      String(row[c])
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
