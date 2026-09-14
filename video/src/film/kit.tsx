import React from "react";
import { AbsoluteFill, Easing, continueRender, delayRender, interpolate, staticFile } from "remotion";
import fonts from "./fonts.json";

// The website's own type system: Newsreader argues, Plex Sans labels, Plex Mono files.
// Self-hosted from public/fonts so a render never depends on reaching Google.
if (typeof document !== "undefined") {
  const handle = delayRender("Loading local fonts", { timeoutInMilliseconds: 120000 });
  const loadOne = (f: (typeof fonts)[number], attempt = 0): Promise<void> =>
    new FontFace(`PNC ${f.family}`, `url(${staticFile(f.file)}) format("woff2")`, { weight: f.weight, style: f.style })
      .load()
      .then((loaded) => {
        document.fonts.add(loaded);
      })
      .catch(() => (attempt < 3 ? new Promise<void>((r) => setTimeout(r, 400)).then(() => loadOne(f, attempt + 1)) : undefined));
  Promise.allSettled(fonts.map((f) => loadOne(f))).finally(() => continueRender(handle));
}
export const SERIF = "'PNC Newsreader', Georgia, serif";
export const SANS = "'PNC IBMPlexSans', 'Segoe UI', sans-serif";
export const MONO = "'PNC IBMPlexMono', Consolas, monospace";
export const KANNADA = "'PNC NotoSerifKannada', serif";

// web/src/styles/tokens.css, verbatim.
export const P = {
  paper: "#fbf7ef",
  paperDeep: "#f2eadd",
  paperSunk: "#ebe1d1",
  ink: "#16130f",
  muted: "#6e6559",
  faint: "#9b9184",
  rule: "#dcd2c0",
  ruleStrong: "#c6b9a2",
  indigo: "#223a5e",
  marigold: "#e08a1e",
  terracotta: "#b8452f",
  sage: "#5b7a5a",
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
export const ease = Easing.bezier(0.22, 0.61, 0.36, 1); // --ease-paper
export const sheet = Easing.bezier(0.65, 0, 0.35, 1); // --ease-sheet
export const ramp = (t: number, a: number, b: number) => interpolate(t, [a, b], [0, 1], clamp);
export const eased = (t: number, a: number, b: number) => ease(ramp(t, a, b));
export const settle = (t: number, a: number, dur = 0.5) => Easing.out(Easing.back(1.5))(ramp(t, a, a + dur));
export const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

/** Cream paper with slow warm glows, the video's replacement for a dark screen. */
export const PaperGlow: React.FC<{ t: number; warmth?: number; drift?: number }> = ({ t, warmth = 1, drift = 1 }) => {
  const dx = Math.sin(t * 0.25 * drift) * 60;
  const dy = Math.cos(t * 0.2 * drift) * 40;
  return (
    <AbsoluteFill style={{ background: P.paper }}>
      <AbsoluteFill
        style={{
          background: [
            `radial-gradient(900px 620px at ${1450 + dx}px ${180 + dy}px, rgba(224,138,30,${0.30 * warmth}), transparent 70%)`,
            `radial-gradient(820px 600px at ${300 - dx}px ${900 - dy}px, rgba(91,122,90,${0.20 * warmth}), transparent 70%)`,
            `radial-gradient(700px 520px at ${420 + dy}px ${160 + dx}px, rgba(34,58,94,${0.10 * warmth}), transparent 70%)`,
          ].join(","),
        }}
      />
      <svg width="1920" height="1080" style={{ position: "absolute", opacity: 0.35, mixBlendMode: "multiply" }}>
        <filter id="grain">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="4" />
          <feColorMatrix values="0 0 0 0 0.45  0 0 0 0 0.38  0 0 0 0 0.28  0 0 0 0.09 0" />
        </filter>
        <rect width="1920" height="1080" filter="url(#grain)" />
      </svg>
    </AbsoluteFill>
  );
};

/** Poor man's directional motion blur: trailing copies along the travel axis. */
export const Streak: React.FC<{ amount: number; axis?: "x" | "y"; children: React.ReactNode; style?: React.CSSProperties }> = ({
  amount,
  axis = "y",
  children,
  style,
}) => {
  const copies = amount > 0.5 ? 6 : 0;
  return (
    <div style={{ position: "relative", ...style }}>
      {Array.from({ length: copies }).map((_, i) => {
        const k = (i + 1) / copies;
        const off = amount * k;
        return (
          <div
            key={i}
            style={{
              position: "absolute", inset: 0, opacity: 0.22 * (1 - k),
              transform: axis === "y" ? `translateY(${off}px)` : `translateX(${off}px)`, filter: `blur(${2 + k * 6}px)`,
            }}
          >
            {children}
          </div>
        );
      })}
      <div style={{ position: "relative", filter: amount > 0.5 ? `blur(${Math.min(8, amount / 18)}px)` : undefined }}>{children}</div>
    </div>
  );
};

/** Typewriter with a caret, used for the reference's "typed line" beat. */
export const Typed: React.FC<{ t: number; at: number; text: string; cps?: number; caret?: boolean; style?: React.CSSProperties }> = ({
  t,
  at,
  text,
  cps = 26,
  caret = true,
  style,
}) => {
  const n = Math.max(0, Math.min(text.length, Math.floor((t - at) * cps)));
  const done = n >= text.length;
  const blink = done ? Math.floor(t * 2.2) % 2 === 0 : true;
  return (
    <span style={style}>
      {text.slice(0, n)}
      {caret && t >= at ? <span style={{ opacity: blink ? 1 : 0, marginLeft: 2, fontWeight: 300 }}>|</span> : null}
    </span>
  );
};
