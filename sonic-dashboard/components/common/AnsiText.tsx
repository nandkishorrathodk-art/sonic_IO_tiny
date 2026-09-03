import React from "react";

/** Foreground color map for ANSI SGR 30-37 / 90-97. */
const FG: Record<string, string> = {
  "30": "#4b5563", "31": "#ef4444", "32": "#22e0a1", "33": "#fbbf24",
  "34": "#3b82f6", "35": "#a855f7", "36": "#22d3ee", "37": "#cbd5e1",
  "90": "#64748b", "91": "#f87171", "92": "#4ade80", "93": "#facc15",
  "94": "#60a5fa", "95": "#c084fc", "96": "#67e8f9", "97": "#f1f5f9",
};

interface Seg {
  text: string;
  color?: string;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
}

function parseAnsi(input: string): Seg[] {
  const out: Seg[] = [];
  let cur: Seg = { text: "" };
  const push = () => { if (cur.text) out.push(cur); cur = { text: "" }; };

  const re = /\x1b\[([0-9;]*)m/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(input)) !== null) {
    if (m.index > last) { cur.text += input.slice(last, m.index); push(); }
    const codes = m[1].split(";").filter(Boolean);
    if (codes.length === 0) {
      cur = { text: "" }; // full reset
    } else {
      for (const c of codes) {
        if (c === "0") { cur = { text: "" }; }
        else if (c === "1") cur.bold = true;
        else if (c === "3") cur.italic = true;
        else if (c === "4") cur.underline = true;
        else if (FG[c]) cur.color = FG[c];
      }
    }
    last = re.lastIndex;
  }
  if (last < input.length) { cur.text += input.slice(last); }
  push();
  return out;
}

const stripEsc = (s: string) => s.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "");

export function AnsiText({ text, className = "" }: { text: string; className?: string }) {
  const segs = parseAnsi(text);
  return (
    <span className={className}>
      {segs.map((s, i) => {
        const style: React.CSSProperties = {};
        if (s.color) style.color = s.color;
        if (s.bold) style.fontWeight = 700;
        if (s.italic) style.fontStyle = "italic";
        if (s.underline) style.textDecoration = "underline";
        return (
          <span key={i} style={style}>
            {stripEsc(s.text)}
          </span>
        );
      })}
    </span>
  );
}
