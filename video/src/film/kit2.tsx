import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import timing from "./vo2.json";
import { MONO, P, SANS, SERIF, ease, eased, lerp, ramp, settle } from "./kit";

// ------------------------------------------------------------------ timing

type Word = { w: string; s: number; e: number };
type Sent = { i: number; start: number; end: number; text: string; words: Word[] };
const TIMING = timing as Sent[];

export const S = (i: number): Sent => TIMING[Math.min(i, TIMING.length - 1)];
/** Start time of `word` (nth occurrence) in sentence i; falls back to the sentence start. */
export const W = (i: number, word: string, nth = 0): number => {
  const hits = S(i).words.filter((w) => w.w === word.toUpperCase());
  return (hits[nth] ?? hits[0] ?? { s: S(i).start }).s;
};
export const VO_END = TIMING[TIMING.length - 1].end;

/** While the cross-case merge rule is not deployed, the merge beat carries an honest tag. */
export const MERGE_IS_LIVE = false;

export function kf(t: number, keys: [number, number][]): number {
  if (t <= keys[0][0]) return keys[0][1];
  for (let i = 0; i < keys.length - 1; i++) {
    const [t0, v0] = keys[i];
    const [t1, v1] = keys[i + 1];
    if (t <= t1) return lerp(v0, v1, ease(t1 === t0 ? 1 : (t - t0) / (t1 - t0)));
  }
  return keys[keys.length - 1][1];
}

// ------------------------------------------------------------------ stage

type Move = "whip" | "rise" | "fade" | "none";

/** One scene on screen between `from` and `to`, entering and leaving with a Numtera-style move. */
export const Stage: React.FC<{ t: number; from: number; to: number; enter?: Move; exit?: Move; children: React.ReactNode }> = ({
  t,
  from,
  to,
  enter = "whip",
  exit = "whip",
  children,
}) => {
  if (t < from - 0.05 || t > to + 0.6) return null;
  const a = ramp(t, from, from + 0.55);
  const b = exit === "none" ? 0 : ramp(t, to, to + 0.5);
  let scale = 1;
  let blur = 0;
  let y = 0;
  let opacity = 1;
  if (enter === "whip") {
    scale *= lerp(1.45, 1, ease(a));
    blur += (1 - a) * 18;
    opacity *= a;
  } else if (enter === "rise") {
    y += (1 - ease(a)) * 90;
    blur += (1 - a) * 8;
    opacity *= a;
  } else if (enter === "fade") {
    opacity *= a;
  }
  if (exit === "whip") {
    scale *= lerp(1, 2.3, b * b);
    blur += b * 24;
    opacity *= 1 - b;
  } else if (exit === "rise") {
    y -= ease(b) * 120;
    blur += b * 8;
    opacity *= 1 - b;
  } else if (exit === "fade") {
    opacity *= 1 - b;
  }
  return (
    <AbsoluteFill style={{ transform: `translateY(${y}px) scale(${scale})`, filter: blur > 0.2 ? `blur(${blur}px)` : undefined, opacity }}>
      {children}
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ pieces

export const Paper: React.FC<{ style?: React.CSSProperties; children?: React.ReactNode }> = ({ style, children }) => (
  <div
    style={{
      background: "#fffdf8", border: `1px solid ${P.rule}`, borderRadius: 12, boxShadow: "0 24px 50px rgba(60,40,10,0.12), 0 2px 6px rgba(60,40,10,0.05)",
      boxSizing: "border-box", ...style,
    }}
  >
    {children}
  </div>
);

export const Mono: React.FC<{ children: React.ReactNode; size?: number; color?: string; style?: React.CSSProperties }> = ({ children, size = 16, color = P.muted, style }) => (
  <span style={{ fontFamily: MONO, fontSize: size, letterSpacing: size * 0.14, color, textTransform: "uppercase", ...style }}>{children}</span>
);

export const Stamp: React.FC<{ t: number; at: number; text: string; color?: string; size?: number; rotate?: number; style?: React.CSSProperties }> = ({
  t,
  at,
  text,
  color = P.sage,
  size = 26,
  rotate = -7,
  style,
}) => {
  const k = ramp(t, at, at + 0.18);
  if (k <= 0) return null;
  return (
    <div
      style={{
        display: "inline-block", transform: `rotate(${rotate}deg) scale(${lerp(2.4, 1, k)})`, opacity: k, filter: `blur(${(1 - k) * 6}px)`,
        fontFamily: MONO, fontWeight: 500, fontSize: size, letterSpacing: size * 0.13, color, border: `${Math.max(2, size / 8)}px solid ${color}`,
        borderRadius: 6, padding: `${size * 0.15}px ${size * 0.5}px`, background: "rgba(251,247,239,0.9)", whiteSpace: "nowrap", ...style,
      }}
    >
      {text}
    </div>
  );
};

export const Source: React.FC<{ t: number; at: number; children: React.ReactNode }> = ({ t, at, children }) => (
  <div style={{ position: "absolute", left: 90, bottom: 58, opacity: ramp(t, at, at + 0.5) }}>
    <Mono size={15} color={P.faint}>Source · {children}</Mono>
  </div>
);

/** A sentence whose words appear as the narrator says them. */
export const Spoken: React.FC<{
  t: number;
  i: number;
  style?: React.CSSProperties;
  accent?: string[];
  accentStyle?: React.CSSProperties;
  text?: string;
}> = ({ t, i, style, accent = [], accentStyle, text }) => {
  const sent = S(i);
  const shown = (text ?? sent.text).split(" ");
  let wi = 0;
  let last = sent.start;
  return (
    <div style={style}>
      {shown.map((word, k) => {
        const clean = word.toUpperCase().replace(/[^A-Z']/g, "");
        const found = clean ? sent.words.findIndex((w, j) => j >= wi && w.w === clean) : -1;
        if (found >= 0) {
          last = sent.words[found].s;
          wi = found + 1;
        }
        const at = last;
        const a = ramp(t, at - 0.08, at + 0.22);
        const isAccent = accent.includes(word.replace(/[^A-Za-z']/g, "").toLowerCase());
        return (
          <React.Fragment key={k}>
            <span
              style={{
                display: "inline-block", opacity: a, transform: `translateY(${(1 - a) * 18}px)`, filter: a < 1 ? `blur(${(1 - a) * 6}px)` : undefined,
                ...(isAccent ? accentStyle : null),
              }}
            >
              {word}
            </span>{" "}
          </React.Fragment>
        );
      })}
    </div>
  );
};

type Focus = { cx: number; cy: number; zoom: number };
type Highlight = { x: number; y: number; w: number; h: number; from: number; to?: number; color?: string };

/**
 * A captured page of the live site in a floating frame. `focus` keyframes pan and zoom
 * inside the capture (coordinates are capture pixels, 1920x1080), like a camera on the UI.
 */
export const Shot: React.FC<{
  t: number;
  src: string;
  x: number;
  y: number;
  w: number;
  h: number;
  focus: [number, Focus][];
  rx?: number;
  ry?: number;
  opacity?: number;
  blur?: number;
  highlights?: Highlight[];
  masks?: { x: number; y: number; w: number; h: number; opacity: number }[];
  sweepAt?: number;
  imgW?: number;
  imgH?: number;
  children?: React.ReactNode;
}> = ({ t, src, x, y, w, h, focus, rx = 6, ry = -10, opacity = 1, blur = 0, highlights = [], masks = [], sweepAt, imgW = 1920, imgH = 1080, children }) => {
  const cx = kf(t, focus.map(([tt, f]) => [tt, f.cx]));
  const cy = kf(t, focus.map(([tt, f]) => [tt, f.cy]));
  const zoom = Math.exp(kf(t, focus.map(([tt, f]) => [tt, Math.log(f.zoom)])));
  const sweep = sweepAt === undefined ? -1 : ramp(t, sweepAt, sweepAt + 1.4);
  if (opacity <= 0.01) return null;
  return (
    <div style={{ position: "absolute", left: x, top: y, perspective: 2400, opacity, filter: blur > 0.2 ? `blur(${blur}px)` : undefined }}>
      <div
        style={{
          width: w, height: h, borderRadius: 16, overflow: "hidden", position: "relative", background: P.paper,
          transform: `rotateX(${rx}deg) rotateY(${ry}deg)`, boxShadow: "0 50px 90px rgba(60,40,10,0.20), 0 0 0 1px rgba(60,40,10,0.10)",
        }}
      >
        <div style={{ position: "absolute", left: 0, top: 0, width: imgW, height: imgH, transformOrigin: "0 0", transform: `translate(${w / 2 - cx * zoom}px, ${h / 2 - cy * zoom}px) scale(${zoom})` }}>
          <Img src={staticFile(src)} style={{ width: imgW, height: imgH, display: "block" }} />
          {masks.map((m, k) => (
            <div key={`m${k}`} style={{ position: "absolute", left: m.x, top: m.y, width: m.w, height: m.h, background: P.paper, opacity: m.opacity }} />
          ))}
          {highlights.map((hl, k) => {
            const o = ramp(t, hl.from, hl.from + 0.3) * (hl.to === undefined ? 1 : 1 - ramp(t, hl.to, hl.to + 0.3));
            return o > 0 ? (
              <div
                key={`h${k}`}
                style={{
                  position: "absolute", left: hl.x, top: hl.y, width: hl.w, height: hl.h, borderRadius: 6, opacity: o,
                  background: `${hl.color ?? P.marigold}22`, boxShadow: `0 0 0 2px ${hl.color ?? P.marigold}`,
                }}
              />
            ) : null;
          })}
          {children}
        </div>
        {sweep >= 0 && sweep < 1 ? (
          <div
            style={{
              position: "absolute", inset: 0,
              background: `linear-gradient(105deg, transparent ${lerp(-40, 120, sweep) - 18}%, rgba(255,236,200,0.55) ${lerp(-40, 120, sweep)}%, transparent ${lerp(-40, 120, sweep) + 18}%)`,
            }}
          />
        ) : null}
      </div>
    </div>
  );
};

/** The explainer card beside the live UI: which agent, what it does, what it did here. */
export const AgentCard: React.FC<{ t: number; from: number; to: number; n: string; name: string; line: string; label?: string; children?: React.ReactNode; x?: number; y?: number; w?: number }> = ({
  t,
  from,
  to,
  n,
  name,
  line,
  label,
  children,
  x = 1310,
  y = 250,
  w = 540,
}) => {
  const a = settle(t, from, 0.55);
  const b = eased(t, to, to + 0.4);
  const o = ramp(t, from, from + 0.2) * (1 - b);
  if (o <= 0.01) return null;
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, opacity: o, transform: `translateX(${(1 - a) * 80 - b * 40}px)` }}>
      <Paper style={{ padding: "28px 32px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Mono size={15} color={P.marigold}>{label ?? `Agent ${n}`}</Mono>
          <div style={{ width: 10, height: 10, borderRadius: 5, background: P.sage, boxShadow: `0 0 0 5px ${P.sage}22` }} />
        </div>
        <div style={{ fontFamily: SERIF, fontSize: 52, color: P.ink, letterSpacing: -1.2, marginTop: 6, lineHeight: 1.05 }}>{name}</div>
        <div style={{ fontFamily: SERIF, fontSize: 28, color: P.muted, marginTop: 10, lineHeight: 1.3 }}>{line}</div>
        {children ? <div style={{ marginTop: 20, borderTop: `1px solid ${P.rule}`, paddingTop: 18 }}>{children}</div> : null}
      </Paper>
    </div>
  );
};

export const Check: React.FC<{ ok: boolean; size?: number }> = ({ ok, size = 28 }) => (
  <div
    style={{
      width: size, height: size, borderRadius: size / 2, background: ok ? P.sage : P.terracotta, display: "inline-flex", alignItems: "center",
      justifyContent: "center", flexShrink: 0,
    }}
  >
    <svg width={size * 0.55} height={size * 0.55} viewBox="0 0 16 16">
      {ok ? (
        <path d="M3 8.5l3 3 7-7" stroke="#fffdf8" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      ) : (
        <path d="M4 4l8 8M12 4l-8 8" stroke="#fffdf8" strokeWidth="2.6" strokeLinecap="round" />
      )}
    </svg>
  </div>
);

export const Headline: React.FC<{ children: React.ReactNode; size?: number; style?: React.CSSProperties }> = ({ children, size = 96, style }) => (
  <div style={{ fontFamily: SERIF, fontSize: size, color: P.ink, letterSpacing: -size * 0.028, lineHeight: 1.04, ...style }}>{children}</div>
);

export const Em: React.FC<{ children: React.ReactNode; color?: string; mark?: number }> = ({ children, color = P.terracotta, mark }) => (
  <span style={{ fontStyle: "italic", color, position: "relative", display: "inline-block" }}>
    {mark !== undefined ? (
      <span
        style={{
          position: "absolute", left: -6, right: -6, bottom: "0.12em", height: "0.3em", background: P.marigold, opacity: 0.3,
          transformOrigin: "left", transform: `scaleX(${mark})`, borderRadius: 3,
        }}
      />
    ) : null}
    <span style={{ position: "relative" }}>{children}</span>
  </span>
);

export { SANS };
