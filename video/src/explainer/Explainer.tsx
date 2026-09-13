import React from "react";
import { AbsoluteFill, Audio, staticFile, useCurrentFrame } from "remotion";
import { EarthZoom } from "../EarthZoom";
import { Journey } from "./Journey";
import { Society } from "./Society";
import { C, FPS, KANNADA, MONO, SANS, eased, ramp, sent } from "./core";

const EARTH_END = 5.6;

const Ending: React.FC<{ t: number }> = ({ t }) => {
  const lines = [
    { at: sent(21).start, text: "We don't fix pipes.", color: C.dim, size: 64 },
    { at: sent(22).start, text: "We make sure someone does.", color: C.ink, size: 64 },
    { at: sent(23).start, text: "Every household reports alone.", color: C.dim, size: 48 },
    { at: sent(24).start, text: "The street gets the leverage.", color: C.amber, size: 48 },
  ];
  const lockup = sent(24).end + 0.1;
  const clearTop = ramp(t, lockup - 0.2, lockup + 0.5);
  return (
    <AbsoluteFill style={{ background: `rgba(6,10,20,${0.9 * ramp(t, sent(21).start - 0.7, sent(21).start)})`, alignItems: "center", justifyContent: "center" }}>
      <div style={{ textAlign: "center", opacity: 1 - clearTop, transform: `translateY(${-clearTop * 30}px)` }}>
        {lines.map((l, i) => (
          <div
            key={i}
            style={{
              fontFamily: SANS, fontWeight: 700, fontSize: l.size, color: l.color, letterSpacing: -0.5, marginTop: i === 2 ? 44 : 6,
              opacity: ramp(t, l.at - 0.15, l.at + 0.3), transform: `translateY(${(1 - eased(t, l.at - 0.15, l.at + 0.45)) * 18}px)`,
            }}
          >
            {l.text}
          </div>
        ))}
      </div>
      <div style={{ position: "absolute", textAlign: "center", opacity: clearTop }}>
        <div style={{ fontFamily: SANS, fontWeight: 800, fontSize: 96, color: C.ink, letterSpacing: -2 }}>Panchayat</div>
        <div style={{ fontFamily: KANNADA, fontWeight: 700, fontSize: 44, color: C.amber, marginTop: -6 }}>ಪಂಚಾಯತ್</div>
        <div style={{ fontFamily: MONO, fontSize: 20, letterSpacing: 3, color: C.dim, marginTop: 26 }}>
          AWS AGENTS FOR HUMANS · GOOD NEIGHBOR TRACK
        </div>
        <div style={{ fontFamily: MONO, fontSize: 16, letterSpacing: 2, color: C.faint, marginTop: 10 }}>
          STRANDS AGENTS · AMAZON BEDROCK AGENTCORE
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const Explainer: React.FC = () => {
  const t = useCurrentFrame() / FPS;
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Audio src={staticFile("voiceover.mp3")} />
      {t < EARTH_END ? (
        <AbsoluteFill style={{ opacity: 1 - ramp(t, EARTH_END - 0.9, EARTH_END) }}>
          <EarthZoom
            durationFrames={Math.round(5.3 * FPS)}
            shot={{ startDistance: 5.6, endDistance: 2 * 1.12, holdFraction: 0.14, spin: Math.PI * 0.04, easeIn: false }}
          />
          <div style={{ position: "absolute", left: 80, bottom: 64, fontFamily: MONO, fontSize: 18, letterSpacing: 2, color: C.dim, opacity: ramp(t, 1.0, 1.6) * (1 - ramp(t, 4.2, 4.8)) }}>
            12.97° N · 77.59° E · BENGALURU
          </div>
        </AbsoluteFill>
      ) : null}
      {t > 4.6 && t < sent(10).start + 0.2 ? <Society t={t} /> : null}
      {t > sent(10).start - 0.7 ? <Journey t={t} /> : null}
      {t > sent(21).start - 0.8 ? <Ending t={t} /> : null}
    </AbsoluteFill>
  );
};
