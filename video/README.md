# Demo video

The hackathon submission film, built in [Remotion](https://www.remotion.dev) so every beat
is reproducible and every word on screen is exact. It uses the website's own design: cream
paper, Newsreader / IBM Plex Sans / IBM Plex Mono, and the site's marigold, sage, indigo and
terracotta, with soft warm glows instead of dark screens. Transitions take their cue from
the Numtera launch video (zoom-blur whips, kinetic type, floating UI) without copying it.

**Devpost rules** (checked 14 Sep): max 5 minutes, public on YouTube or Vimeo, must show the
working project and pitch the problem, who it is for and why it matters.
**Deadline: Mon 14 Sep 2026, 5:00 pm PT = Tue 15 Sep, 5:30 am IST.**

## Structure (about 4:20)

| # | Beat | Narration lines |
|---|---|---|
| 1 | Complaint slips from six offices, all stamped CLOSED | 1-7 |
| 2 | Three sourced facts: 15 times, 13.34 lakh, 2 in 3 | 8-10 |
| 3 | The building knows in 15 minutes; nobody has time to chase | 11-13 |
| 4 | Ink map: peninsular India to Bengaluru to the Ward 12 drawing | 14-16 |
| 5 | Meet Panchayat, built on Strands Agents and AgentCore | 17-19 |
| 6 | The live site: report, runtime trace, one card per agent, signature, A2A desk, refusal, ticket | 20-28 |
| 7 | When nobody is asking: Watchdog ladder, Pattern Watch, Anti-Abuse, disputed closure, other desks | 29-34 |
| 8 | Close and end card | 35-38 |

## What is real, and what is labelled

- **Website footage is captured from the deployed site** (`tools/capture_flow.py`). One real
  report was filed and signed on 14 Sep; the simulated BWSSB desk refused it and the site
  shows "desk did not take it · retry booked". The ticket shown after it, `BWSSB-100004`, is
  from an earlier live case on the same deployed desk, and the video says so on screen.
- **The cross-case merge is not deployed.** The Pattern Watch merge carries an
  `IN ROLLOUT · CROSS-CASE MERGE` tag while `MERGE_IS_LIVE` is `false` in
  `src/film/kit2.tsx`. When the merge ships, capture it, drop the footage in, and flip the flag.
- **Institution desks are calibrated simulators**, and the film says so.
- **Facts carry their sources on screen:** Deccan Herald (BBMP Sahaaya, the pothole closed 15
  times; BWSSB ~300 complaints a day, March 2024), The Tribune (RBI Ombudsman, 13.34 lakh
  complaints, FY 2024-25), LocalCircles via NewsMeter (2 in 3 could not get help).

## Render

```bash
cd video
npm ci
npm run studio                     # preview and scrub, composition "Film"
npx remotion render src/index.ts Film out/panchayat-film.mp4 --codec=h264 --crf=18 --timeout=120000
```

Fonts are self-hosted in `public/fonts` so a render never depends on reaching Google.

## Voiceover and timing

Every animation is keyed to the narrator's words through `src/film/vo2.json`. To change the
voice or the script:

1. Edit `narration-v2.txt` (one sentence per line; spell numbers out).
2. Put the new audio in `public/` and set `VO_FILE` in `src/film/Film.tsx`.
3. Re-time: `python tools/align_voiceover.py --narration narration-v2.txt --audio public/<file> --out src/film/vo2.json`
4. Regenerate the music bed to the new length: `python tools/make_audio.py`

Voice: ElevenLabs **Riya Rao - Engaging & Encouraging Tutor** (`ZBagl2bR5Xv44f5Xpxn6`, Indian
English, female), `eleven_multilingual_v2`, 2,944 credits. The raw take is 227 s; short pauses
were inserted between beats (243 s) so cards and stamps have room to read, then re-aligned.

If ElevenLabs generation fails through the Claude connector while the account itself works on
elevenlabs.io, sign in to elevenlabs.io in the browser once; on 14 Sep that restored the
connector's generation calls.

## Music and sound

`tools/make_audio.py` synthesizes the music bed (a reflective progression for the problem that
opens into a hopeful one at "Meet Panchayat") and the whoosh, stamp and pop effects. No
third-party audio, so no licensing questions.

## Credits

India outline: Natural Earth via world-atlas (`tools/india_map.py`); the map frames the
peninsula only. Fonts: Newsreader, IBM Plex Sans, IBM Plex Mono, Noto Serif Kannada (SIL OFL).
