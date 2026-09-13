import { Easing, interpolate } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";
import { loadFont as loadKannada } from "@remotion/google-fonts/NotoSansKannada";
import timing from "../vo_timing.json";

export const FPS = 30;
export const TOTAL_SECONDS = 106.2;

export const SANS = loadInter("normal", { weights: ["400", "500", "600", "700", "800"], subsets: ["latin"] }).fontFamily;
export const MONO = loadMono("normal", { weights: ["400", "600"], subsets: ["latin"] }).fontFamily;
export const KANNADA = loadKannada("normal", { weights: ["500", "700"], subsets: ["kannada"] }).fontFamily;

export const C = {
  bg: "#060a14",
  panel: "rgba(13,19,33,0.94)",
  ink: "#f2eee6",
  dim: "#9aa3b8",
  faint: "#4a5470",
  amber: "#ffb020",
  red: "#ff5a4e",
  indigo: "#7b93ff",
  green: "#3ddc97",
  lift: "#9fb0ff",
  light: "#d2b0ff",
  garbage: "#7fd6b4",
};

type Word = { w: string; s: number; e: number };
type Sentence = { i: number; start: number; end: number; text: string; words: Word[] };
const SENTENCES = timing as Sentence[];

export const sent = (i: number) => SENTENCES[i];
export const wordAt = (i: number, word: string, nth = 0): number => {
  const hits = SENTENCES[i].words.filter((w) => w.w === word.toUpperCase());
  if (!hits[nth]) throw new Error(`no word ${word} in sentence ${i}`);
  return hits[nth].s;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
export const EASE = Easing.bezier(0.33, 0, 0.2, 1);
export const ramp = (t: number, a: number, b: number) => interpolate(t, [a, b], [0, 1], clamp);
export const eased = (t: number, a: number, b: number) => EASE(ramp(t, a, b));
export const popIn = (t: number, a: number, dur = 0.45) => Easing.out(Easing.back(1.8))(ramp(t, a, a + dur));
export const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

export function keyframes(t: number, keys: [number, number][]): number {
  if (t <= keys[0][0]) return keys[0][1];
  for (let i = 0; i < keys.length - 1; i++) {
    const [t0, v0] = keys[i];
    const [t1, v1] = keys[i + 1];
    if (t <= t1) return lerp(v0, v1, EASE(t1 === t0 ? 1 : (t - t0) / (t1 - t0)));
  }
  return keys[keys.length - 1][1];
}

export function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
}
