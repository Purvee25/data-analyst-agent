// Reveals text with a lightweight typewriter effect so answers feel like they
// arrive in real time. Purely cosmetic — the full text is already in hand; we
// just unveil it. Animates once on mount (the parent keys turns stably).

import { useEffect, useState } from "react";

export default function TypedText({ text, speed = 12 }: { text: string; speed?: number }) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    setCount(0);
    let i = 0;
    // Reveal a few characters per tick so long answers don't crawl.
    const step = Math.max(1, Math.round(text.length / 120));
    const id = setInterval(() => {
      i += step;
      if (i >= text.length) {
        setCount(text.length);
        clearInterval(id);
      } else {
        setCount(i);
      }
    }, speed);
    return () => clearInterval(id);
  }, [text, speed]);

  const done = count >= text.length;
  return (
    <span>
      {text.slice(0, count)}
      {!done && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-indigo-300 align-middle" />}
    </span>
  );
}
