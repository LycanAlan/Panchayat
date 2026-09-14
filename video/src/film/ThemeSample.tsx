import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";
import { KANNADA, MONO, P, PaperGlow, SANS, SERIF, Streak, eased, lerp, ramp, settle } from "./kit";

const Icon: React.FC<{ kind: string; color: string }> = ({ kind, color }) => {
  const s = { stroke: color, strokeWidth: 2.2, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg width={34} height={34} viewBox="0 0 24 24">
      {kind === "hospital" && <><rect x="3" y="3" width="18" height="18" rx="3" {...s} /><path d="M12 7v10M7 12h10" {...s} /></>}
      {kind === "power" && <path d="M13 2 4 14h7l-1 8 9-12h-7z" {...s} />}
      {kind === "school" && <><path d="M2 9l10-5 10 5-10 5z" {...s} /><path d="M6 11v5c3 2 9 2 12 0v-5" {...s} /></>}
      {kind === "bank" && <><path d="M3 9l9-5 9 5" {...s} /><path d="M5 10v8M10 10v8M14 10v8M19 10v8M3 20h18" {...s} /></>}
      {kind === "road" && <><path d="M8 3 5 21M16 3l3 18" {...s} /><ellipse cx="12" cy="13" rx="3" ry="1.6" {...s} /></>}
      {kind === "water" && <><path d="M12 3s6 7 6 11a6 6 0 0 1-12 0c0-4 6-11 6-11z" {...s} /></>}
    </svg>
  );
};

const SLIPS = [
  { kind: "hospital", office: "GOVT HOSPITAL · OPD", issue: "Six hours, no doctor on duty", ref: "GRV-58201", note: "Day 3: same queue", x: -560, y: -250, r: -3 },
  { kind: "power", office: "ELECTRICITY BOARD", issue: "Power cut, two days", ref: "ELC-20417", note: "Day 2: still dark", x: 0, y: -280, r: 2 },
  { kind: "school", office: "EDUCATION OFFICE", issue: "Scholarship not credited", ref: "EDU-09133", note: "Month 5: nothing", x: 560, y: -240, r: -2 },
  { kind: "bank", office: "BANK GRIEVANCE CELL", issue: "Wrong charge, no refund", ref: "BNK-77310", note: "Week 6: no reply", x: -560, y: 170, r: 2.5 },
  { kind: "road", office: "MUNICIPALITY", issue: "Pothole on Main Road", ref: "MUN-31982", note: "Closed 15 times", x: 0, y: 200, r: -1.5 },
  { kind: "water", office: "WATER BOARD", issue: "No water for three days", ref: "WTR-45210", note: "Day 9: taps still dry", x: 560, y: 160, r: 3 },
];

const Slip: React.FC<{ t: number; i: number }> = ({ t, i }) => {
  const s = SLIPS[i];
  const inAt = 0.1 + i * 0.12;
  const k = settle(t, inAt, 0.55);
  const stampAt = 1.25 + i * 0.13;
  const stamp = ramp(t, stampAt, stampAt + 0.18);
  const noteAt = 2.25 + i * 0.1;
  return (
    <div
      style={{
        position: "absolute", left: 960 + s.x - 240, top: 540 + s.y - 115, width: 480, height: 230,
        transform: `translateY(${(1 - k) * -90}px) rotate(${s.r}deg) scale(${lerp(0.9, 1, k)})`, opacity: ramp(t, inAt, inAt + 0.15),
      }}
    >
      <div
        style={{
          width: "100%", height: "100%", background: "#fffdf8", border: `1px solid ${P.rule}`, borderRadius: 6, padding: "22px 26px",
          boxShadow: "0 18px 40px rgba(60,40,10,0.10), 0 2px 6px rgba(60,40,10,0.06)", boxSizing: "border-box", position: "relative",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Icon kind={s.kind} color={P.indigo} />
            <span style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 2, color: P.muted }}>{s.office}</span>
          </div>
          <span style={{ fontFamily: MONO, fontSize: 14, color: P.faint }}>{s.ref}</span>
        </div>
        <div style={{ fontFamily: SERIF, fontSize: 36, color: P.ink, marginTop: 22, letterSpacing: -0.5 }}>{s.issue}</div>
        <div style={{ height: 1, background: P.rule, marginTop: 20 }} />
        <div style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 25, color: P.terracotta, marginTop: 12, opacity: ramp(t, noteAt, noteAt + 0.3) }}>
          {s.note}
        </div>
        {stamp > 0 ? (
          <div
            style={{
              position: "absolute", right: 18, bottom: 14, transform: `rotate(-7deg) scale(${lerp(2.6, 1, stamp)})`, opacity: stamp,
              filter: `blur(${(1 - stamp) * 6}px)`, fontFamily: MONO, fontWeight: 500, fontSize: 22, letterSpacing: 3, color: P.sage,
              border: `3px solid ${P.sage}`, borderRadius: 6, padding: "4px 12px", background: "rgba(251,247,239,0.85)",
            }}
          >
            CLOSED · RESOLVED
          </div>
        ) : null}
      </div>
    </div>
  );
};

export const ThemeSample: React.FC = () => {
  const t = useCurrentFrame() / 30;

  // ---- 1. complaint slips, stamped closed, still broken
  const whip1 = eased(t, 3.3, 3.95);
  const shake = t > 1.25 && t < 2.1 ? Math.sin(t * 90) * 2.2 * (1 - ramp(t, 1.25, 2.1)) : 0;

  // ---- 2. the site's own headline, arriving word by word
  const punch = ramp(t, 3.8, 4.25);
  const closedToLine = eased(t, 4.9, 5.6);
  const words = ["A", "complaint", "closed", "is", "not", "a", "problem", "fixed."];
  const whip2 = eased(t, 7.0, 7.55);

  // ---- 3. Meet Panchayat
  const meetIn = (i: number) => ramp(t, 7.45 + i * 0.07, 7.8 + i * 0.07);
  const meetShift = eased(t, 8.35, 8.95);
  const bloom = eased(t, 8.4, 10.2);
  const toUI = eased(t, 10.0, 10.55);

  // ---- 4. the real website, floating
  const ui = eased(t, 10.1, 10.9);
  const sweep = ramp(t, 10.6, 12.2);
  const checks = [
    { at: 10.9, agent: "Intake", what: "read back what it heard" },
    { at: 11.45, agent: "Remedy", what: "BWSSB Assistant Engineer, cited" },
    { at: 12.0, agent: "Digest", what: "signed by a named member" },
    { at: 12.55, agent: "BWSSB desk", what: "ticket BWSSB-100004" },
  ];

  return (
    <AbsoluteFill style={{ background: P.paper, overflow: "hidden" }}>
      <PaperGlow t={t} warmth={lerp(0.85, 1.35, bloom) - 0.25 * ramp(t, 10.6, 12)} />

      {t < 4.1 ? (
        <AbsoluteFill
          style={{
            transform: `translate(${shake}px, ${shake * 0.6}px) scale(${lerp(1, 1.04, ramp(t, 0, 3.3)) * lerp(1, 2.8, whip1)})`,
            filter: `blur(${whip1 * 26}px)`, opacity: 1 - ramp(t, 3.6, 4.0),
          }}
        >
          {SLIPS.map((_, i) => <Slip key={i} t={t} i={i} />)}
        </AbsoluteFill>
      ) : null}

      {t >= 3.8 && t < 7.7 ? (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", transform: `scale(${lerp(1, 2.4, whip2)})`, filter: `blur(${whip2 * 22}px)`, opacity: 1 - ramp(t, 7.3, 7.6) }}>
          <div style={{ width: 1500, position: "relative", height: 420 }}>
            <div
              style={{
                position: "absolute", left: 0, right: 0, top: lerp(90, 60, closedToLine), textAlign: "center", fontFamily: SERIF, color: P.ink,
                fontSize: lerp(300, 118, closedToLine), letterSpacing: lerp(-9, -3.5, closedToLine), lineHeight: 1,
                transform: `scale(${lerp(2.2, 1, punch)})`, opacity: punch * (1 - ramp(t, 5.45, 5.65)),
              }}
            >
              <Streak amount={(1 - punch) * 120}>closed.</Streak>
            </div>
            <div style={{ position: "absolute", left: 0, right: 0, top: 60, textAlign: "center", fontFamily: SERIF, fontSize: 118, lineHeight: 1.08, letterSpacing: -3.5, color: P.ink }}>
              {words.map((w, i) => {
                const at = i === 2 ? 5.45 : 5.4 + (i < 2 ? i : i - 1) * 0.16;
                const k = ramp(t, at, at + 0.35);
                const last = w === "fixed.";
                return (
                  <React.Fragment key={i}>
                    <span
                      style={{
                        display: "inline-block", opacity: k, transform: `translateY(${(1 - k) * 26}px)`, filter: `blur(${(1 - k) * 8}px)`,
                        fontStyle: last ? "italic" : "normal", color: last ? P.terracotta : P.ink, position: "relative",
                      }}
                    >
                      {last ? (
                        <span
                          style={{
                            position: "absolute", left: -8, right: -8, bottom: 14, height: 34, background: P.marigold, opacity: 0.32,
                            transformOrigin: "left", transform: `scaleX(${eased(t, 6.55, 7.0)})`, borderRadius: 3,
                          }}
                        />
                      ) : null}
                      <span style={{ position: "relative" }}>{w}</span>
                    </span>
                    {i === 2 ? <br /> : " "}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
        </AbsoluteFill>
      ) : null}

      {t >= 7.4 && t < 10.6 ? (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", transform: `translateY(${-toUI * 180}px)`, opacity: 1 - toUI }}>
          <div style={{ position: "relative", textAlign: "center" }}>
            <div style={{ fontFamily: KANNADA, fontSize: 44, color: P.marigold, opacity: ramp(t, 8.9, 9.4), marginBottom: 6 }}>ಪಂಚಾಯತ್</div>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "center", fontFamily: SERIF, color: P.ink, letterSpacing: -6 }}>
              <div style={{ display: "flex", fontSize: lerp(280, 150, meetShift) }}>
                {"Meet".split("").map((ch, i) => (
                  <Streak key={i} amount={(1 - meetIn(i)) * 160} style={{ opacity: meetIn(i), transform: `translateY(${(1 - meetIn(i)) * 120}px)` }}>
                    {ch}
                  </Streak>
                ))}
              </div>
              <div
                style={{
                  fontSize: 150, fontStyle: "italic", color: P.indigo, marginLeft: 34 * meetShift, maxWidth: meetShift * 760, overflow: "hidden",
                  whiteSpace: "nowrap", opacity: ramp(t, 8.5, 8.9),
                }}
              >
                Panchayat
              </div>
            </div>
            <div style={{ fontFamily: SANS, fontSize: 30, color: P.muted, marginTop: 18, opacity: ramp(t, 9.2, 9.6), letterSpacing: 0.3 }}>
              the agents that stay on the case
            </div>
          </div>
        </AbsoluteFill>
      ) : null}

      {t >= 10.1 ? (
        <AbsoluteFill>
          <div style={{ position: "absolute", left: 90, top: 150, perspective: 2200 }}>
            <div
              style={{
                width: 1120, height: 700, borderRadius: 14, overflow: "hidden", position: "relative",
                transform: `translateY(${(1 - ui) * 160}px) rotateX(${lerp(24, 10, ui) + ramp(t, 10.9, 13) * -2}deg) rotateY(${lerp(-26, -14, ui) + ramp(t, 10.9, 13) * 3}deg)`,
                boxShadow: "0 50px 90px rgba(60,40,10,0.22), 0 0 0 1px rgba(60,40,10,0.08)", opacity: ui,
              }}
            >
              <Img src={staticFile("site/home.png")} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "top" }} />
              <div
                style={{
                  position: "absolute", inset: 0,
                  background: `linear-gradient(105deg, transparent ${lerp(-40, 110, sweep) - 18}%, rgba(255,236,200,0.55) ${lerp(-40, 110, sweep)}%, transparent ${lerp(-40, 110, sweep) + 18}%)`,
                }}
              />
            </div>
          </div>
          <div
            style={{
              position: "absolute", right: 110, top: 300, width: 560, background: "#fffdf8", border: `1px solid ${P.rule}`, borderRadius: 12,
              padding: "26px 30px", boxShadow: "0 30px 60px rgba(60,40,10,0.14)", opacity: ramp(t, 10.5, 10.9), transform: `translateX(${(1 - eased(t, 10.5, 11)) * 60}px)`,
            }}
          >
            <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 2.5, color: P.muted }}>CASE · WARD 12 · NO WATER</div>
            {checks.map((c) => {
              const k = ramp(t, c.at, c.at + 0.25);
              return (
                <div key={c.agent} style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 22, opacity: lerp(0.28, 1, k) }}>
                  <div style={{ width: 30, height: 30, borderRadius: 15, border: `2px solid ${k > 0.5 ? P.sage : P.ruleStrong}`, background: k > 0.5 ? P.sage : "transparent", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    {k > 0.5 ? <svg width="16" height="16" viewBox="0 0 16 16"><path d="M3 8.5l3 3 7-7" stroke="#fffdf8" strokeWidth="2.4" fill="none" strokeLinecap="round" /></svg> : null}
                  </div>
                  <div>
                    <div style={{ fontFamily: SANS, fontWeight: 600, fontSize: 22, color: P.ink }}>{c.agent}</div>
                    <div style={{ fontFamily: SERIF, fontSize: 22, color: P.muted }}>{c.what}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
