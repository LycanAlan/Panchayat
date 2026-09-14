import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";
import { PaperGlow, ramp } from "./kit";
import { S, W } from "./kit2";
import { Facts, MapZoom, Opening, Stamina } from "./Part1";
import { Meet, Website } from "./Part2";
import { Background, Close, FILM_END } from "./Part3";

export const FPS = 30;
export const FILM_FRAMES = Math.round(FILM_END * FPS);
export const VO_FILE = "vo-riya.mp3";

const WHOOSH = [7, 8, 9, 10, 11, 12, 13, 16, 19, 28, 29, 30, 32, 33, 34, 35].map((i) => S(i).start - 0.35);
const STAMPS = [W(6, "CLOSED"), W(7, "RESOLVED"), W(27, "COMES") + 0.1, W(32, "RESOLVED"), W(32, "DISPUTE"), W(34, "CLOSE")];
const POPS = [W(0, "HOSPITAL"), W(1, "POWER"), W(2, "SCHOLARSHIP"), W(3, "BANK"), W(4, "POTHOLE"), W(4, "TAP")].map((x) => x - 0.15);

const Sfx: React.FC<{ at: number; src: string; volume: number }> = ({ at, src, volume }) => (
  <Sequence from={Math.max(0, Math.round(at * FPS))} durationInFrames={60}>
    <Audio src={staticFile(src)} volume={volume} />
  </Sequence>
);

export const Film: React.FC = () => {
  const frame = useCurrentFrame();
  const t = frame / FPS;
  const warmth = interpolate(t, [0, S(7).start, S(16).start, S(17).start, S(28).start, S(34).start, FILM_END], [0.7, 0.75, 0.9, 1.25, 1.0, 1.1, 1.4], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <PaperGlow t={t} warmth={warmth} />
      <Opening t={t} />
      <Facts t={t} />
      <Stamina t={t} />
      <MapZoom t={t} />
      <Meet t={t} />
      <Website t={t} />
      <Background t={t} />
      <Close t={t} end={FILM_END} />

      <Audio src={staticFile(VO_FILE)} volume={1} />
      <Audio
        src={staticFile("audio/music_bed.mp3")}
        volume={(f) => 0.22 * ramp(f / FPS, 0, 2.5) * (1 - ramp(f / FPS, FILM_END - 4, FILM_END)) * (f / FPS > S(37).end ? 1.6 : 1)}
      />
      {WHOOSH.map((at, k) => <Sfx key={`w${k}`} at={at} src="audio/whoosh.wav" volume={0.35} />)}
      {STAMPS.map((at, k) => <Sfx key={`s${k}`} at={at} src="audio/stamp.wav" volume={0.5} />)}
      {POPS.map((at, k) => <Sfx key={`p${k}`} at={at} src="audio/pop.wav" volume={0.3} />)}
    </AbsoluteFill>
  );
};
