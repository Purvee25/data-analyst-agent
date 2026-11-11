// Renders a Q&A answer as readable text: strips markdown emphasis, and turns
// "- item" / "1. item" lines (or inline "1. … 2. …" runs) into a tidy list so
// long answers don't arrive as one dense paragraph.

const clean = (s: string) => s.replace(/\*\*|__|`/g, "").trim();

export function parseAnswer(text: string): { intro: string[]; items: string[] } {
  let body = clean(text);
  // Break inline numbered runs ("... 1. Foo. 2. Bar") onto their own lines.
  body = body.replace(/\s+(\d{1,2})[.)]\s+(?=[A-Z])/g, "\n$1. ");
  const intro: string[] = [];
  const items: string[] = [];
  for (const raw of body.split(/\n+/)) {
    const line = raw.trim();
    if (!line) continue;
    const m = line.match(/^(?:[-•*]|\d{1,2}[.)])\s+(.*)$/);
    if (m) items.push(m[1]);
    else if (items.length === 0) intro.push(line);
    else items[items.length - 1] += " " + line;
  }
  return { intro, items };
}

export default function FormattedAnswer({ text }: { text: string }) {
  const { intro, items } = parseAnswer(text);
  return (
    <div className="space-y-2">
      {intro.map((p, i) => (
        <p key={i}>{p}</p>
      ))}
      {items.length > 0 && (
        <ul className="space-y-1.5">
          {items.map((it, i) => (
            <li key={i} className="flex gap-2">
              <span className="mt-[0.55rem] h-1 w-1 shrink-0 rounded-full bg-accent" />
              <span>{it}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
