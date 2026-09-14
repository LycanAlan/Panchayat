import React from "react";
import { AbsoluteFill } from "remotion";
import india from "./india.json";
import { MONO, P, SERIF, eased, lerp, ramp, settle } from "./kit";
import { Em, Headline, Mono, Paper, S, Shot, Source, Spoken, Stage, Stamp, W, kf } from "./kit2";

// ------------------------------------------------------------ icons

export const Icon: React.FC<{ kind: string; color?: string; size?: number }> = ({ kind, color = P.indigo, size = 34 }) => {
  const s = { stroke: color, strokeWidth: 2.1, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24">
      {kind === "hospital" && <><rect x="3" y="3" width="18" height="18" rx="3" {...s} /><path d="M12 7v10M7 12h10" {...s} /></>}
      {kind === "power" && <path d="M13 2 4 14h7l-1 8 9-12h-7z" {...s} />}
      {kind === "school" && <><path d="M2 9l10-5 10 5-10 5z" {...s} /><path d="M6 11v5c3 2 9 2 12 0v-5" {...s} /></>}
      {kind === "bank" && <><path d="M3 9l9-5 9 5" {...s} /><path d="M5 10v8M10 10v8M14 10v8M19 10v8M3 20h18" {...s} /></>}
      {kind === "road" && <><path d="M8 3 5 21M16 3l3 18" {...s} /><ellipse cx="12" cy="13" rx="3" ry="1.6" {...s} /></>}
      {kind === "water" && <path d="M12 3s6 7 6 11a6 6 0 0 1-12 0c0-4 6-11 6-11z" {...s} />}
      {kind === "tap" && <><path d="M4 9h9a3 3 0 0 1 3 3v2" {...s} /><path d="M8 9V6h4v3M16 17v1" {...s} /><path d="M16 20.5v.5" {...s} /></>}
      {kind === "clock" && <><circle cx="12" cy="12" r="9" {...s} /><path d="M12 7v5l3 2" {...s} /></>}
    </svg>
  );
};

// ------------------------------------------------------------ 1. every complaint, closed

const SLIPS = [
  { kind: "hospital", office: "Govt hospital · OPD", issue: "Six hours, no doctor on duty", ref: "GRV-58201", note: "Day 3: same queue", x: -560, y: -250, r: -3 },
  { kind: "power", office: "Electricity board", issue: "Power cut, two days", ref: "ELC-20417", note: "Day 2: still dark", x: 0, y: -280, r: 2 },
  { kind: "school", office: "Education office", issue: "Scholarship not credited", ref: "EDU-09133", note: "Month 5: nothing", x: 560, y: -240, r: -2 },
  { kind: "bank", office: "Bank grievance cell", issue: "Wrong charge, no refund", ref: "BNK-77310", note: "Week 6: no reply", x: -560, y: 170, r: 2.5 },
  { kind: "road", office: "Municipality", issue: "Pothole on Main Road", ref: "MUN-31982", note: "Still there", x: 0, y: 200, r: -1.5 },
  { kind: "water", office: "Water board", issue: "No water for three days", ref: "WTR-45210", note: "Day 9: taps still dry", x: 560, y: 160, r: 3 },
];

const Slip: React.FC<{ t: number; i: number; inAt: number; stampAt: number; noteAt: number; scale?: number; stampLabel?: string }> = ({
  t,
  i,
  inAt,
  stampAt,
  noteAt,
  scale = 1,
  stampLabel = "CLOSED · RESOLVED",
}) => {
  const s = SLIPS[i];
  const k = settle(t, inAt, 0.55);
  if (t < inAt) return null;
  return (
    <div
      style={{
        position: "absolute", left: 960 + s.x - 240, top: 540 + s.y - 115, width: 480, height: 230,
        transform: `translateY(${(1 - k) * -90}px) rotate(${s.r}deg) scale(${lerp(0.9, 1, k) * scale})`, opacity: ramp(t, inAt, inAt + 0.15),
      }}
    >
      <Paper style={{ width: "100%", height: "100%", padding: "22px 26px", position: "relative", borderRadius: 6 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Icon kind={s.kind} />
            <Mono size={15}>{s.office}</Mono>
          </div>
          <span style={{ fontFamily: MONO, fontSize: 14, color: P.faint }}>{s.ref}</span>
        </div>
        <div style={{ fontFamily: SERIF, fontSize: 36, color: P.ink, marginTop: 22, letterSpacing: -0.5 }}>{s.issue}</div>
        <div style={{ height: 1, background: P.rule, marginTop: 20 }} />
        <div style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 25, color: P.terracotta, marginTop: 12, opacity: ramp(t, noteAt, noteAt + 0.3) }}>{s.note}</div>
        <div style={{ position: "absolute", right: 18, bottom: 14 }}>
          <Stamp t={t} at={stampAt} text={stampLabel} size={22} />
        </div>
      </Paper>
    </div>
  );
};

export const Opening: React.FC<{ t: number }> = ({ t }) => {
  const ins = [W(0, "HOSPITAL") - 0.15, W(1, "POWER") - 0.15, W(2, "SCHOLARSHIP") - 0.15, W(3, "BANK") - 0.15, W(4, "POTHOLE") - 0.15, W(4, "TAP") - 0.15];
  const closedAt = W(6, "CLOSED");
  const cam = {
    s: kf(t, [[0, 1.75], [ins[1], 1.75], [ins[1] + 0.6, 1.55], [ins[2] + 0.6, 1.35], [ins[3] + 0.6, 1.18], [ins[4] + 0.6, 1.0], [S(7).start, 1.05]]),
    x: kf(t, [[0, SLIPS[0].x], [ins[1], SLIPS[0].x], [ins[1] + 0.6, (SLIPS[0].x + SLIPS[1].x) / 2], [ins[2] + 0.6, 180], [ins[3] + 0.6, 0], [ins[4] + 0.6, 0]]),
    y: kf(t, [[0, SLIPS[0].y], [ins[2] + 0.6, -150], [ins[3] + 0.6, -40], [ins[4] + 0.6, 0]]),
  };
  const shake = t > closedAt && t < closedAt + 0.9 ? Math.sin(t * 90) * 3 * (1 - ramp(t, closedAt, closedAt + 0.9)) : 0;
  return (
    <Stage t={t} from={-1} to={S(7).start - 0.3} enter="none">
      <AbsoluteFill style={{ transform: `translate(${shake}px, ${shake * 0.6}px) scale(${cam.s}) translate(${-cam.x}px, ${-cam.y}px)` }}>
        {SLIPS.map((_, i) => (
          <Slip key={i} t={t} i={i} inAt={ins[i]} stampAt={closedAt + i * 0.09} noteAt={closedAt + 0.9 + i * 0.08} />
        ))}
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 70, textAlign: "center" }}>
        <div style={{ opacity: ramp(t, S(5).start - 0.1, S(5).start + 0.3) * (1 - ramp(t, S(6).start - 0.2, S(6).start)) }}>
          <Headline size={62}>Every one was <Em color={P.indigo}>reported.</Em></Headline>
        </div>
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, opacity: ramp(t, S(6).start, S(6).start + 0.3) }}>
          <Headline size={62}>And every one was marked <Em mark={eased(t, closedAt, closedAt + 0.5)}>closed.</Em></Headline>
        </div>
      </div>
    </Stage>
  );
};

// ------------------------------------------------------------ 2. the numbers

export const Facts: React.FC<{ t: number }> = ({ t }) => {
  const r0 = W(7, "RESOLVED");
  const r1 = W(7, "TIMES") + 0.15;
  const progress = ramp(t, r0, r1);
  const count = Math.max(1, Math.floor(lerp(1, 15.999, progress)));
  const phase = (progress * 14) % 1;
  const lakh = lerp(0, 13.34, eased(t, S(8).start + 0.2, W(8, "LAKH")));
  const dots = Array.from({ length: 30 });
  const filled = Math.round(20 * eased(t, W(9, "TWO") - 0.2, W(9, "HELP")));
  return (
    <>
      <Stage t={t} from={S(7).start - 0.3} to={S(8).start - 0.3}>
        <div style={{ position: "absolute", left: 150, top: 330, width: 640, height: 300, transform: "rotate(-2deg)" }}>
          <Paper style={{ width: "100%", height: "100%", padding: "34px 40px", position: "relative", borderRadius: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <Icon kind="road" size={40} />
              <Mono size={18}>Municipality · Whitefield</Mono>
            </div>
            <div style={{ fontFamily: SERIF, fontSize: 48, color: P.ink, marginTop: 28 }}>Large pothole on the road</div>
            <div style={{ position: "absolute", right: 30, bottom: 26, transform: `scale(${t > r0 ? lerp(1.5, 1, Math.min(1, phase * 5)) : 1})` }}>
              <Stamp t={t} at={r0 - 0.05} text={`RESOLVED ×${count}`} size={30} />
            </div>
          </Paper>
        </div>
        <div style={{ position: "absolute", left: 930, top: 250 }}>
          <div style={{ fontFamily: SERIF, fontSize: 280, color: P.ink, letterSpacing: -10, lineHeight: 0.9, opacity: ramp(t, r0, r0 + 0.3) }}>
            {count}
            <span style={{ fontSize: 110, fontStyle: "italic", color: P.terracotta, letterSpacing: -2 }}> times</span>
          </div>
          <Spoken t={t} i={7} text="marked resolved." style={{ fontFamily: SERIF, fontSize: 60, color: P.muted, marginTop: 10 }} />
          <div style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 58, color: P.terracotta, marginTop: 34, opacity: ramp(t, W(7, "STILL") - 0.3, W(7, "STILL")) }}>
            The pothole was still there.
          </div>
        </div>
        <Source t={t} at={S(7).start + 0.5}>Deccan Herald, BBMP Sahaaya complaints, Bengaluru</Source>
      </Stage>

      <Stage t={t} from={S(8).start - 0.3} to={S(9).start - 0.3}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
          <Icon kind="bank" size={80} color={P.indigo} />
          <div style={{ fontFamily: SERIF, fontSize: 250, color: P.ink, letterSpacing: -9, lineHeight: 1, marginTop: 20, fontVariantNumeric: "lining-nums tabular-nums" }}>
            {lakh.toFixed(2)}
            <span style={{ fontStyle: "italic", color: P.indigo, fontSize: 150, letterSpacing: -3 }}> lakh</span>
          </div>
          <Spoken t={t} i={8} text="complaints to India's banking ombudsman, in one year." style={{ fontFamily: SERIF, fontSize: 56, color: P.muted, marginTop: 18 }} />
        </AbsoluteFill>
        <Source t={t} at={S(8).start + 0.5}>RBI Integrated Ombudsman Scheme, FY 2024-25 · The Tribune</Source>
      </Stage>

      <Stage t={t} from={S(9).start - 0.3} to={S(10).start - 0.3}>
        <div style={{ position: "absolute", left: 170, top: 300, display: "grid", gridTemplateColumns: "repeat(6, 70px)", gap: 26 }}>
          {dots.map((_, k) => {
            const a = ramp(t, S(9).start + k * 0.03, S(9).start + 0.25 + k * 0.03);
            const on = k < filled;
            return (
              <div key={k} style={{ width: 70, height: 70, borderRadius: 35, opacity: a, transform: `scale(${lerp(0.4, 1, a)})`, background: on ? P.terracotta : "transparent", border: `3px solid ${on ? P.terracotta : P.ruleStrong}` }} />
            );
          })}
        </div>
        <div style={{ position: "absolute", left: 870, top: 240, width: 900 }}>
          <div style={{ fontFamily: SERIF, fontSize: 250, color: P.ink, letterSpacing: -9, lineHeight: 0.95, opacity: ramp(t, W(9, "TWO") - 0.2, W(9, "TWO") + 0.2) }}>
            2 <span style={{ fontStyle: "italic", color: P.terracotta, fontSize: 170 }}>in</span> 3
          </div>
          <Spoken t={t} i={9} text="people with a serious service problem could not get help." style={{ fontFamily: SERIF, fontSize: 56, color: P.muted, marginTop: 20, lineHeight: 1.2 }} />
        </div>
        <Source t={t} at={S(9).start + 0.5}>LocalCircles national survey, 15,000+ responses, 312 districts · NewsMeter</Source>
      </Stage>
    </>
  );
};

// ------------------------------------------------------------ 3. nobody has the time

const CHAT = [
  ["12/09", "06:02", "No water since morning?"],
  ["12/17", "06:04", "Same here. Tank is empty."],
  ["12/12", "06:05", "Motor is running dry"],
  ["12/04", "06:09", "Nothing on our side either"],
  ["12/21", "06:11", "Who do we even call?"],
  ["12/06", "06:14", "Someone please complain"],
];

export const Stamina: React.FC<{ t: number }> = ({ t }) => {
  const items = [
    { at: W(12, "OFFICE"), text: "Find the right office" },
    { at: W(12, "DEADLINE"), text: "Count the legal deadline" },
    { at: W(12, "MISSED"), text: "Notice when it's missed" },
    { at: W(12, "LADDER"), text: "Push it up the ladder" },
  ];
  const week = 1 + Math.floor(10 * ramp(t, W(12, "LADDER"), S(12).end + 0.4));
  return (
    <>
      <Stage t={t} from={S(10).start - 0.3} to={S(11).start - 0.3} exit="rise">
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
          <Spoken t={t} i={10} accent={["nobody", "knows"]} accentStyle={{ fontStyle: "italic", color: P.indigo }} style={{ fontFamily: SERIF, fontSize: 104, color: P.ink, letterSpacing: -3, textAlign: "center", width: 1500 }} />
        </AbsoluteFill>
      </Stage>

      <Stage t={t} from={S(11).start - 0.3} to={S(12).start - 0.3} enter="rise">
        <div style={{ position: "absolute", left: 150, top: 150, width: 560 }}>
          <Mono size={16}>Building group · 4th Cross</Mono>
          {CHAT.map(([flat, time, msg], k) => {
            const at = S(11).start + 0.1 + k * 0.32;
            const a = settle(t, at, 0.45);
            return (
              <div key={k} style={{ marginTop: 18, opacity: ramp(t, at, at + 0.15), transform: `translateY(${(1 - a) * 30}px) scale(${lerp(0.92, 1, a)})`, transformOrigin: "left" }}>
                <Paper style={{ padding: "14px 20px", borderRadius: 14, display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 18 }}>
                  <span style={{ fontFamily: SERIF, fontSize: 30, color: P.ink }}>{msg}</span>
                  <span style={{ fontFamily: MONO, fontSize: 14, color: P.faint, whiteSpace: "nowrap" }}>{flat} · {time}</span>
                </Paper>
              </div>
            );
          })}
        </div>
        <div style={{ position: "absolute", left: 860, top: 330, width: 950 }}>
          <Headline size={100}>The whole building knows</Headline>
          <div style={{ opacity: ramp(t, W(11, "FIFTEEN") - 0.2, W(11, "FIFTEEN") + 0.2) }}>
            <Headline size={100}>in <Em mark={eased(t, W(11, "FIFTEEN"), W(11, "MINUTES") + 0.4)}>15 minutes.</Em></Headline>
          </div>
        </div>
      </Stage>

      <Stage t={t} from={S(12).start - 0.3} to={S(13).start - 0.3}>
        <div style={{ position: "absolute", left: 150, top: 170 }}>
          <Headline size={80}>What nobody has <Em>time</Em> for:</Headline>
          {items.map((it, k) => {
            const a = settle(t, it.at - 0.1, 0.5);
            return (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 28, marginTop: 42, opacity: ramp(t, it.at - 0.1, it.at + 0.1), transform: `translateX(${(1 - a) * -50}px)` }}>
                <div style={{ width: 46, height: 46, border: `3px solid ${P.ruleStrong}`, borderRadius: 8, background: "#fffdf8" }} />
                <span style={{ fontFamily: SERIF, fontSize: 62, color: P.ink }}>{it.text}</span>
              </div>
            );
          })}
        </div>
        <div style={{ position: "absolute", right: 170, top: 330, textAlign: "center", opacity: ramp(t, W(12, "LADDER") - 0.2, W(12, "LADDER")) }}>
          <Paper style={{ padding: "34px 50px" }}>
            <Mono size={20}>Follow-up</Mono>
            <div style={{ fontFamily: MONO, fontSize: 130, color: week >= 11 ? P.terracotta : P.ink, lineHeight: 1.1 }}>W{String(week).padStart(2, "0")}</div>
            <Mono size={16} color={P.faint}>week after week</Mono>
          </Paper>
        </div>
      </Stage>
    </>
  );
};

// ------------------------------------------------------------ 4. where it hurts most: Ward 12

const MAP = india as unknown as { width: number; height: number; paths: string[]; bengaluru: [number, number]; cities: Record<string, [number, number]> };

export const MapZoom: React.FC<{ t: number }> = ({ t }) => {
  const [bx, by] = MAP.bengaluru;
  const draw = eased(t, S(13).start - 0.2, S(13).start + 2.2);
  const toBlr = W(14, "BENGALURU");
  const s = Math.exp(kf(t, [[S(13).start, Math.log(1.9)], [W(14, "WATER"), Math.log(2.3)], [toBlr + 0.2, Math.log(7)], [toBlr + 1.2, Math.log(9)]]));
  const cx = kf(t, [[S(13).start, 470], [W(14, "WATER"), 430], [toBlr + 0.2, bx], [toBlr + 1.2, bx]]);
  const cy = kf(t, [[S(13).start, 640], [W(14, "WATER"), 660], [toBlr + 0.2, by], [toBlr + 1.2, by]]);
  const toDrawing = ramp(t, toBlr + 0.9, toBlr + 1.6);
  const pin = ramp(t, W(14, "WATER") - 0.2, W(14, "WATER") + 0.2);
  const statAt = S(15).start;
  return (
    <Stage t={t} from={S(13).start - 0.3} to={S(16).start - 0.35}>
      <AbsoluteFill style={{ opacity: 1 - toDrawing * 0.85 }}>
        <svg width={1920} height={1080}>
          <g transform={`translate(960 540) scale(${s}) translate(${-cx} ${-cy})`}>
            {Array.from({ length: 14 }).map((_, k) => (
              <line key={`h${k}`} x1={-400} x2={1300} y1={k * 80} y2={k * 80} stroke={P.rule} strokeWidth={1 / s} strokeDasharray={`${4 / s} ${6 / s}`} />
            ))}
            {Array.from({ length: 16 }).map((_, k) => (
              <line key={`v${k}`} y1={-200} y2={1200} x1={-300 + k * 90} x2={-300 + k * 90} stroke={P.rule} strokeWidth={1 / s} strokeDasharray={`${4 / s} ${6 / s}`} />
            ))}
            {MAP.paths.map((d, k) => (
              <path key={k} d={d} fill={`rgba(224,138,30,${0.06 * draw})`} stroke={P.ink} strokeWidth={2.2 / s} pathLength={1} strokeDasharray="1" strokeDashoffset={1 - draw} strokeLinejoin="round" />
            ))}
            {Object.entries(MAP.cities).map(([name, [x, y]]) => (
              <g key={name} opacity={ramp(t, S(13).start + 1.4, S(13).start + 1.9) * (1 - ramp(t, toBlr, toBlr + 0.4))}>
                <circle cx={x} cy={y} r={4 / s} fill={P.muted} />
                <text x={x + 9 / s} y={y + 5 / s} fontFamily={MONO} fontSize={15 / s} fill={P.muted} letterSpacing={2 / s}>{name.toUpperCase()}</text>
              </g>
            ))}
            <circle cx={bx} cy={by} r={(22 + 10 * Math.sin(t * 5)) / s} fill={P.marigold} opacity={0.25 * pin} />
            <circle cx={bx} cy={by} r={7 / s} fill={P.marigold} opacity={pin} />
            <text x={bx + 14 / s} y={by - 12 / s} fontFamily={SERIF} fontSize={34 / s} fill={P.ink} opacity={pin}>Bengaluru</text>
          </g>
        </svg>
        <div style={{ position: "absolute", left: 90, top: 70, opacity: draw }}>
          <Mono size={16}>Sheet 01 · Peninsular India · N.T.S.</Mono>
        </div>
      </AbsoluteFill>

      <AbsoluteFill style={{ opacity: toDrawing }}>
        <Shot
          t={t}
          src="site/street.png"
          x={110}
          y={170}
          w={1380}
          h={620}
          rx={4}
          ry={-6}
          imgW={2000}
          imgH={1250}
          focus={[
            [toBlr + 0.9, { cx: 900, cy: 945, zoom: 2.1 }],
            [statAt + 3, { cx: 1000, cy: 940, zoom: 1.45 }],
          ]}
          sweepAt={toBlr + 1.4}
        />
        <div style={{ position: "absolute", left: 130, top: 70 }}>
          <Headline size={70}>Ward 12 · <Em color={P.indigo}>4th Cross</Em></Headline>
        </div>
      </AbsoluteFill>

      <div style={{ position: "absolute", left: 90, bottom: 150, opacity: ramp(t, S(13).start, S(13).start + 0.4) * (1 - ramp(t, W(14, "WATER") - 0.3, W(14, "WATER"))) }}>
        <Headline size={84}>So we started where it <Em>hurts most.</Em></Headline>
      </div>

      <div style={{ position: "absolute", right: 110, top: 300, opacity: ramp(t, statAt, statAt + 0.4), transform: `translateX(${(1 - settle(t, statAt, 0.6)) * 80}px)` }}>
        <Paper style={{ padding: "34px 44px", width: 520 }}>
          <Icon kind="water" size={46} color={P.marigold} />
          <div style={{ fontFamily: SERIF, fontSize: 150, color: P.ink, letterSpacing: -5, lineHeight: 1 }}>
            ~{Math.round(lerp(0, 300, eased(t, statAt + 0.2, W(15, "HUNDRED") + 0.4)))}
          </div>
          <div style={{ fontFamily: SERIF, fontSize: 40, color: P.muted, lineHeight: 1.2 }}>water complaints a day, in Bengaluru's 2024 crisis</div>
        </Paper>
      </div>
      <Source t={t} at={statAt + 0.3}>Deccan Herald, BWSSB chairman, March 2024</Source>
    </Stage>
  );
};
