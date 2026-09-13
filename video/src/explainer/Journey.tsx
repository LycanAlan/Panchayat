import React from "react";
import { AbsoluteFill } from "remotion";
import { getLength, getPointAtLength } from "@remotion/paths";
import { C, KANNADA, MONO, SANS, eased, keyframes, lerp, popIn, ramp, sent, wordAt } from "./core";

type Cloud = { id: string; name: string; x: number; y: number; line: string; infra: string; start: number };

const CLOUDS: Cloud[] = [
  { id: "intake", name: "Intake", x: 330, y: 250, line: "Reads back what it heard", infra: "Strands Graph · AgentCore Runtime", start: sent(11).start },
  { id: "household", name: "Household", x: 960, y: 250, line: "One home, one position", infra: "Strands Swarm inside one home", start: sent(12).start },
  { id: "warden", name: "Privacy Warden", x: 1590, y: 250, line: "Urgency crosses. Reasons don't.", infra: "the membrane", start: sent(13).start },
  { id: "remedy", name: "Remedy", x: 1590, y: 560, line: "Looks up the office, cites the rule", infra: "curated jurisdiction table", start: sent(14).start },
  { id: "digest", name: "Digest", x: 960, y: 560, line: "A named person signs", infra: "agents draft, humans sign", start: sent(16).start },
  { id: "desk", name: "BWSSB desk", x: 330, y: 560, line: "Issues a ticket", infra: "A2A · own process · simulator", start: sent(17).start },
  { id: "watchdog", name: "Watchdog", x: 330, y: 870, line: "Holds the statutory clock", infra: "EventBridge Scheduler → Lambda", start: sent(18).start },
  { id: "closure", name: "Closure check", x: 960, y: 870, line: "The street can dispute a close", infra: "check_closure · live claims", start: sent(20).start },
];

const PATH = "M 80 250 L 1590 250 C 1860 250 1860 560 1590 560 L 330 560 C 60 560 60 870 330 870 L 1760 870";
const TOTAL = getLength(PATH);
const TURN1 = getLength("M 1590 250 C 1860 250 1860 560 1590 560");
const TURN2 = getLength("M 330 560 C 60 560 60 870 330 870");
const STOP = [250, 880, 1510, 1510 + TURN1, 1510 + TURN1 + 630, 1510 + TURN1 + 1260, 1510 + TURN1 + 1260 + TURN2, 1510 + TURN1 + 1260 + TURN2 + 630];

const W = {
  strands: wordAt(10, "STRANDS"),
  reason: wordAt(13, "REASON"),
  cites: wordAt(14, "CITES"),
  guesses: sent(15).start,
  signs: wordAt(16, "SIGNS"),
  ticket: wordAt(17, "TICKET"),
  deadline: wordAt(19, "DEADLINE"),
  climbs: wordAt(19, "CLIMBS"),
  resolved: wordAt(20, "RESOLVED"),
  dry: wordAt(20, "DRY"),
  dispute: wordAt(20, "DISPUTE"),
  end: sent(21).start,
  begin: sent(10).start,
};

const leaveAt = (k: number) => (k + 1 < CLOUDS.length ? CLOUDS[k + 1].start - 1.25 : W.end - 0.9);

function tokenDistance(t: number): number {
  const keys: [number, number][] = [
    [W.begin + 0.2, 0],
    [CLOUDS[0].start - 0.25, STOP[0]],
  ];
  for (let k = 1; k < CLOUDS.length; k++) {
    keys.push([CLOUDS[k].start - 1.25, STOP[k - 1]]);
    keys.push([CLOUDS[k].start - 0.2, STOP[k]]);
  }
  keys.push([W.end - 0.9, STOP[STOP.length - 1]]);
  keys.push([W.end + 0.4, TOTAL - 170]);
  return keyframes(t, keys);
}

const CloudShape: React.FC<{ fill: string; glow: string; glowOpacity: number }> = ({ fill, glow, glowOpacity }) => {
  const bumps = [
    [-62, 8, 50],
    [0, -22, 70],
    [62, 4, 54],
    [-26, 22, 46],
    [30, 24, 46],
    [-102, 30, 34],
    [102, 30, 34],
  ];
  const shape = (color: string) => (
    <>
      {bumps.map(([x, y, r], i) => (
        <circle key={i} cx={x} cy={y} r={r} fill={color} />
      ))}
      <rect x={-130} y={18} width={260} height={48} rx={24} fill={color} />
    </>
  );
  return (
    <>
      <g opacity={glowOpacity} filter="url(#cloudGlow)">{shape(glow)}</g>
      {shape(fill)}
    </>
  );
};

const Check: React.FC<{ s: number }> = ({ s }) => (
  <g transform={`translate(112 -52) scale(${s})`}>
    <circle r={17} fill={C.green} />
    <path d="M -8 0 L -2 7 L 9 -6" stroke="#06140d" strokeWidth={3.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />
  </g>
);

const Line: React.FC<{ o: number; children: React.ReactNode; style?: React.CSSProperties }> = ({ o, children, style }) =>
  o > 0.01 ? <div style={{ opacity: o, marginTop: 8, ...style }}>{children}</div> : null;

const TokenCard: React.FC<{ t: number; active: number }> = ({ t, active }) => {
  const stageOpacity = (k: number) => (active === k ? ramp(t, CLOUDS[k].start - 0.2, CLOUDS[k].start + 0.25) * (1 - ramp(t, leaveAt(k), leaveAt(k) + 0.3)) : 0);
  const trail = [
    { k: 0, label: "read back" },
    { k: 1, label: "one position" },
    { k: 2, label: "reason withheld" },
    { k: 3, label: "BWSSB AE · cited" },
    { k: 4, label: "signed" },
    { k: 5, label: "BWSSB-100004" },
    { k: 6, label: "tier 2" },
  ].filter((x) => t > leaveAt(x.k));

  const warden = stageOpacity(2);
  const blur = 10 * ramp(t, W.reason - 0.5, W.reason + 0.3);
  const days = 1 + Math.floor(6 * ramp(t, CLOUDS[6].start + 0.3, W.deadline));

  return (
    <div style={{ width: 450, padding: "16px 22px", borderRadius: 16, background: "#0d1321", border: `2.5px solid ${C.indigo}`, boxShadow: `0 0 50px ${C.indigo}50`, fontFamily: SANS }}>
      <div style={{ fontFamily: MONO, fontSize: 14, letterSpacing: 2, color: C.indigo }}>CASE · WARD 12</div>
      <div style={{ fontWeight: 700, fontSize: 30, color: C.ink }}>No water</div>
      <div style={{ fontWeight: 500, fontSize: 19, color: C.amber }}>12 households · 4th Cross</div>

      {/* intake */}
      <Line o={stageOpacity(0)}>
        <div style={{ fontFamily: KANNADA, fontSize: 22, color: C.ink }}>ಮೂರು ದಿನದಿಂದ ನೀರು ಬಂದಿಲ್ಲ</div>
        <div style={{ fontSize: 18, color: C.dim, fontStyle: "italic", whiteSpace: "nowrap" }}>
          “I understood: no water, third day?”{" "}
          <span style={{ color: C.green, fontStyle: "normal", fontWeight: 700, opacity: ramp(t, CLOUDS[0].start + 2.2, CLOUDS[0].start + 2.5) }}>✓ yes</span>
        </div>
      </Line>

      {/* household */}
      <Line o={stageOpacity(1)}>
        <div style={{ display: "flex", gap: 6, height: 30, alignItems: "center", position: "relative" }}>
          {["father", "mother", "grandmother"].map((m, i) => {
            const k = eased(t, CLOUDS[1].start + 0.6, CLOUDS[1].start + 1.4);
            return (
              <span key={m} style={{ fontSize: 15, padding: "2px 9px", borderRadius: 7, border: `1.5px solid ${C.amber}`, color: C.ink, transform: `translateX(${-k * i * 78}px)`, opacity: 1 - k }}>
                {m}
              </span>
            );
          })}
          <span style={{ position: "absolute", left: 0, fontSize: 18, fontWeight: 600, color: C.ink, opacity: ramp(t, CLOUDS[1].start + 1.2, CLOUDS[1].start + 1.6) }}>
            one household position
          </span>
        </div>
      </Line>

      {/* warden */}
      <Line o={warden} style={{ position: "relative", height: 34 }}>
        <div style={{ position: "absolute", fontSize: 21, fontWeight: 600, color: C.red, filter: `blur(${blur}px)`, opacity: 1 - ramp(t, W.reason + 0.1, W.reason + 0.5) }}>
          Dialysis on Thursday
        </div>
        <div style={{ position: "absolute", fontSize: 21, fontWeight: 700, color: C.amber, opacity: ramp(t, W.reason + 0.2, W.reason + 0.6) }}>
          HIGH priority · reason withheld
        </div>
      </Line>

      {/* remedy */}
      <Line o={stageOpacity(3)}>
        <div style={{ fontSize: 19, fontWeight: 600, color: C.ink }}>→ BWSSB Assistant Engineer, sub-division office</div>
        <div style={{ fontFamily: MONO, fontSize: 13, color: C.indigo, marginTop: 4, opacity: ramp(t, W.cites - 0.1, W.cites + 0.3) }}>
          cited: BWSSB Citizen Charter, restoration of interrupted supply
        </div>
        <div style={{ fontFamily: MONO, fontSize: 13, color: C.green, marginTop: 4, opacity: ramp(t, W.guesses - 0.1, W.guesses + 0.3) }}>looked up · never generated</div>
      </Line>

      {/* digest */}
      <Line o={stageOpacity(4)}>
        <div style={{ fontSize: 18, color: C.dim }}>Draft ready. Nothing leaves unsigned.</div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, opacity: ramp(t, W.signs - 0.3, W.signs) }}>
          <svg width={96} height={34} viewBox="0 0 120 40">
            <path
              d="M 4 28 C 14 6 22 36 32 18 C 40 4 46 34 58 20 C 66 10 72 30 84 16 C 92 8 102 24 116 12"
              stroke={C.ink}
              strokeWidth={2.6}
              fill="none"
              strokeDasharray={260}
              strokeDashoffset={260 * (1 - ramp(t, W.signs - 0.2, W.signs + 0.6))}
            />
          </svg>
          <span style={{ fontSize: 17, fontWeight: 600, color: C.green, whiteSpace: "nowrap" }}>signed by a named member</span>
        </div>
      </Line>

      {/* desk */}
      <Line o={stageOpacity(5)}>
        <div style={{ fontSize: 18, color: C.dim }}>Filed agent to agent…</div>
        <div style={{ fontFamily: MONO, fontSize: 30, fontWeight: 600, color: C.green, transform: `scale(${popIn(t, W.ticket, 0.4)})`, transformOrigin: "left center" }}>
          Ticket BWSSB-100004
        </div>
      </Line>

      {/* watchdog */}
      <Line o={stageOpacity(6)}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <span style={{ fontSize: 18, color: C.dim }}>7-day window</span>
          <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 600, color: t >= W.deadline ? C.red : C.ink }}>
            {t >= W.deadline ? "BREACHED" : `day ${days}/7`}
          </span>
        </div>
        <div style={{ fontSize: 19, fontWeight: 600, color: C.amber, opacity: ramp(t, W.climbs - 0.2, W.climbs + 0.2) }}>
          Tier 2 → Assistant Executive Engineer
        </div>
      </Line>

      {/* closure */}
      <Line o={stageOpacity(7)}>
        <div style={{ fontSize: 19, color: C.dim, opacity: ramp(t, W.resolved - 0.2, W.resolved + 0.2) }}>
          Desk says: <span style={{ color: C.green, fontWeight: 700 }}>RESOLVED</span>
        </div>
        <div style={{ fontSize: 19, fontWeight: 600, color: C.red, opacity: ramp(t, W.dry - 0.2, W.dry + 0.2) }}>9 new reports: taps still dry</div>
        <div
          style={{
            display: "inline-block", marginTop: 6, fontFamily: MONO, fontSize: 24, fontWeight: 600, color: C.red, border: `2.5px solid ${C.red}`, borderRadius: 6, padding: "2px 10px",
            transform: `rotate(-4deg) scale(${popIn(t, W.dispute, 0.35)})`,
          }}
        >
          DISPUTED · REOPENED
        </div>
      </Line>

      {trail.length ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 10 }}>
          {trail.map((x) => (
            <span key={x.k} style={{ fontFamily: MONO, fontSize: 11, color: C.green, border: `1px solid ${C.green}66`, borderRadius: 5, padding: "1px 6px", opacity: ramp(t, leaveAt(x.k), leaveAt(x.k) + 0.4) }}>
              ✓ {x.label}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
};

export const Journey: React.FC<{ t: number }> = ({ t }) => {
  const dist = tokenDistance(t);
  const tok = getPointAtLength(PATH, Math.max(0, Math.min(TOTAL, dist)));
  let active = -1;
  CLOUDS.forEach((c, k) => {
    if (t >= c.start - 0.25) active = k;
  });

  const follow = eased(t, CLOUDS[0].start - 1.0, CLOUDS[0].start + 0.1) * (1 - eased(t, W.end - 0.3, W.end + 1.0));
  const s = Math.exp(lerp(Math.log(0.9), Math.log(1.55), follow));
  const halfW = 960 / s;
  const halfH = 540 / s;
  const fx = Math.min(Math.max(tok.x + 40, halfW - 60), 1920 - halfW + 60);
  const fy = Math.min(Math.max(tok.y - 90, halfH - 90), 1080 - halfH + 190);
  const nearStop = Math.min(...STOP.map((d) => Math.abs(dist - d)));
  const dotOpacity = ramp(nearStop, 30, 110);
  const cx = lerp(960, fx, follow);
  const cy = lerp(560, fy, follow);

  const drawn = eased(t, W.begin + 0.1, W.begin + 4.2);
  const sceneOpacity = ramp(t, W.begin - 0.6, W.begin + 0.2);

  return (
    <AbsoluteFill style={{ opacity: sceneOpacity, background: `radial-gradient(ellipse at 50% 45%, #0c1430 0%, ${C.bg} 72%)` }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: 1920, height: 1080, transformOrigin: "0 0", transform: `translate(${960 - s * cx}px, ${540 - s * cy}px) scale(${s})` }}>
        <svg width={1920} height={1080} style={{ position: "absolute", overflow: "visible" }}>
          <defs>
            <filter id="cloudGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="18" />
            </filter>
          </defs>
          <path d={PATH} stroke="#1c2540" strokeWidth={10} fill="none" strokeLinecap="round" strokeDasharray={TOTAL} strokeDashoffset={TOTAL * (1 - drawn)} />
          <path d={PATH} stroke={C.indigo} strokeWidth={5} fill="none" strokeLinecap="round" strokeDasharray={`${Math.max(0, dist)} ${TOTAL}`} opacity={0.9} />

          {/* A2A: the desk is someone else's process with its own state */}
          <g opacity={ramp(t, CLOUDS[4].start + 1, CLOUDS[4].start + 1.8)}>
            <line x1={645} y1={430} x2={645} y2={690} stroke={C.dim} strokeWidth={2} strokeDasharray="8 8" />
          </g>

          {CLOUDS.map((c, k) => {
            const appear = popIn(t, W.begin + 0.5 + k * 0.42, 0.5);
            const on = active === k && t < leaveAt(k) + 0.3;
            const done = t > leaveAt(k) + 0.1 && k <= active;
            const glow = on ? 0.55 + 0.1 * Math.sin(t * 5) : 0;
            return (
              <g key={c.id} transform={`translate(${c.x} ${c.y}) scale(${appear * (on ? 1.08 : 1)})`}>
                <CloudShape fill={on ? "#1d2a52" : done ? "#142038" : "#111a2e"} glow={C.indigo} glowOpacity={glow} />
                {done ? <Check s={popIn(t, leaveAt(k) + 0.1, 0.35)} /> : null}
              </g>
            );
          })}

          {/* Watchdog clock ring */}
          {(() => {
            const k = 6;
            const o = active === k ? ramp(t, CLOUDS[k].start, CLOUDS[k].start + 0.3) * (1 - ramp(t, leaveAt(k), leaveAt(k) + 0.3)) : 0;
            const p = ramp(t, CLOUDS[k].start + 0.3, W.deadline);
            const r = 150;
            const circ = 2 * Math.PI * r;
            return o > 0 ? (
              <g opacity={o} transform={`translate(${CLOUDS[k].x} ${CLOUDS[k].y}) rotate(-90)`}>
                <circle r={r} stroke="#233052" strokeWidth={8} fill="none" />
                <circle r={r} stroke={t >= W.deadline ? C.red : C.amber} strokeWidth={8} fill="none" strokeDasharray={`${circ * p} ${circ}`} strokeLinecap="round" />
              </g>
            ) : null;
          })()}

          {/* The street answers the closure */}
          {Array.from({ length: 9 }).map((_, i) => {
            const a = (i / 9) * Math.PI * 2 - Math.PI / 2;
            const x = CLOUDS[7].x + Math.cos(a) * 230;
            const y = CLOUDS[7].y + Math.sin(a) * 150;
            const s2 = popIn(t, W.dry + i * 0.07, 0.3) * (1 - ramp(t, W.end + 0.2, W.end + 0.8));
            return s2 > 0 ? (
              <g key={i}>
                <line x1={x} y1={y} x2={CLOUDS[7].x} y2={CLOUDS[7].y} stroke={C.red} strokeWidth={1.5} opacity={0.35 * Math.min(1, s2)} strokeDasharray="4 5" />
                <circle cx={x} cy={y} r={11 * s2} fill={C.red} />
              </g>
            ) : null;
          })}
        </svg>

        {CLOUDS.map((c, k) => {
          const appear = ramp(t, W.begin + 0.7 + k * 0.42, W.begin + 1.1 + k * 0.42);
          const on = active === k && t < leaveAt(k) + 0.3;
          return (
            <React.Fragment key={c.id}>
              <div style={{ position: "absolute", left: c.x - 150, top: c.y - 14, width: 300, textAlign: "center", fontFamily: SANS, fontWeight: 700, fontSize: 27, color: on ? C.ink : "#c9cfdd", opacity: appear }}>
                {c.name}
              </div>
              <div style={{ position: "absolute", left: c.x - 190, top: c.y + 82, width: 380, textAlign: "center", opacity: appear }}>
                <div style={{ fontFamily: SANS, fontWeight: 500, fontSize: 19, color: C.dim }}>{c.line}</div>
                <div style={{ display: "inline-block", marginTop: 6, fontFamily: MONO, fontSize: 13, color: C.indigo, background: "rgba(123,147,255,0.10)", borderRadius: 6, padding: "2px 8px" }}>{c.infra}</div>
              </div>
            </React.Fragment>
          );
        })}

        <div style={{ position: "absolute", left: 645 - 110, top: 700, width: 220, textAlign: "center", fontFamily: MONO, fontSize: 13, color: C.dim, opacity: ramp(t, CLOUDS[4].start + 1, CLOUDS[4].start + 1.8) }}>
          A2A boundary
          <br />
          the desk keeps its own state
        </div>

        <div style={{ position: "absolute", left: tok.x, top: tok.y - 118, transform: `translate(-50%, -100%) scale(${ramp(t, W.begin - 0.2, W.begin + 0.4)})`, transformOrigin: "50% 100%" }}>
          <TokenCard t={t} active={active} />
        </div>
        <div style={{ position: "absolute", left: tok.x - 11, top: tok.y - 11, width: 22, height: 22, borderRadius: 11, background: C.indigo, boxShadow: `0 0 24px ${C.indigo}`, opacity: dotOpacity }} />
      </div>

      <div
        style={{
          position: "absolute", left: 0, right: 0, top: 40, textAlign: "center", fontFamily: MONO, fontSize: 22, letterSpacing: 3, color: C.dim,
          opacity: ramp(t, W.strands - 0.3, W.strands + 0.2) * (1 - ramp(t, CLOUDS[0].start - 0.6, CLOUDS[0].start)),
        }}
      >
        BUILT ON <span style={{ color: C.ink }}>STRANDS AGENTS</span> · <span style={{ color: C.ink }}>AMAZON BEDROCK AGENTCORE</span>
      </div>
      <div style={{ position: "absolute", left: 40, bottom: 30, fontFamily: MONO, fontSize: 15, letterSpacing: 2, color: C.faint, opacity: ramp(t, CLOUDS[0].start, CLOUDS[0].start + 0.6) }}>
        STRANDS AGENTS · AGENTCORE RUNTIME · A2A · EVENTBRIDGE · DYNAMODB
      </div>
    </AbsoluteFill>
  );
};
