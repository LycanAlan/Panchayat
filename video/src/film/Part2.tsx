import React from "react";
import { AbsoluteFill } from "remotion";
import { KANNADA, MONO, P, SANS, SERIF, Streak, eased, lerp, ramp, settle } from "./kit";
import { AgentCard, Check, Em, Headline, Mono, Paper, S, Shot, Spoken, Stage, Stamp, W, kf } from "./kit2";
import { Icon } from "./Part1";

// ------------------------------------------------------------ 5. Meet Panchayat

export const Meet: React.FC<{ t: number }> = ({ t }) => {
  const m = W(16, "MEET") - 0.15;
  const letter = (i: number) => ramp(t, m + i * 0.07, m + 0.35 + i * 0.07);
  const shift = eased(t, m + 0.55, m + 1.1);
  return (
    <Stage t={t} from={S(16).start - 0.3} to={S(19).start - 0.3} enter="fade">
      <AbsoluteFill style={{ alignItems: "center", paddingTop: 230 }}>
        <div style={{ fontFamily: KANNADA, fontSize: 48, color: P.marigold, opacity: ramp(t, m + 0.9, m + 1.3), marginBottom: 4 }}>ಪಂಚಾಯತ್</div>
        <div style={{ display: "flex", alignItems: "baseline", fontFamily: SERIF, color: P.ink, letterSpacing: -6 }}>
          <div style={{ display: "flex", fontSize: lerp(290, 170, shift) }}>
            {"Meet".split("").map((ch, i) => (
              <Streak key={i} amount={(1 - letter(i)) * 160} style={{ opacity: letter(i), transform: `translateY(${(1 - letter(i)) * 120}px)` }}>
                {ch}
              </Streak>
            ))}
          </div>
          <div style={{ fontSize: 170, fontStyle: "italic", color: P.indigo, marginLeft: 38 * shift, maxWidth: shift * 900, overflow: "hidden", whiteSpace: "nowrap", opacity: ramp(t, m + 0.6, m + 0.9) }}>
            Panchayat
          </div>
        </div>
        <Spoken
          t={t}
          i={17}
          accent={["stays", "case"]}
          accentStyle={{ fontStyle: "italic", color: P.terracotta }}
          style={{ fontFamily: SERIF, fontSize: 50, color: P.ink, width: 1400, textAlign: "center", lineHeight: 1.25, marginTop: 34 }}
        />
        <div style={{ display: "flex", gap: 22, marginTop: 50 }}>
          {[
            { at: W(18, "STRANDS"), label: "Strands Agents" },
            { at: W(18, "AMAZON"), label: "Amazon Bedrock AgentCore" },
          ].map((c) => {
            const a = settle(t, c.at - 0.1, 0.5);
            return (
              <div key={c.label} style={{ opacity: ramp(t, c.at - 0.1, c.at + 0.1), transform: `translateY(${(1 - a) * 30}px) scale(${lerp(0.9, 1, a)})` }}>
                <Paper style={{ padding: "16px 28px", borderRadius: 40, display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 12, height: 12, borderRadius: 6, background: P.marigold }} />
                  <span style={{ fontFamily: SANS, fontWeight: 600, fontSize: 30, color: P.ink }}>{c.label}</span>
                </Paper>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </Stage>
  );
};

// ------------------------------------------------------------ 6. the live site, agent by agent

const FX = 70;
const FY = 190;
const FW = 1180;
const FH = 664;

const ROWS = { signal: 736, delib: 766, minim: 796, routed: 846, drafted: 915 };

const Chip: React.FC<{ children: React.ReactNode; color?: string; style?: React.CSSProperties }> = ({ children, color = P.marigold, style }) => (
  <span style={{ display: "inline-block", fontFamily: SANS, fontWeight: 500, fontSize: 22, color: P.ink, border: `2px solid ${color}`, borderRadius: 22, padding: "5px 14px", background: "#fffdf8", ...style }}>
    {children}
  </span>
);

export const Website: React.FC<{ t: number }> = ({ t }) => {
  const s = (i: number) => S(i).start;
  const layer = (from: number, to: number) => ramp(t, from - 0.25, from + 0.15) * (1 - ramp(t, to - 0.15, to + 0.25));

  // trace rows revealed as each agent is explained
  const maskTop = kf(t, [
    [s(21) - 0.3, ROWS.signal - 32],
    [s(21) + 0.2, ROWS.signal],
    [s(22), ROWS.signal],
    [s(22) + 0.4, ROWS.delib],
    [s(23), ROWS.delib],
    [s(23) + 0.4, ROWS.minim],
    [s(24), ROWS.minim],
    [s(24) + 0.5, ROWS.drafted],
  ]);
  const traceFocus = (): [number, { cx: number; cy: number; zoom: number }][] => [
    [s(21), { cx: 668, cy: 735, zoom: 1.85 }],
    [s(22), { cx: 668, cy: 745, zoom: 1.85 }],
    [s(23), { cx: 668, cy: 765, zoom: 1.85 }],
    [s(24), { cx: 668, cy: 820, zoom: 1.6 }],
  ];

  const typed = ramp(t, W(20, "WRITES"), S(20).end);
  const clickAt = S(25).end - 0.2;
  const cursorK = eased(t, W(25, "ASKS"), clickAt);
  const signedLayer = layer(clickAt + 0.3, s(26) + 0.6);
  const a2a = ramp(t, s(26) - 0.1, s(26) + 0.5) * (1 - ramp(t, s(27) - 0.3, s(27) + 0.1));
  const packet = eased(t, W(26, "TRAVELS"), W(26, "DESK") + 0.2);

  const tag = (text: string, from: number, to: number) => (
    <div style={{ position: "absolute", left: FX + 10, top: FY - 70, opacity: layer(from, to) }}>
      <Mono size={17} color={P.indigo}>{text}</Mono>
    </div>
  );

  return (
    <Stage t={t} from={s(19) - 0.3} to={s(28) - 0.3} enter="rise">
      <div style={{ position: "absolute", left: FX + 10, top: 70, opacity: ramp(t, s(19) - 0.2, s(19) + 0.3) }}>
        <Headline size={64}>
          Here it is, <Em color={P.indigo}>live.</Em>
        </Headline>
      </div>

      <Shot t={t} src="flow/01_home.png" x={FX} y={FY} w={FW} h={FH} opacity={layer(s(19), s(20))} focus={[[s(19), { cx: 960, cy: 540, zoom: 0.62 }], [s(20), { cx: 900, cy: 520, zoom: 0.75 }]]} sweepAt={s(19) + 0.3} />
      {tag("Deployed site · Amazon Bedrock AgentCore", s(19), s(21))}

      <Shot
        t={t}
        src="flow/03_intake_typed.png"
        x={FX}
        y={FY}
        w={FW}
        h={FH}
        opacity={layer(s(20), s(21))}
        focus={[[s(20), { cx: 720, cy: 820, zoom: 1.1 }], [s(20) + 1.2, { cx: 660, cy: 915, zoom: 1.9 }]]}
        masks={[{ x: lerp(422, 690, typed), y: 889, w: 690 - lerp(422, 690, typed) + 2, h: 34, opacity: typed < 1 ? 1 : 0 }]}
      />

      <Shot
        t={t}
        src="flow/06_trace_done.png"
        x={FX}
        y={FY}
        w={FW}
        h={FH}
        opacity={layer(s(21), s(25))}
        focus={traceFocus()}
        masks={[{ x: 396, y: maskTop, w: 560, h: 1080 - maskTop, opacity: 1 }]}
        highlights={[
          { x: 400, y: 707, w: 540, h: 28, from: s(21) + 0.3, to: s(22) },
          { x: 400, y: 737, w: 540, h: 28, from: s(22) + 0.4, to: s(23) },
          { x: 400, y: 767, w: 540, h: 28, from: s(23) + 0.4, to: s(24) },
          { x: 716, y: 800, w: 222, h: 44, from: W(24, "CITES") - 0.1 },
        ]}
      />
      {tag("Runtime trace · what each agent did", s(21), s(25))}

      <Shot
        t={t}
        src="flow/08_draft_to_sign.png"
        x={FX}
        y={FY}
        w={FW}
        h={FH}
        opacity={layer(s(25), clickAt + 0.3)}
        focus={[[s(25), { cx: 780, cy: 640, zoom: 1.0 }], [s(25) + 1.5, { cx: 760, cy: 730, zoom: 1.25 }]]}
        highlights={[{ x: 404, y: 816, w: 272, h: 34, from: W(25, "SIGNS") }]}
      >
        <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0, pointerEvents: "none" }}>
          <g transform={`translate(${lerp(980, 560, cursorK)} ${lerp(1000, 838, cursorK)}) scale(${t > clickAt && t < clickAt + 0.2 ? 0.85 : 1})`} opacity={ramp(t, W(25, "ASKS") - 0.2, W(25, "ASKS"))}>
            <path d="M0 0 L0 26 L7 19 L12 30 L17 28 L12 17 L22 17 Z" fill={P.ink} stroke="#fff" strokeWidth={2} />
          </g>
          <circle cx={560} cy={838} r={10 + 50 * ramp(t, clickAt, clickAt + 0.5)} fill="none" stroke={P.marigold} strokeWidth={4} opacity={t > clickAt ? 1 - ramp(t, clickAt, clickAt + 0.5) : 0} />
        </svg>
      </Shot>
      {tag("Rule 4 · agents draft, people sign", s(25), clickAt + 0.3)}

      <Shot t={t} src="flow/10_signed.png" x={FX} y={FY} w={FW} h={FH} opacity={signedLayer * (1 - a2a * 0.8)} blur={a2a * 8} focus={[[clickAt, { cx: 900, cy: 760, zoom: 1.1 }]]} highlights={[{ x: 404, y: 910, w: 400, h: 70, from: clickAt + 0.5 }]} />

      <AbsoluteFill style={{ opacity: a2a }}>
        <div style={{ position: "absolute", left: FX + 40, top: FY + 170, width: FW - 80 }}>
          <svg width={FW - 80} height={330} style={{ position: "absolute", left: 0, top: 0 }}>
            <line x1={330} y1={160} x2={FW - 460} y2={160} stroke={P.ruleStrong} strokeWidth={3} strokeDasharray="10 10" />
            <line x1={(FW - 80) / 2} y1={10} x2={(FW - 80) / 2} y2={320} stroke={P.indigo} strokeWidth={2} strokeDasharray="6 8" />
            <circle cx={lerp(330, FW - 460, packet)} cy={160} r={16} fill={P.marigold} />
          </svg>
          <Paper style={{ position: "absolute", left: 0, top: 80, width: 320, padding: "22px 26px" }}>
            <Mono size={14}>Panchayat</Mono>
            <div style={{ fontFamily: SERIF, fontSize: 34, color: P.ink, marginTop: 6 }}>Signed filing</div>
            <div style={{ fontFamily: SERIF, fontSize: 24, color: P.muted }}>tier 1 · BWSSB Assistant Engineer</div>
          </Paper>
          <div style={{ position: "absolute", left: (FW - 80) / 2 - 60, top: -26, width: 120, textAlign: "center" }}>
            <Mono size={16} color={P.indigo}>A2A</Mono>
          </div>
          <Paper style={{ position: "absolute", right: 0, top: 80, width: 380, padding: "22px 26px", border: `2px dashed ${P.indigo}` }}>
            <Mono size={14} color={P.indigo}>Simulated desk · own process</Mono>
            <div style={{ fontFamily: SERIF, fontSize: 34, color: P.ink, marginTop: 6 }}>Water board desk</div>
            <div style={{ fontFamily: SERIF, fontSize: 24, color: P.muted }}>keeps its own records</div>
          </Paper>
        </div>
      </AbsoluteFill>

      <Shot
        t={t}
        src="flow/11_ticket.png"
        x={FX}
        y={FY}
        w={FW}
        h={FH}
        opacity={layer(s(27), W(27, "TICKET") - 0.2)}
        focus={[[s(27), { cx: 900, cy: 320, zoom: 1.2 }], [W(27, "REFUSE"), { cx: 780, cy: 340, zoom: 1.45 }]]}
        highlights={[{ x: 592, y: 370, w: 322, h: 30, from: W(27, "REFUSE") - 0.1, color: P.terracotta }]}
      />
      <Shot
        t={t}
        src="flow/21_ticket_filing.png"
        x={FX}
        y={FY}
        w={FW}
        h={FH}
        opacity={layer(W(27, "TICKET") - 0.2, s(28) + 1)}
        focus={[[W(27, "TICKET") - 0.2, { cx: 760, cy: 880, zoom: 1.2 }], [W(27, "TICKET") + 0.8, { cx: 700, cy: 920, zoom: 1.55 }]]}
        masks={[{ x: 400, y: 1018, w: 1120, h: 40, opacity: 1 }]}
        highlights={[
          { x: 592, y: 942, w: 190, h: 28, from: W(27, "TICKET") + 0.1, color: P.sage },
          { x: 592, y: 980, w: 120, h: 28, from: W(27, "TICKET") + 0.3, color: P.sage },
        ]}
      />
      {tag("Same deployed desk · an earlier live case", W(27, "TICKET") - 0.2, s(28) + 1)}

      {/* ---- the agent explained beside the UI ---- */}
      <AgentCard t={t} from={s(21)} to={s(22) - 0.25} n="01" name="Intake" line="Reads the report back before anything acts on it.">
        <div style={{ fontFamily: SERIF, fontSize: 28, color: P.ink, fontStyle: "italic" }}>“No water in our tank for three days?”</div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 12 }}>
          <Check ok size={26} />
          <Mono size={14}>Confirmed · then pursued</Mono>
        </div>
      </AgentCard>

      <AgentCard t={t} from={s(22)} to={s(23) - 0.25} n="02" name="Household" line="Brings the family's view into one position.">
        {(() => {
          const k = eased(t, W(22, "GRANDMOTHER"), W(22, "URGENT"));
          return (
            <div style={{ position: "relative", height: 150 }}>
              {[
                ["Father", "no water", P.marigold],
                ["Mother", "nothing to cook", P.marigold],
                ["Grandmother", "dialysis Thursday", P.terracotta],
              ].map(([who, what, color], i) => (
                <div key={who} style={{ position: "absolute", left: lerp(0, 60, k), top: lerp(i * 50, 45, k), opacity: lerp(1, 0, ramp(k, 0.6, 1)) }}>
                  <Chip color={color}>{who} · {what}</Chip>
                </div>
              ))}
              <div style={{ position: "absolute", left: 0, top: 36, opacity: ramp(k, 0.7, 1) }}>
                <div style={{ fontFamily: SERIF, fontSize: 34, color: P.ink }}>One household position</div>
                <Mono size={15} color={P.terracotta}>Urgent · needed by Thursday</Mono>
              </div>
            </div>
          );
        })()}
      </AgentCard>

      <AgentCard t={t} from={s(23)} to={s(24) - 0.25} n="03" name="Privacy Warden" line="Decides exactly what leaves the home.">
        {(() => {
          const k = ramp(t, W(23, "MEDICAL") - 0.3, W(23, "PRIVATE"));
          return (
            <div style={{ position: "relative", height: 110 }}>
              <div style={{ position: "absolute", fontFamily: SERIF, fontSize: 36, color: P.terracotta, filter: `blur(${k * 12}px)`, opacity: 1 - ramp(k, 0.6, 1) }}>Dialysis on Thursday</div>
              <div style={{ position: "absolute", opacity: ramp(k, 0.5, 1) }}>
                <div style={{ fontFamily: SERIF, fontSize: 36, color: P.ink }}>HIGH priority</div>
                <Mono size={15} color={P.sage}>Reason withheld · stays in the home</Mono>
              </div>
            </div>
          );
        })()}
      </AgentCard>

      <AgentCard t={t} from={s(24)} to={s(25) - 0.25} n="04" name="Remedy" line="Finds the responsible office, and cites the rule.">
        {[
          { at: W(24, "OFFICE"), text: "BWSSB, not BBMP" },
          { at: W(24, "TABLE"), text: "From 31 curated Ward 12 routes" },
          { at: W(24, "CITES"), text: "Cites BWSSB Citizen Charter" },
          { at: W(24, "GUESSES"), text: "Never generated, never guessed" },
        ].map((r) => (
          <div key={r.text} style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10, opacity: ramp(t, r.at - 0.1, r.at + 0.15) }}>
            <Check ok size={24} />
            <span style={{ fontFamily: SERIF, fontSize: 28, color: P.ink }}>{r.text}</span>
          </div>
        ))}
      </AgentCard>

      <AgentCard t={t} from={s(25)} to={s(26) - 0.25} n="05" name="Digest" line="Asks one person, in their language, and waits.">
        <div style={{ fontFamily: SERIF, fontSize: 28, color: P.ink }}>“Your water case is ready to file with BWSSB. Reply YES to approve.”</div>
        <div style={{ marginTop: 12, opacity: ramp(t, clickAt, clickAt + 0.3) }}>
          <Mono size={15} color={P.sage}>Signed by a named member</Mono>
        </div>
      </AgentCard>

      <AgentCard t={t} from={s(26)} to={s(27) - 0.25} n="" label="Institution · over A2A" name="Institution desk" line="A separate agent, reached over A2A, keeping its own records.">
        <Mono size={15} color={P.indigo}>Calibrated simulator · refuses and goes quiet like a real office</Mono>
      </AgentCard>

      <AgentCard t={t} from={s(27)} to={s(28) - 0.3} n="" label="Institution · reply" name="What the desk said" line="The answer is written back to the case.">
        <div style={{ display: "flex", alignItems: "center", gap: 12, opacity: ramp(t, W(27, "REFUSE") - 0.1, W(27, "REFUSE") + 0.2) }}>
          <Check ok={false} size={26} />
          <span style={{ fontFamily: SERIF, fontSize: 28, color: P.ink }}>Refused · clock held, retry booked</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12, opacity: ramp(t, W(27, "TICKET") - 0.1, W(27, "TICKET") + 0.2) }}>
          <Check ok size={26} />
          <span style={{ fontFamily: MONO, fontSize: 28, color: P.ink }}>BWSSB-100004</span>
        </div>
        <div style={{ marginTop: 16 }}>
          <Stamp t={t} at={W(27, "COMES") + 0.1} text="TICKET ISSUED" size={24} />
        </div>
      </AgentCard>

      <div style={{ position: "absolute", left: FX + 20, bottom: 70, opacity: ramp(t, s(20), s(20) + 0.3) * (1 - ramp(t, s(21) - 0.2, s(21))) }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <Icon kind="tap" size={36} color={P.marigold} />
          <span style={{ fontFamily: SERIF, fontSize: 40, color: P.ink }}>A resident writes it in their own words.</span>
        </div>
      </div>
    </Stage>
  );
};
