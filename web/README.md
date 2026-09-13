# Panchayat — the site

The public face of the case file. Five routes, one drawing, no UI library.

```bash
npm install
npm run dev      # vite, :5173
npm run build    # static output in dist/
npm run preview
npm run lint     # oxlint
```

## What is where

```
src/
  routes/      Index · Case · Street · Process · About
  components/  Masthead Footer StreetPlan HeroSection Document
               Stamp LegalClock Ladder ReportInput Icon Bits
  data/        case · street · authorities · indic
  styles/      reset · tokens · type · layout · paper · plan
               components · pages
  lib/         motion.js — Lenis + ScrollTrigger + reduced motion
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

Everything on these pages is a fixture in `src/data/`, shaped after
`core/types.py`. Nothing fetches. The statutory windows, authorities and
citations are real; the households are synthetic and the desks are calibrated
simulators. `CORRELATION.semantic_available` is `false` on purpose and is
surfaced in the UI — a cluster that hides which terms ran is claiming
agreement it never computed.
