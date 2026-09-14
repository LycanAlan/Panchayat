import React from "react";
import { AbsoluteFill } from "remotion";
import { KANNADA, MONO, P, SANS, SERIF, eased, lerp, ramp, settle } from "./kit";
import { Check, Em, Headline, MERGE_IS_LIVE, Mono, Paper, S, Spoken, Stage, Stamp, VO_END, W } from "./kit2";
import { Icon } from "./Part1";

// ------------------------------------------------------------ 7. when nobody is asking

const LADDER = [
  { tier: 1, who: "BWSSB Assistant Engineer", note: "filed" },
  { tier: 2, who: "Assistant Executive Engineer", note: "escalation drafted" },
  { tier: 3, who: "Sakala Competent Officer", note: "statutory appeal" },
  { tier: 4, who: "RTI application", note: "drafted, never auto-filed" },
];

const HOUSES = Array.from({ length: 12 }).map((_, k) => ({
  x: 250 + k * 128,
  h: [130, 160, 118, 150, 172, 124, 145, 162, 120, 155, 138, 168][k],
  main: [0, 2, 3, 5, 7, 8, 10].includes(k) ? "A" : "B",
}));
const A_HOUSES = HOUSES.map((h, k) => ({ ...h, k })).filter((h) => h.main === "A");
const DECOY = 4;
const GROUND = 820;
const MAIN_A = 900;
const MAIN_B = 960;

const Street: React.FC<{ t: number }> = ({ t }) => {
  const reportAt = (j: number) => W(30, "NEIGHBOURS") + j * 0.22;
  const joinAt = (j: number) => W(30, "JOINS") + j * 0.14;
  const arrived = A_HOUSES.filter((_, j) => j > 0 && t > joinAt(j) + 0.5).length;
  const card = { x: 960, y: 300 };
  const decoyStart = S(31).start + 0.2;
  const decoyFly = eased(t, decoyStart, decoyStart + 0.9);
  const decoyBack = eased(t, W(31, "LINE") + 0.3, W(31, "LINE") + 1.0);
  const checks = [
    { at: W(31, "REAL"), text: "Registered flat" },
    { at: W(31, "CONSENTED"), text: "Has consented" },
    { at: W(31, "LINE"), text: "On the same water line" },
  ];
  return (
    <>
      <svg width={1920} height={1080} style={{ position: "absolute" }}>
        <line x1={180} x2={1740} y1={GROUND} y2={GROUND} stroke={P.ink} strokeWidth={2} />
        <line x1={180} x2={1740} y1={MAIN_A} y2={MAIN_A} stroke={P.marigold} strokeWidth={6} />
        <line x1={180} x2={1740} y1={MAIN_B} y2={MAIN_B} stroke={P.indigo} strokeWidth={4} strokeDasharray="14 8" />
        <text x={1750} y={MAIN_A + 6} fontFamily={MONO} fontSize={16} fill={P.marigold} letterSpacing={2}>MAIN A</text>
        <text x={1750} y={MAIN_B + 6} fontFamily={MONO} fontSize={16} fill={P.indigo} letterSpacing={2}>MAIN B</text>
        {HOUSES.map((h, k) => {
          const pipeY = h.main === "A" ? MAIN_A : MAIN_B;
          const a = ramp(t, S(30).start - 0.2 + k * 0.05, S(30).start + 0.2 + k * 0.05);
          return (
            <g key={k} opacity={a}>
              <line x1={h.x + 40} x2={h.x + 40} y1={GROUND} y2={pipeY} stroke={h.main === "A" ? P.marigold : P.indigo} strokeWidth={2} strokeDasharray="4 4" />
              <circle cx={h.x + 40} cy={pipeY} r={5} fill={h.main === "A" ? P.marigold : P.indigo} />
              <rect x={h.x} y={GROUND - h.h} width={80} height={h.h} fill="#fffdf8" stroke={P.ink} strokeWidth={1.8} />
              <path d={`M${h.x - 6} ${GROUND - h.h} L${h.x + 40} ${GROUND - h.h - 26} L${h.x + 86} ${GROUND - h.h} Z`} fill="#fffdf8" stroke={P.ink} strokeWidth={1.8} />
              <rect x={h.x + 16} y={GROUND - h.h + 22} width={16} height={16} fill="none" stroke={P.muted} strokeWidth={1.4} />
              <rect x={h.x + 48} y={GROUND - 36} width={16} height={36} fill="none" stroke={P.muted} strokeWidth={1.4} />
              <text x={h.x + 30} y={GROUND + 26} fontFamily={MONO} fontSize={14} fill={P.faint}>{String(k + 1).padStart(2, "0")}</text>
            </g>
          );
        })}
      </svg>

      {A_HOUSES.map((h, j) => {
        const r = settle(t, reportAt(j), 0.4);
        if (t < reportAt(j)) return null;
        const fly = j === 0 ? 0 : eased(t, joinAt(j), joinAt(j) + 0.55);
        const hx = h.x + 40;
        const hy = GROUND - h.h - 70;
        const x = lerp(hx, card.x, fly);
        const y = lerp(hy, card.y + 60, fly) - Math.sin(fly * Math.PI) * 120;
        const gone = j === 0 ? 1 - ramp(t, joinAt(1), joinAt(1) + 0.4) : 1 - ramp(fly, 0.85, 1);
        return (
          <div key={h.k} style={{ position: "absolute", left: x, top: y, transform: `translate(-50%,-50%) scale(${lerp(0.4, 1, r) * lerp(1, 0.5, fly)})`, opacity: gone }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#fffdf8", border: `2px solid ${P.terracotta}`, borderRadius: 20, padding: "5px 12px", whiteSpace: "nowrap" }}>
              <div style={{ width: 10, height: 10, borderRadius: 5, background: P.terracotta }} />
              <span style={{ fontFamily: SANS, fontWeight: 500, fontSize: 20, color: P.ink }}>no water</span>
            </div>
          </div>
        );
      })}

      {t > decoyStart ? (
        <div
          style={{
            position: "absolute", left: lerp(lerp(HOUSES[DECOY].x + 40, 1380, decoyFly), HOUSES[DECOY].x + 40, decoyBack),
            top: lerp(lerp(GROUND - HOUSES[DECOY].h - 70, 380, decoyFly), GROUND - HOUSES[DECOY].h - 70, decoyBack),
            transform: "translate(-50%,-50%)", opacity: 1 - ramp(decoyBack, 0.7, 1),
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#fffdf8", border: `2px solid ${P.indigo}`, borderRadius: 20, padding: "5px 12px", whiteSpace: "nowrap" }}>
            <span style={{ fontFamily: SANS, fontWeight: 500, fontSize: 20, color: P.ink }}>no water · house 05</span>
            {t > W(31, "LINE") ? <Check ok={false} size={22} /> : null}
          </div>
        </div>
      ) : null}

      <div style={{ position: "absolute", left: card.x, top: card.y, transform: `translate(-50%,-50%) scale(${1 + 0.04 * Math.min(arrived, 6) * (t < W(30, "STRONGER") + 1 ? 1 : 1)})` }}>
        <Paper style={{ padding: "22px 34px", minWidth: 470, border: `2.5px solid ${P.indigo}` }}>
          <Mono size={15} color={P.indigo}>Case · Ward 12 · 4th Cross</Mono>
          <div style={{ fontFamily: SERIF, fontSize: 48, color: P.ink }}>No water</div>
          <div style={{ fontFamily: SERIF, fontSize: 32, color: P.marigold }}>
            {1 + arrived} {arrived === 0 ? "household" : "households"} on Main A
          </div>
        </Paper>
        {!MERGE_IS_LIVE ? (
          <div style={{ position: "absolute", left: "100%", top: 10, marginLeft: 18, opacity: ramp(t, W(30, "JOINS") - 0.2, W(30, "JOINS") + 0.2), whiteSpace: "nowrap" }}>
            <span style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 2, color: P.marigold, border: `1.5px dashed ${P.marigold}`, borderRadius: 6, padding: "4px 10px", background: "#fffdf8" }}>
              IN ROLLOUT · CROSS-CASE MERGE
            </span>
          </div>
        ) : null}
      </div>

      <div style={{ position: "absolute", right: 110, top: 190, width: 420, opacity: ramp(t, S(31).start - 0.1, S(31).start + 0.3) }}>
        <Paper style={{ padding: "24px 28px" }}>
          <Mono size={15} color={P.marigold}>Agent 08 · Anti-Abuse</Mono>
          {checks.map((c) => (
            <div key={c.text} style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 14, opacity: ramp(t, c.at - 0.1, c.at + 0.15) }}>
              <Check ok size={24} />
              <span style={{ fontFamily: SERIF, fontSize: 28, color: P.ink }}>{c.text}</span>
            </div>
          ))}
          <div style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 26, color: P.terracotta, marginTop: 14, opacity: ramp(t, W(31, "LINE") + 0.3, W(31, "LINE") + 0.6) }}>House 05 is on Main B: not counted.</div>
        </Paper>
      </div>
    </>
  );
};

export const Background: React.FC<{ t: number }> = ({ t }) => {
  const s = (i: number) => S(i).start;
  const days = 1 + Math.floor(6 * ramp(t, W(29, "CLOCK"), W(29, "MISSES")));
  const breached = t > W(29, "MISSES") + 0.2;
  const rungAt = [s(29) + 0.3, W(29, "OFFICER"), W(29, "NEXT", 1), W(29, "SIGNS") + 0.4];
  const desks = [
    { at: W(33, "WATER"), name: "Water board", note: "Live routes · Ward 12", live: true },
    { at: W(33, "OFFICES"), name: "Ward office", note: "Desk deployed", live: false },
    { at: W(33, "SCHOOLS"), name: "Schools", note: "Desk deployed", live: false },
    { at: W(33, "TANKERS"), name: "Water tankers", note: "Desk deployed", live: false },
    { at: W(33, "PAYMENT"), name: "Payments", note: "Desk deployed", live: false },
  ];
  const ring = 2 * Math.PI * 180;
  return (
    <>
      <Stage t={t} from={s(28) - 0.3} to={s(29) - 0.3}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
          <Mono size={20} color={P.marigold}>Ambient · temporal · always on</Mono>
          <Spoken t={t} i={28} accent={["time"]} accentStyle={{ fontStyle: "italic", color: P.terracotta }} style={{ fontFamily: SERIF, fontSize: 100, color: P.ink, letterSpacing: -3, textAlign: "center", width: 1500, marginTop: 18 }} />
        </AbsoluteFill>
      </Stage>

      <Stage t={t} from={s(29) - 0.3} to={s(30) - 0.3}>
        <div style={{ position: "absolute", left: 120, top: 70 }}>
          <Mono size={16} color={P.marigold}>Agent 06 · Watchdog · EventBridge Scheduler → Lambda</Mono>
          <Headline size={72} style={{ marginTop: 8 }}>Holds the <Em>legal clock.</Em></Headline>
        </div>
        <svg width={520} height={520} style={{ position: "absolute", left: 140, top: 290 }}>
          <circle cx={260} cy={260} r={180} fill="#fffdf8" stroke={P.rule} strokeWidth={18} />
          <circle
            cx={260} cy={260} r={180} fill="none" stroke={breached ? P.terracotta : P.marigold} strokeWidth={18} strokeLinecap="round"
            strokeDasharray={`${ring * ramp(t, W(29, "CLOCK"), W(29, "MISSES"))} ${ring}`} transform="rotate(-90 260 260)"
          />
          <text x={260} y={255} textAnchor="middle" fontFamily={SERIF} fontSize={120} fill={breached ? P.terracotta : P.ink}>{breached ? "7" : days}</text>
          <text x={260} y={310} textAnchor="middle" fontFamily={MONO} fontSize={20} letterSpacing={3} fill={breached ? P.terracotta : P.muted}>
            {breached ? "DEADLINE MISSED" : "DAYS OF 7"}
          </text>
        </svg>
        <div style={{ position: "absolute", left: 760, top: 250, width: 1040 }}>
          {LADDER.map((r, k) => {
            const a = settle(t, rungAt[k], 0.5);
            const on = t > rungAt[k];
            return (
              <div key={r.tier} style={{ marginTop: k === 0 ? 0 : 22, opacity: lerp(0.3, 1, ramp(t, rungAt[k], rungAt[k] + 0.2)), transform: `translateX(${(1 - a) * 40 + k * 40}px)` }}>
                <Paper style={{ padding: "20px 28px", display: "flex", alignItems: "center", justifyContent: "space-between", border: on && k > 0 && k < 3 ? `2px solid ${P.marigold}` : `1px solid ${P.rule}` }}>
                  <div>
                    <Mono size={14} color={P.faint}>Tier {r.tier}</Mono>
                    <div style={{ fontFamily: SERIF, fontSize: 38, color: P.ink }}>{r.who}</div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                    <span style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 24, color: P.muted }}>{r.note}</span>
                    {k > 0 && k < 3 ? (
                      <svg width={90} height={32} viewBox="0 0 120 40" opacity={ramp(t, W(29, "SIGNS") - 0.1 + k * 0.15, W(29, "SIGNS") + 0.3 + k * 0.15)}>
                        <path d="M4 28 C 14 6 22 36 32 18 C 40 4 46 34 58 20 C 66 10 72 30 84 16 C 92 8 102 24 116 12" stroke={P.indigo} strokeWidth={3} fill="none" />
                      </svg>
                    ) : k === 0 ? <Check ok size={30} /> : null}
                  </div>
                </Paper>
              </div>
            );
          })}
          <div style={{ marginTop: 22, marginLeft: 120, opacity: ramp(t, W(29, "PERSON") - 0.2, W(29, "PERSON") + 0.2) }}>
            <Mono size={16} color={P.indigo}>A person signs every step</Mono>
          </div>
        </div>
      </Stage>

      <Stage t={t} from={s(30) - 0.3} to={s(32) - 0.3}>
        <div style={{ position: "absolute", left: 120, top: 70 }}>
          <Mono size={16} color={P.marigold}>Agent 07 · Pattern Watch · DynamoDB Streams → Lambda</Mono>
          <Headline size={64} style={{ marginTop: 8 }}>
            Same water line, <Em color={P.indigo}>one stronger case.</Em>
          </Headline>
        </div>
        <Street t={t} />
      </Stage>

      <Stage t={t} from={s(32) - 0.3} to={s(33) - 0.3}>
        <div style={{ position: "absolute", left: 120, top: 70 }}>
          <Mono size={16} color={P.marigold}>Closure check · the street's own reports</Mono>
          <Headline size={72} style={{ marginTop: 8 }}>
            Closed on paper? <Em>Not while taps are dry.</Em>
          </Headline>
        </div>
        <div style={{ position: "absolute", left: 180, top: 330 }}>
          <Paper style={{ padding: "30px 40px", width: 780, height: 250, position: "relative" }}>
            <Mono size={15} color={P.indigo}>Case · Ward 12 · 4th Cross</Mono>
            <div style={{ fontFamily: SERIF, fontSize: 54, color: P.ink }}>No water</div>
            <div style={{ fontFamily: SERIF, fontSize: 30, color: P.muted }}>Desk reply: supply restored</div>
            <div style={{ position: "absolute", right: 30, top: 30 }}>
              <Stamp t={t} at={W(32, "RESOLVED")} text="CLOSED · RESOLVED" size={24} />
            </div>
            <div style={{ position: "absolute", right: 40, bottom: 30 }}>
              <Stamp t={t} at={W(32, "DISPUTE")} text="DISPUTED" color={P.terracotta} size={46} rotate={-10} />
            </div>
          </Paper>
          <div style={{ display: "flex", gap: 26, marginTop: 50 }}>
            {Array.from({ length: 7 }).map((_, k) => {
              const a = ramp(t, W(32, "DRY") - 0.2 + k * 0.08, W(32, "DRY") + 0.1 + k * 0.08);
              return (
                <div key={k} style={{ textAlign: "center", opacity: lerp(0.3, 1, a) }}>
                  <Icon kind="tap" size={58} color={a > 0.5 ? P.terracotta : P.ruleStrong} />
                  <div style={{ fontFamily: MONO, fontSize: 13, color: a > 0.5 ? P.terracotta : P.faint }}>DRY</div>
                </div>
              );
            })}
          </div>
        </div>
        <div style={{ position: "absolute", left: 1000, top: 380, width: 780, opacity: ramp(t, W(32, "CLIMBS") - 0.2, W(32, "CLIMBS") + 0.2), transform: `translateY(${(1 - settle(t, W(32, "CLIMBS") - 0.2, 0.5)) * 60}px)` }}>
          <svg width={120} height={180} style={{ display: "block", marginLeft: 20 }}>
            <path d="M60 170 L60 30 M20 70 L60 25 L100 70" stroke={P.marigold} strokeWidth={10} fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <Paper style={{ padding: "24px 32px", marginTop: 10, border: `2px solid ${P.marigold}` }}>
            <Mono size={14} color={P.faint}>Tier 2 · escalation drafted</Mono>
            <div style={{ fontFamily: SERIF, fontSize: 40, color: P.ink }}>Assistant Executive Engineer</div>
            <div style={{ fontFamily: SERIF, fontSize: 26, color: P.muted }}>with the street's reports as evidence</div>
          </Paper>
        </div>
      </Stage>

      <Stage t={t} from={s(33) - 0.3} to={s(34) - 0.3}>
        <div style={{ position: "absolute", left: 0, right: 0, top: 160, textAlign: "center" }}>
          <Headline size={84}>
            We started with <Em color={P.indigo}>water.</Em>
          </Headline>
          <div style={{ marginTop: 10 }}>
            <Mono size={18}>The same agents already speak to</Mono>
          </div>
        </div>
        <div style={{ position: "absolute", left: 100, right: 100, top: 470, display: "flex", justifyContent: "center", gap: 26 }}>
          {desks.map((d, k) => {
            const a = settle(t, d.at - 0.15, 0.5);
            return (
              <div key={d.name} style={{ opacity: ramp(t, d.at - 0.15, d.at + 0.05), transform: `translateY(${(1 - a) * 60}px)` }}>
                <Paper style={{ width: 300, padding: "30px 26px", textAlign: "center", border: d.live ? `2.5px solid ${P.sage}` : `1px solid ${P.rule}` }}>
                  <Icon kind={["water", "road", "school", "tap", "bank"][k]} size={54} color={d.live ? P.sage : P.indigo} />
                  <div style={{ fontFamily: SERIF, fontSize: 40, color: P.ink, marginTop: 12 }}>{d.name}</div>
                  <Mono size={13} color={d.live ? P.sage : P.faint}>{d.note}</Mono>
                </Paper>
              </div>
            );
          })}
        </div>
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 150, textAlign: "center", opacity: ramp(t, W(33, "PAYMENT") + 0.3, W(33, "PAYMENT") + 0.7) }}>
          <Mono size={16} color={P.faint}>Each desk is its own A2A process with its own records</Mono>
        </div>
      </Stage>
    </>
  );
};

// ------------------------------------------------------------ 8. the close

export const Close: React.FC<{ t: number; end: number }> = ({ t, end }) => {
  const s = (i: number) => S(i).start;
  const card = S(37).end + 0.9;
  return (
    <>
      <Stage t={t} from={s(34) - 0.3} to={s(35) - 0.3}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
          <Headline size={150}>Offices close tickets.</Headline>
          <div style={{ marginTop: 30 }}>
            <Stamp t={t} at={W(34, "CLOSE")} text="CLOSED" size={40} />
          </div>
        </AbsoluteFill>
      </Stage>

      <Stage t={t} from={s(35) - 0.3} to={s(36) - 0.3}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", textAlign: "center" }}>
          <Spoken t={t} i={35} text="Panchayat keeps the case open" style={{ fontFamily: SERIF, fontSize: 118, color: P.ink, letterSpacing: -3.5 }} accent={["panchayat"]} accentStyle={{ fontStyle: "italic", color: P.indigo }} />
          <div style={{ opacity: ramp(t, W(35, "UNTIL") - 0.1, W(35, "UNTIL") + 0.2) }}>
            <Headline size={118}>
              until the water <Em mark={eased(t, W(35, "COMES"), W(35, "BACK") + 0.5)}>comes back.</Em>
            </Headline>
          </div>
        </AbsoluteFill>
      </Stage>

      <Stage t={t} from={s(36) - 0.3} to={card - 0.2} enter="rise" exit="fade">
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", textAlign: "center" }}>
          <div style={{ opacity: lerp(1, 0.45, ramp(t, s(37) - 0.2, s(37) + 0.2)) }}>
            <Spoken t={t} i={36} style={{ fontFamily: SERIF, fontSize: 104, color: P.ink, letterSpacing: -3 }} />
          </div>
          <div style={{ marginTop: 20 }}>
            <Spoken t={t} i={37} text="With Panchayat, the street" style={{ fontFamily: SERIF, fontSize: 104, color: P.ink, letterSpacing: -3 }} accent={["panchayat"]} accentStyle={{ fontStyle: "italic", color: P.indigo }} />
            <div style={{ opacity: ramp(t, W(37, "GETS") - 0.1, W(37, "GETS") + 0.2) }}>
              <Headline size={104}>
                gets the <Em mark={eased(t, W(37, "LEVERAGE"), W(37, "LEVERAGE") + 0.5)}>leverage.</Em>
              </Headline>
            </div>
          </div>
        </AbsoluteFill>
      </Stage>

      <Stage t={t} from={card} to={end + 5} enter="fade" exit="none">
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", textAlign: "center" }}>
          <div style={{ fontFamily: KANNADA, fontSize: 56, color: P.marigold }}>ಪಂಚಾಯತ್</div>
          <div style={{ fontFamily: SERIF, fontSize: 200, color: P.ink, letterSpacing: -7, lineHeight: 1 }}>Panchayat</div>
          <div style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 46, color: P.muted, marginTop: 14 }}>Every household reports alone. The street gets the leverage.</div>
          <div style={{ width: 120, height: 2, background: P.ruleStrong, margin: "44px 0 34px" }} />
          <div style={{ fontFamily: SANS, fontWeight: 500, fontSize: 36, color: P.ink, letterSpacing: 1 }}>Ali · Kartik · Alakshendra · Raghav</div>
          <div style={{ marginTop: 22 }}>
            <Mono size={18} color={P.muted}>AWS Agents for Humans · Good Neighbor track</Mono>
          </div>
          <div style={{ marginTop: 10 }}>
            <Mono size={16} color={P.faint}>Built on Strands Agents · Amazon Bedrock AgentCore</Mono>
          </div>
        </AbsoluteFill>
      </Stage>
    </>
  );
};

export const FILM_END = VO_END + 5.5;
