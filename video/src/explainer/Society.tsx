import React, { useMemo } from "react";
import { AbsoluteFill } from "remotion";
import { C, KANNADA, MONO, SANS, eased, keyframes, lerp, popIn, ramp, rng, sent, wordAt } from "./core";

// ------------------------------------------------------------ geometry

const U = 20;
const C30 = Math.cos(Math.PI / 6);
type P = [number, number];
const iso = (x: number, y: number, z: number): P => [(x - y) * C30 * U, (x + y) * 0.5 * U - z * U];
const pts = (ps: P[]) => ps.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");

const TW = 6;
const TD = 5;
const TH = 17;
const FLOORS = 10;
// Painter's order: back to front.
const TOWERS = [
  { id: "A", x: 0, y: 0 },
  { id: "C", x: 0, y: 10 },
  { id: "B", x: 11, y: 0 },
  { id: "D", x: 11, y: 10 },
];

type Win = { key: string; tower: string; poly: P[]; c: P; lit: number };

function buildWindows(): Win[] {
  const r = rng(7);
  const out: Win[] = [];
  for (const t of TOWERS) {
    for (let fl = 0; fl < FLOORS; fl++) {
      const z0 = 1.0 + fl * 1.55;
      const z1 = z0 + 0.8;
      for (let c = 0; c < 4; c++) {
        const x0 = t.x + 0.55 + c * 1.4;
        const x1 = x0 + 0.75;
        const y = t.y + TD;
        out.push({
          key: `${t.id}L${fl}${c}`,
          tower: t.id,
          poly: [iso(x0, y, z0), iso(x1, y, z0), iso(x1, y, z1), iso(x0, y, z1)],
          c: iso((x0 + x1) / 2, y, (z0 + z1) / 2),
          lit: r(),
        });
      }
      for (let c = 0; c < 3; c++) {
        const y0 = t.y + 0.55 + c * 1.45;
        const y1 = y0 + 0.75;
        const x = t.x + TW;
        out.push({
          key: `${t.id}R${fl}${c}`,
          tower: t.id,
          poly: [iso(x, y0, z0), iso(x, y1, z0), iso(x, y1, z1), iso(x, y0, z1)],
          c: iso(x, (y0 + y1) / 2, (z0 + z1) / 2),
          lit: r(),
        });
      }
    }
  }
  return out;
}

type Block = { x: number; y: number; w: number; d: number; h: number; lit: number[] };
function buildCity(): Block[] {
  const r = rng(11);
  const out: Block[] = [];
  let guard = 0;
  while (out.length < 70 && guard++ < 2000) {
    const x = Math.round(-46 + r() * 100);
    const y = Math.round(-40 + r() * 90);
    const w = 3 + Math.round(r() * 4);
    const d = 3 + Math.round(r() * 3);
    const nearSociety = x > -9 && x < 25 && y > -9 && y < 24;
    const inFront = x + y > 20 && Math.abs(x - y) < 34;
    if (nearSociety || inFront) continue;
    if (out.some((b) => Math.abs(b.x - x) < 8 && Math.abs(b.y - y) < 8)) continue;
    out.push({ x, y, w, d, h: 2 + r() * 9, lit: [r(), r(), r(), r()] });
  }
  return out.sort((a, b) => a.x + a.y - (b.x + b.y));
}

// ------------------------------------------------------------ the story

const FOCUS = "CL41";
const T = {
  fadeIn: 4.7,
  father: wordAt(2, "FATHER") - 0.15,
  mother: wordAt(3, "MOTHER") - 0.15,
  grandmother: wordAt(4, "GRANDMOTHER") - 0.15,
  building: sent(5).start,
  alone: sent(6).start,
  stamina: sent(7).start,
  eleven: wordAt(7, "ELEVEN"),
  resolved: wordAt(7, "RESOLVED"),
  done: wordAt(7, "DONE"),
  panchayat: sent(8).start,
  agents: wordAt(8, "AGENTS"),
  oneHousehold: sent(9).start,
  neighbour: wordAt(9, "NEIGHBOUR"),
  stronger: wordAt(9, "STRONGER"),
  out: sent(10).start,
};

type Kind = "water" | "lift" | "light" | "garbage";
const KIND_COLOR: Record<Kind, string> = { water: C.amber, lift: C.lift, light: C.light, garbage: C.garbage };
const NEIGHBOURS: { key: string; text: string; kind: Kind; dy: number }[] = [
  { key: "AL81", text: "No water since Monday", kind: "water", dy: -26 },
  { key: "BR42", text: "No water", kind: "water", dy: -26 },
  { key: "CL83", text: "Tank dry", kind: "water", dy: -26 },
  { key: "AL40", text: "Lift broken", kind: "lift", dy: 26 },
  { key: "BL73", text: "No supply, 3 days", kind: "water", dy: -26 },
  { key: "DR81", text: "No water, 3 days", kind: "water", dy: -26 },
  { key: "BL30", text: "Streetlight out", kind: "light", dy: 26 },
  { key: "CR60", text: "Tank empty", kind: "water", dy: 26 },
  { key: "BR91", text: "Motor running dry", kind: "water", dy: -26 },
  { key: "DL21", text: "Tank dry again", kind: "water", dy: 26 },
  { key: "DR32", text: "Lift broken", kind: "lift", dy: -26 },
  { key: "AR62", text: "No water", kind: "water", dy: -26 },
  { key: "CR91", text: "Streetlight out", kind: "light", dy: -26 },
  { key: "DL63", text: "No supply", kind: "water", dy: -26 },
  { key: "AR20", text: "Garbage not picked", kind: "garbage", dy: 26 },
  { key: "CL20", text: "Dry taps", kind: "water", dy: 26 },
];

type Cam = { cx: number; cy: number; s: number };
const toScreen = (p: P, cam: Cam): P => [960 + cam.s * (p[0] - cam.cx), 540 + cam.s * (p[1] - cam.cy)];

const OFFICE: P = [1690, 150];
const CASE_REST: P = [420, 860];
// Other problems line up on the right, sized by priority, while water becomes the case.
const SLOTS: Record<Exclude<Kind, "water">, { p: P; scale: number; at: number }> = {
  lift: { p: [1500, 760], scale: 1.3, at: T.neighbour + 0.6 },
  light: { p: [1500, 850], scale: 1.05, at: T.neighbour + 1.1 },
  garbage: { p: [1500, 925], scale: 0.88, at: T.neighbour + 1.6 },
};
const JOURNEY_START: P = [196, 130];

export const Society: React.FC<{ t: number }> = ({ t }) => {
  const windows = useMemo(buildWindows, []);
  const city = useMemo(buildCity, []);
  const byKey = useMemo(() => Object.fromEntries(windows.map((w) => [w.key, w])), [windows]);

  const overview = iso(8.5, 7.5, 7.5);
  const focusWin = byKey[FOCUS].c;
  const focusFrame: P = [focusWin[0] + 10, focusWin[1] - 48];

  const logS = keyframes(t, [
    [4.4, Math.log(0.95)],
    [5.4, Math.log(1.05)],
    [8.9, Math.log(4.3)],
    [T.building - 0.2, Math.log(4.55)],
    [T.building + 2.6, Math.log(1.42)],
    [T.panchayat, Math.log(1.5)],
    [T.out, Math.log(1.58)],
  ]);
  const zoomK = keyframes(t, [
    [5.4, 0],
    [8.9, 1],
    [T.building - 0.2, 1],
    [T.building + 2.6, 0],
  ]);
  const cam: Cam = {
    cx: lerp(overview[0], focusFrame[0], zoomK),
    cy: lerp(overview[1], focusFrame[1], zoomK) + keyframes(t, [[T.building + 2.6, 0], [T.panchayat, 0], [T.panchayat + 1.5, -40]]),
    s: Math.exp(logS),
  };

  const sceneOpacity = ramp(t, T.fadeIn, T.fadeIn + 0.8) * (1 - ramp(t, T.out - 0.9, T.out));
  const ws = toScreen(focusWin, cam);

  // Neighbour chips: pop, go quiet over "eleven weeks", wake up under Panchayat, then merge.
  const popAt = (i: number) => T.building + 0.25 + i * 0.24;
  const dimAt = (i: number) => T.stamina + 1.6 + i * 0.28;
  const waterOrder = NEIGHBOURS.filter((n) => n.kind === "water").map((n) => n.key);
  const flightStart = (key: string) => T.neighbour - 0.1 + waterOrder.indexOf(key) * 0.26;
  const arrived = waterOrder.filter((k) => t >= flightStart(k) + 0.55).length;

  const caseForm = popIn(t, T.oneHousehold + 0.2, 0.5);
  const caseLift = eased(t, T.out - 1.0, T.out + 0.2);
  const collapse = eased(t, T.building + 0.1, T.building + 2.3);
  const flatChipPos: P = toScreen(focusWin, cam);
  const casePos: P = [
    lerp(lerp(flatChipPos[0], CASE_REST[0], eased(t, T.oneHousehold, T.oneHousehold + 1.2)), JOURNEY_START[0], caseLift),
    lerp(lerp(flatChipPos[1] - 30, CASE_REST[1], eased(t, T.oneHousehold, T.oneHousehold + 1.2)), JOURNEY_START[1], caseLift),
  ];
  const caseScale = (1 + 0.05 * arrived) * lerp(1, 0.78, caseLift);

  const week = 1 + Math.floor(10 * ramp(t, T.stamina + 0.3, T.eleven + 0.5));
  const quiet = ramp(t, T.panchayat - 0.6, T.panchayat + 0.2);

  return (
    <AbsoluteFill style={{ opacity: sceneOpacity, background: `radial-gradient(ellipse at 50% 40%, #0d1630 0%, ${C.bg} 70%)` }}>
      <svg width={1920} height={1080} style={{ position: "absolute" }}>
        <g transform={`translate(960 540) scale(${cam.s}) translate(${-cam.cx} ${-cam.cy})`}>
          <polygon points={pts([iso(-70, -70, 0), iso(90, -70, 0), iso(90, 90, 0), iso(-70, 90, 0)])} fill="#070c18" />
          {[-6, 21].map((y) => (
            <polygon key={`ry${y}`} points={pts([iso(-70, y, 0), iso(90, y, 0), iso(90, y + 2, 0), iso(-70, y + 2, 0)])} fill="#0e1628" />
          ))}
          {[-6, 23].map((x) => (
            <polygon key={`rx${x}`} points={pts([iso(x, -70, 0), iso(x + 2, -70, 0), iso(x + 2, 90, 0), iso(x, 90, 0)])} fill="#0e1628" />
          ))}
          <polygon points={pts([iso(-2.5, -2.5, 0), iso(19.5, -2.5, 0), iso(19.5, 17.5, 0), iso(-2.5, 17.5, 0)])} fill="#101a2e" />
          {city.map((b, i) => (
            <g key={`b${i}`} opacity={0.75}>
              <polygon points={pts([iso(b.x, b.y + b.d, 0), iso(b.x + b.w, b.y + b.d, 0), iso(b.x + b.w, b.y + b.d, b.h), iso(b.x, b.y + b.d, b.h)])} fill="#10182a" />
              <polygon points={pts([iso(b.x + b.w, b.y, 0), iso(b.x + b.w, b.y + b.d, 0), iso(b.x + b.w, b.y + b.d, b.h), iso(b.x + b.w, b.y, b.h)])} fill="#0b1120" />
              <polygon points={pts([iso(b.x, b.y, b.h), iso(b.x + b.w, b.y, b.h), iso(b.x + b.w, b.y + b.d, b.h), iso(b.x, b.y + b.d, b.h)])} fill="#151e33" />
              {b.lit.map((l, j) =>
                l > 0.45 ? (
                  <circle key={j} cx={iso(b.x + 0.8 + j * (b.w / 4), b.y + b.d, b.h * (0.3 + 0.15 * j))[0]} cy={iso(b.x + 0.8 + j * (b.w / 4), b.y + b.d, b.h * (0.3 + 0.15 * j))[1]} r={1.6} fill="#ffcf7a" opacity={0.5} />
                ) : null,
              )}
            </g>
          ))}
          {TOWERS.map((tw) => {
            const { x, y } = tw;
            return (
              <g key={tw.id}>
                <polygon points={pts([iso(x, y + TD, 0), iso(x + TW, y + TD, 0), iso(x + TW, y + TD, TH), iso(x, y + TD, TH)])} fill="#1b2438" />
                <polygon points={pts([iso(x + TW, y, 0), iso(x + TW, y + TD, 0), iso(x + TW, y + TD, TH), iso(x + TW, y, TH)])} fill="#131a2b" />
                <polygon points={pts([iso(x, y, TH), iso(x + TW, y, TH), iso(x + TW, y + TD, TH), iso(x, y + TD, TH)])} fill="#28324a" />
                <polygon points={pts([iso(x + 1.2, y + 1.2, TH + 1.2), iso(x + 2.6, y + 1.2, TH + 1.2), iso(x + 2.6, y + 2.4, TH + 1.2), iso(x + 1.2, y + 2.4, TH + 1.2)])} fill="#39445f" />
                <polygon points={pts([iso(x + 1.2, y + 2.4, TH), iso(x + 2.6, y + 2.4, TH), iso(x + 2.6, y + 2.4, TH + 1.2), iso(x + 1.2, y + 2.4, TH + 1.2)])} fill="#2b3550" />
                {windows
                  .filter((w) => w.tower === tw.id)
                  .map((w) => {
                    const isFocus = w.key === FOCUS;
                    const on = isFocus || w.lit > 0.3;
                    const flicker = 0.06 * Math.sin(t * 1.7 + w.lit * 60);
                    return (
                      <polygon
                        key={w.key}
                        points={pts(w.poly)}
                        fill={on ? "#ffd98a" : "#0c1322"}
                        opacity={on ? (isFocus ? 1 : 0.45 + 0.45 * w.lit + flicker) : 1}
                      />
                    );
                  })}
              </g>
            );
          })}
          <circle
            cx={focusWin[0]}
            cy={focusWin[1]}
            r={12 + 4 * Math.sin(t * 4)}
            fill={C.amber}
            opacity={0.35 * ramp(t, 5.6, 7) * (1 - ramp(t, T.building + 1, T.building + 2))}
          />
        </g>

        {/* Every household files alone: a thin line each, to one office. */}
        {NEIGHBOURS.map((n, i) => {
          const p = toScreen(byKey[n.key].c, cam);
          const k = eased(t, T.alone + 0.1 + i * 0.1, T.alone + 0.8 + i * 0.1);
          const o = k * (1 - ramp(t, dimAt(i), dimAt(i) + 1.2)) * (1 - quiet);
          return o > 0.01 ? (
            <line key={`l${i}`} x1={p[0]} y1={p[1] + n.dy} x2={lerp(p[0], OFFICE[0], k)} y2={lerp(p[1] + n.dy, OFFICE[1] + 40, k)} stroke={KIND_COLOR[n.kind]} strokeWidth={1.4} strokeDasharray="5 6" opacity={0.55 * o} />
          ) : null;
        })}
      </svg>

      {/* ---- the office every household is writing to, separately ---- */}
      <div
        style={{
          position: "absolute", left: OFFICE[0] - 90, top: OFFICE[1] - 10, width: 180, textAlign: "center",
          opacity: ramp(t, T.alone, T.alone + 0.5) * (1 - quiet), fontFamily: MONO, color: C.dim, fontSize: 15, letterSpacing: 1,
        }}
      >
        <svg width={64} height={50} viewBox="0 0 64 50">
          <polygon points="32,2 62,16 2,16" fill="#2a3450" />
          {[10, 22, 34, 46].map((x) => (
            <rect key={x} x={x} y={18} width={7} height={24} fill="#2a3450" />
          ))}
          <rect x={2} y={44} width={60} height={5} fill="#2a3450" />
        </svg>
        <div>THE RIGHT OFFICE?</div>
      </div>

      {/* ---- week counter ---- */}
      <div
        style={{
          position: "absolute", left: 80, top: 70, fontFamily: MONO, color: C.dim, fontSize: 22, letterSpacing: 2,
          opacity: ramp(t, T.stamina + 0.2, T.stamina + 0.7) * (1 - quiet),
        }}
      >
        FOLLOW-UP · WEEK <span style={{ color: C.ink, fontSize: 40, fontWeight: 600 }}>{String(week).padStart(2, "0")}</span>
      </div>

      {/* ---- neighbour chips ---- */}
      {NEIGHBOURS.map((n, i) => {
        const p0 = toScreen(byKey[n.key].c, cam);
        const home: P = [p0[0], p0[1] + n.dy];
        const s = popIn(t, popAt(i), 0.4);
        if (s <= 0.001) return null;
        const stampedEarly = n.kind === "water" && ["AL81", "DR81", "CR60"].includes(n.key);
        const dim = ramp(t, dimAt(i), dimAt(i) + 1.2) * (1 - quiet) * (stampedEarly ? 1 - ramp(t, T.resolved - 0.3, T.resolved) : 1);
        let x = home[0];
        let y = home[1];
        let scale = s;
        let opacity = 1 - 0.65 * dim;
        if (n.kind === "water") {
          const k = eased(t, flightStart(n.key), flightStart(n.key) + 0.55);
          const cx = lerp(home[0], casePos[0], 0.5);
          const cy = Math.min(home[1], casePos[1]) - 160;
          x = (1 - k) * (1 - k) * home[0] + 2 * (1 - k) * k * cx + k * k * casePos[0];
          y = (1 - k) * (1 - k) * home[1] + 2 * (1 - k) * k * cy + k * k * casePos[1];
          scale = s * lerp(1, 0.35, k);
          opacity *= 1 - ramp(t, flightStart(n.key) + 0.45, flightStart(n.key) + 0.55);
        } else {
          const slot = SLOTS[n.kind];
          const group = NEIGHBOURS.filter((m) => m.kind === n.kind);
          const k = eased(t, slot.at, slot.at + 0.7);
          x = lerp(home[0], slot.p[0], k);
          y = lerp(home[1], slot.p[1], k);
          if (group[0].key !== n.key) opacity *= 1 - ramp(t, slot.at + 0.6, slot.at + 0.7);
          else scale = s * lerp(1, slot.scale, k);
        }
        opacity *= 1 - ramp(t, T.out - 1.0, T.out - 0.4);
        if (opacity <= 0.01) return null;
        const merged = n.kind !== "water" && NEIGHBOURS.filter((m) => m.kind === n.kind).length > 1 && t > SLOTS[n.kind].at + 0.6;
        const stamped = n.kind === "water" && ["AL81", "DR81", "CR60"].includes(n.key);
        return (
          <div key={n.key} style={{ position: "absolute", left: x, top: y, transform: `translate(-50%,-50%) scale(${scale})`, opacity }}>
            <div
              style={{
                display: "flex", alignItems: "center", gap: 8, whiteSpace: "nowrap", padding: "6px 12px", borderRadius: 9,
                background: C.panel, border: `1.5px solid ${KIND_COLOR[n.kind]}`, color: C.ink, fontFamily: SANS, fontWeight: 600, fontSize: 16,
                boxShadow: `0 0 18px ${KIND_COLOR[n.kind]}33`,
              }}
            >
              <span style={{ width: 8, height: 8, borderRadius: 4, background: KIND_COLOR[n.kind] }} />
              {merged ? `${n.text} · 2 homes` : n.text}
            </div>
            {stamped ? (
              <div
                style={{
                  position: "absolute", left: "50%", top: -30, whiteSpace: "nowrap", fontFamily: MONO, fontSize: 13, fontWeight: 600,
                  transform: `translateX(-50%) rotate(-6deg) scale(${popIn(t, T.resolved + 0.1, 0.35)})`, opacity: 1 - quiet,
                  color: C.green, border: `1.5px solid ${C.green}`, borderRadius: 4, padding: "1px 6px", background: "rgba(6,10,20,0.9)",
                }}
              >
                CLOSED: RESOLVED{" "}
                <span style={{ color: C.red, opacity: ramp(t, T.done, T.done + 0.3) }}>· tap still dry</span>
              </div>
            ) : null}
          </div>
        );
      })}

      {/* ---- the family, inside one flat ---- */}
      {[
        { at: T.father, who: "FATHER", what: "Third day without supply", dx: -470, dy: -300, high: false },
        { at: T.mother, who: "MOTHER", what: "Empty tank, nothing to cook", dx: 70, dy: -360, high: false },
        { at: T.grandmother, who: "GRANDMOTHER", what: "Dialysis on Thursday", dx: -190, dy: -175, high: true },
      ].map((m) => {
        const s = popIn(t, m.at, 0.5) * lerp(1, 0.3, collapse);
        const o = 1 - ramp(t, T.building + 1.6, T.building + 2.2);
        if (s <= 0.001 || o <= 0.01) return null;
        const cx = ws[0] + m.dx * (1 - collapse);
        const cy = ws[1] + m.dy * (1 - collapse);
        return (
          <React.Fragment key={m.who}>
            <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0, opacity: o * ramp(t, m.at, m.at + 0.3) }}>
              <line x1={ws[0]} y1={ws[1]} x2={cx} y2={cy + 50} stroke={m.high ? C.red : C.amber} strokeWidth={2} strokeDasharray="4 5" />
            </svg>
            <div style={{ position: "absolute", left: cx, top: cy, transform: `translate(-50%,-50%) scale(${s})`, opacity: o }}>
              <div
                style={{
                  width: 400, padding: "16px 22px", borderRadius: 14, background: C.panel, border: `2px solid ${m.high ? C.red : C.amber}`,
                  boxShadow: `0 0 40px ${m.high ? C.red : C.amber}40`,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", fontFamily: MONO, fontSize: 16, letterSpacing: 2, color: m.high ? C.red : C.amber }}>
                  <span>{m.who}</span>
                  {m.high ? <span>● HIGH PRIORITY</span> : null}
                </div>
                <div style={{ fontFamily: SANS, fontWeight: 600, fontSize: 30, color: C.ink, marginTop: 6 }}>{m.what}</div>
              </div>
            </div>
          </React.Fragment>
        );
      })}

      {/* ---- one flat, now one chip, then the case ---- */}
      {t > T.building + 1.9 ? (
        <div
          style={{
            position: "absolute", left: casePos[0], top: casePos[1],
            transform: `translate(-50%,-50%) scale(${(t < T.oneHousehold + 0.2 ? popIn(t, T.building + 1.9, 0.4) : 1) * caseScale * (t >= T.oneHousehold + 0.2 ? 0.8 + 0.2 * caseForm : 1)})`,
            opacity: 1 - 0.65 * ramp(t, dimAt(0), dimAt(0) + 1.2) * (1 - quiet) - ramp(t, T.out - 0.3, T.out),
          }}
        >
          {t < T.oneHousehold + 0.2 ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8, whiteSpace: "nowrap", padding: "7px 14px", borderRadius: 10, background: C.panel, border: `2px solid ${C.amber}`, color: C.ink, fontFamily: SANS, fontWeight: 700, fontSize: 17 }}>
              <span style={{ width: 9, height: 9, borderRadius: 5, background: C.amber }} />
              Flat C-402 · 3 people, no water
            </div>
          ) : (
            <div style={{ width: 430, padding: "18px 24px", borderRadius: 16, background: C.panel, border: `2.5px solid ${C.indigo}`, boxShadow: `0 0 60px ${C.indigo}55` }}>
              <div style={{ fontFamily: MONO, fontSize: 16, letterSpacing: 2, color: C.indigo }}>CASE OPENED</div>
              <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 34, color: C.ink, marginTop: 4 }}>No water</div>
              <div style={{ fontFamily: SANS, fontWeight: 500, fontSize: 22, color: C.amber, marginTop: 4 }}>
                {1 + arrived} {arrived === 0 ? "household" : "households"} · 4th Cross, Ward 12
              </div>
            </div>
          )}
        </div>
      ) : null}

      <div
        style={{
          position: "absolute", left: SLOTS.lift.p[0], top: SLOTS.lift.p[1] - 64, transform: "translateX(-50%)", whiteSpace: "nowrap",
          fontFamily: MONO, fontSize: 15, letterSpacing: 2, color: C.dim,
          opacity: ramp(t, SLOTS.lift.at + 0.3, SLOTS.lift.at + 0.8) * (1 - ramp(t, T.out - 1.2, T.out - 0.7)),
        }}
      >
        OTHER ISSUES · SIZED BY PRIORITY
      </div>

      {/* ---- pattern watch label ---- */}
      <div
        style={{
          position: "absolute", left: CASE_REST[0], top: CASE_REST[1] + 110, transform: "translateX(-50%)", whiteSpace: "nowrap",
          fontFamily: MONO, fontSize: 16, color: C.dim, opacity: ramp(t, T.neighbour - 0.4, T.neighbour + 0.2) * (1 - ramp(t, T.out - 1.2, T.out - 0.7)),
        }}
      >
        <span style={{ color: C.indigo }}>Pattern Watch</span> · ambient · DynamoDB Streams → Lambda
      </div>

      {/* ---- honesty: the cross-case merge is designed, not live ---- */}
      <div
        style={{
          position: "absolute", left: CASE_REST[0], top: CASE_REST[1] + 142, transform: "translateX(-50%)", whiteSpace: "nowrap",
          fontFamily: MONO, fontSize: 15, letterSpacing: 1, color: C.amber, border: `1.5px dashed ${C.amber}`, borderRadius: 6, padding: "3px 10px",
          background: "rgba(6,10,20,0.85)",
          opacity: ramp(t, T.neighbour - 0.2, T.neighbour + 0.4) * (1 - ramp(t, T.out - 1.2, T.out - 0.7)),
        }}
      >
        DESIGN PREVIEW · live build opens one case per report
      </div>

      {/* ---- title ---- */}
      <div
        style={{
          position: "absolute", left: 0, right: 0, top: 70, textAlign: "center", textShadow: "0 4px 30px rgba(6,10,20,0.95), 0 0 12px rgba(6,10,20,0.9)",
          opacity: ramp(t, T.panchayat, T.panchayat + 0.5) * (1 - ramp(t, T.out - 1.2, T.out - 0.6)),
          transform: `translateY(${(1 - eased(t, T.panchayat, T.panchayat + 0.6)) * 20}px)`,
        }}
      >
        <div style={{ fontFamily: SANS, fontWeight: 800, fontSize: 76, color: C.ink, letterSpacing: -1 }}>
          <span style={{ fontFamily: KANNADA, fontWeight: 700, color: C.amber, fontSize: 54, marginRight: 22 }}>ಪಂಚಾಯತ್</span>
          Panchayat
        </div>
        <div style={{ fontFamily: SANS, fontWeight: 500, fontSize: 30, color: C.dim, opacity: ramp(t, T.agents - 0.5, T.agents) }}>
          a neighbourhood of agents
        </div>
      </div>

      {/* ---- place caption ---- */}
      <div style={{ position: "absolute", left: 80, bottom: 64, fontFamily: MONO, fontSize: 18, letterSpacing: 2, color: C.dim, opacity: ramp(t, 5.4, 6.2) * (1 - ramp(t, T.stamina - 0.5, T.stamina)) }}>
        WARD 12 · BENGALURU
      </div>
    </AbsoluteFill>
  );
};
