# Panchayat — the site

The public face of the case file. Five routes that tell the story from
fixtures, one route that reads the deployed runtime, one drawing, no UI library.

```bash
npm install
npm run dev      # vite, :5173 — /api proxied to :8787, see below
npm run build    # static output in dist/
npm run preview
npm run lint     # oxlint
```

## What is where

```
src/
  routes/      Index · Case · Street · Process · About · Live
  components/  Masthead Footer StreetPlan HeroSection Document
               Stamp LegalClock Ladder ReportInput Icon Bits
  data/        case · street · authorities · indic · segments
  styles/      reset · tokens · type · layout · paper · plan
               components · pages · live
  lib/         motion.js — Lenis + ScrollTrigger + reduced motion
               api.js — the only file that touches the network
```

## Decisions worth knowing before you edit

**No UI library, and that is the point.** Chakra, MUI, Radix, Tailwind,
FontAwesome and Lucide were all removed. Every rule, icon and line weight here
is authored. Adding a component library back would undo the only thing that
makes the page not look generated.

**The drawings are data, not assets.** `data/street.js` holds the geometry for
all twenty-four properties and both mains; `StreetPlan.jsx` renders it. Change
which house is on which feeder there and the elevation, the service runs, the
annotations and the probe readout all follow. There are no images anywhere in
the build — the paper grain is one inline `feTurbulence`.

**`StreetPlan` has four stages, and the page owns them.** The component is
pure; a route sets `stage` from a ScrollTrigger. 0 elevation, 1 mains, 2 the
feeder traced, 3 the closure disputed. Transitions are CSS on `data-stage`, so
the drawing can be rendered at any stage server-side or in a still.

**The RESOLVED stamp never animates.** It is a static SVG with a displacement
map, a noise mask and a blurred underprint. A stamp is something you find on
a page, not something that arrives. Animating a false closure would make it
look like a flourish, and the false closure is what the case turns on.

**The plan pans on phones, it does not shrink.** Below 900px the sheet keeps a
legible scale inside a horizontal scroller, the way paper slides on a table.
Shrinking twenty-four house numbers to four pixels is not responsive.

**Kannada, Hindi and Tamil are artifacts, not a translation layer.** They
appear where they truly belong — the masthead, the words a household actually
used, the printing on the form. `data/indic.js` holds them.

**Reduced motion is a real path, not a stylesheet afterthought.** Lenis does
not start, GSAP setups take a `reduced` flag and set their end state directly,
and every CSS transition collapses. The page must be complete on first paint.

## Data

The story pages (`/`, `/case`, `/street`, `/process`, `/about`) render
fixtures in `src/data/`, shaped after `core/types.py`. The statutory windows,
authorities and citations are real; the households are synthetic and the desks
are calibrated simulators. `CORRELATION.semantic_available` is `false` on
purpose and is surfaced in the UI — a cluster that hides which terms ran is
claiming agreement it never computed.

**Two things are live, and they say so on the page.** The intake line on `/`
sends a real report to the AgentCore runtime and replays the trace it wrote.
`/live/:caseId` reads that case back, shows the draft, and takes the
signature. Both go through `src/lib/api.js` to `POST /api`, and nothing else
fetches.

## Running against the real runtime

`/api` is `handlers/web_api.py`, one Lambda that serves `dist/` and forwards
to AgentCore, so the site and the API share an origin. Locally the same
handler runs on :8787 with your AWS profile:

```bash
python scripts/web_api_local.py   # from the repo root
cd web && npm run dev             # http://localhost:5173
```

Deploy with `scripts/deploy_web.ps1`. See `docs/deploy/WEB.md`.
