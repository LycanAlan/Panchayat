# Demo video

The submission video for the AWS Agents for Humans hackathon, Good Neighbor
track. Code-rendered with [Remotion](https://www.remotion.dev), so every beat
is reproducible and editable, and every word on screen is exact.

**Rules that shape it** (Devpost, checked 14 Sep): max 5 minutes, public on
YouTube or Vimeo, must show the working project and pitch the problem, who it
is for and why it matters. Voiceover without appearing on camera is allowed.
**Deadline: Mon 14 Sep 2026, 5:00 pm PT = Tue 15 Sep, 5:30 am IST.**

## Structure

| Part | Length | Status |
|---|---|---|
| 1. Problem | 0:00 - 0:47 | **Done** (this folder) |
| 2. Architecture demo | 0:47 - 1:46 | **Done** (this folder) |
| 3. Screen recording of the live site | ~2 - 3 min | **Not started**, see below |

`renders/panchayat-explainer-v3-share.mp4` is the current cut, compressed to
fit GitHub. Render the full-quality master locally for the upload.

### Part 1, problem (Society scene)
Night Earth, a pulse on Bengaluru, a dive into a four-tower society and one lit
window. Father, mother and grandmother cards pop from it, each on its word;
grandmother's is HIGH priority. Cards pop across the building, each draws its
own line to "the right office?", a follow-up counter runs to week 11, and
"CLOSED: RESOLVED" stamps land on taps that are still dry. Then Panchayat: one
case opens, eleven neighbours' water cards merge into it (12 households), and
other issues line up on the right sized by priority.

**The merge carries a `DESIGN PREVIEW · live build opens one case per report`
label.** Per `docs/handoff/status-2026-09-14.md`, the cross-case merge rule is
not built; the live site mints a case per report. The video must not claim
agreement the system did not compute.

### Part 2, architecture (Journey scene)
The case rides an S-shaped path through one cloud per agent: Intake (Kannada
read-back), Household, Privacy Warden ("dialysis" blurs to "HIGH priority ·
reason withheld"), Remedy (the real ladder entry: BWSSB Assistant Engineer,
BWSSB Citizen Charter), Digest (a named signature), BWSSB desk over A2A (ticket
BWSSB-100004, the real deployed ticket format), Watchdog (7-day window,
breach, tier 2 to the Assistant Executive Engineer) and the closure check
(desk says resolved, 9 new reports say dry, DISPUTED). Each cloud names the
AWS piece behind it. Ends on "We don't fix pipes. We make sure someone does."

## Render

```bash
cd video
npm ci
npm run studio      # preview and scrub
npm run render      # out/panchayat-explainer.mp4, ~106 s, 1080p30, ~15 min
```

Beats are timed from `src/vo_timing.json`. If you change `narration.txt`,
regenerate `public/voiceover.mp3`, then re-time everything with:

```bash
python video/tools/align_voiceover.py
```

## Voiceover

ElevenLabs, `eleven_multilingual_v2`, voice **Ranbir Merchant - Warm &
Friendly** (neutral Indian accent), 104.6 s, 1,409 credits. Pranab was the
first choice but every Indian-accent library voice except a few needs the
Creator plan; this one works on the current plan.

## Credits

Earth day, night-lights and cloud textures: [Solar System Scope](https://www.solarsystemscope.com/textures/),
CC BY 4.0, derived from NASA imagery. Fonts: Inter, JetBrains Mono, Noto Sans
Kannada via Google Fonts.

## Next: screen recording (Part 3)

Planned shot list, recorded headlessly at 1920x1080 with Playwright against
the deployed site:

1. Home, type "No water in our tank for three days", 4th Cross, Report it.
   The real runtime trace replays: intake, routing with its citation, draft.
2. Open the live file: state, authority, statutory deadline, the draft body.
3. Sign it. About 100 s later the Watchdog files it (cut in the edit).
4. The ticket appears on the case page.

**Before recording, a person must OK the live writes:** it adds one real case
to the live table and the Watchdog files it with the simulated BWSSB desk.

**The deployed site predates PR #43**, so the case page will not show the
ticket arrive on its own; step 4 needs "Read it again" on camera unless the web
Lambda is redeployed first (`scripts/deploy_web.ps1`, needs the AWS CLI and
the `panchayat` profile, which Raghav's laptop does not have).
