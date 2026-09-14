/**
 * Section A–A through 12/12, 4th Cross.
 *
 * The drawing follows the water rather than the architecture, because
 * the water is what the case is about. In a Bengaluru house the chain
 * is: distribution main → ferrule → meter at the boundary → sump under
 * the yard → pump → overhead tank → tap. Six links, and a household
 * can see exactly one of them.
 *
 * Every link is labelled with its state on the sixth of September. The
 * bracket on the right is the whole argument: what a household can see
 * is above the grade line, and what failed is below it.
 */

import RoadSection from './RoadSection.jsx'
import { useScenario } from '../lib/scenario.jsx'

const G = 470 // finished ground level
const MAIN = 790 // invert of Main A
const L = 150 // left wall, outer face
const R = 470 // right wall, outer face
const T = 14 // wall thickness

export default function HeroSection() {
  // The pothole case has its own section through the road, drawn to the
  // same sheet. Water keeps this one.
  const { scenario } = useScenario()
  if (scenario.hero === 'roads') return <RoadSection />

  return (
    <svg
      className="sect"
      viewBox="0 0 700 880"
      role="img"
      aria-label="Section through house 12/12 following the water supply: Main A below the road, a ferrule up to the meter chamber at the property line, into the underground sump, pumped up an external riser to the overhead tank on the roof, and back down to a tap. On 6 September the sump, the pump and the tank are all empty, and the fault is an air lock on the main. A bracket marks everything above ground as what a household can see and everything below as what failed."
    >
      <defs>
        {/* poché: the convention for anything the section cuts through */}
        <pattern
          id="sect-poche"
          width="6"
          height="6"
          patternTransform="rotate(45)"
          patternUnits="userSpaceOnUse"
        >
          <line x1="0" y1="0" x2="0" y2="6" stroke="var(--rule-strong)" strokeWidth="1.1" />
        </pattern>
        <pattern id="sect-soil" width="26" height="26" patternUnits="userSpaceOnUse">
          <circle cx="4" cy="6" r="0.85" fill="var(--rule-strong)" />
          <circle cx="17" cy="16" r="0.7" fill="var(--rule-strong)" />
          <circle cx="9" cy="22" r="0.6" fill="var(--rule-strong)" />
        </pattern>
      </defs>

      {/* ---- sheet furniture ---- */}
      <g className="sect-plate">
        <path d="M8 30 H30 M8 8 V30" />
        <path d="M692 30 H670 M692 8 V30" />
        <path d="M8 850 H30 M8 872 V850" />
        <path d="M692 850 H670 M692 872 V850" />
      </g>
      <text className="sect-t1" x="26" y="40">SECTION A–A · HOUSE 12/12</text>
      <text className="sect-t3" x="26" y="56">WATER PATH · DRG. PNC-W12-04 · 06 SEP 2026</text>

      {/* ---- ground ---- */}
      <g className="sect-ground" style={{ '--d': '0.15s' }}>
        <rect className="fade" x="18" y={G + 1} width="664" height={846 - G} fill="url(#sect-soil)" opacity="0.5" />
        <path className="draw heavy" pathLength="1" d={`M18 ${G} H682`} />
        <rect className="fade" x="18" y={G + 1} width="664" height="8" fill="url(#sect-poche)" opacity="0.55" />
        <text className="sect-t3 sect-halo" x="24" y={G - 9}>FGL ± 0.00</text>
      </g>

      {/* ---- the shell, cut ---- */}
      <g className="sect-shell" style={{ '--d': '0.3s' }}>
        {/* walls */}
        <rect className="poche" x={L} y="180" width={T} height={G - 180} />
        <rect className="poche" x={R - T} y="180" width={T} height={G - 180} />
        {/* slabs: roof, intermediate, ground */}
        <rect className="poche" x={L} y="208" width={R - L} height="12" />
        <rect className="poche" x={L} y="340" width={R - L} height="12" />
        <rect className="poche" x={L} y={G} width={R - L} height="14" />
        {/* parapet returns */}
        <path className="draw thin" pathLength="1" d={`M${L} 180 H${L + T} M${R - T} 180 H${R}`} />
      </g>

      {/* ---- overhead tank ---- */}
      <g className="sect-oht" style={{ '--d': '0.66s' }}>
        <path className="draw thin" pathLength="1" d="M268 208 V160 M352 208 V160" />
        <rect className="draw" pathLength="1" x="250" y="108" width="120" height="52" rx="3" />
        <rect className="draw thin" pathLength="1" x="298" y="100" width="24" height="8" />
        <path className="sect-empty" d="M256 154 H364" />
        <text className="sect-t2 sect-halo bad" x="500" y="126">OHT · 1000 L</text>
        <text className="sect-t3 sect-halo bad" x="500" y="141">EMPTY SINCE 04 SEP</text>
      </g>

      {/* ---- below grade: meter, sump, pump ---- */}
      <g className="sect-below" style={{ '--d': '0.95s' }}>
        <path className="sect-boundary" pathLength="1" d="M112 330 V812" />
        <text
          className="sect-t3 sect-halo"
          x="102"
          y="404"
          textAnchor="middle"
          transform="rotate(-90 102 404)"
        >
          PROPERTY LINE
        </text>

        {/* meter chamber */}
        <rect className="draw thin" pathLength="1" x="76" y="490" width="72" height="56" />
        <circle className="draw thin" pathLength="1" cx="112" cy="518" r="12" />
        <path className="draw thin" pathLength="1" d="M112 518 L118 511" />
        <text className="sect-t3 sect-halo" x="112" y="570" textAnchor="middle">METER</text>
        <text className="sect-t3 sect-halo bad" x="112" y="584" textAnchor="middle">0 kL SINCE 04 SEP</text>

        {/* sump */}
        <rect className="draw" pathLength="1" x="190" y="530" width="170" height="110" />
        <rect className="draw thin" pathLength="1" x="198" y="538" width="154" height="94" />
        <path className="sect-empty" d="M204 624 H346" />
        <text className="sect-t3 sect-halo" x="275" y="572" textAnchor="middle">SUMP · 4000 L</text>
        <text className="sect-t3 sect-halo bad" x="275" y="586" textAnchor="middle">EMPTY SINCE 04 SEP</text>

        {/* pump */}
        <rect className="draw thin" pathLength="1" x="392" y="556" width="48" height="38" />
        <circle className="draw thin" pathLength="1" cx="416" cy="575" r="11" />
        <path className="draw thin" pathLength="1" d="M388 594 H444 M392 594 v8 M440 594 v8" />
        <text className="sect-t3 sect-halo" x="500" y="572">PUMP · 0.5 HP</text>
        <text className="sect-t3 sect-halo bad" x="500" y="586">DRY-RUNNING · CUT OUT</text>
        <path className="sect-lead" pathLength="1" d="M446 580 H494" />
      </g>

      {/* ---- the pipework, main to tap ---- */}
      <g className="sect-pipe" style={{ '--d': '1.25s' }}>
        {/* 1 · ferrule off the main, up to the meter */}
        <path className="draw pipe" pathLength="1" d={`M112 ${MAIN} V546`} />
        <circle className="sect-ferrule" cx="112" cy={MAIN} r="5" />
        <text className="sect-t3 sect-halo" x="126" y="700">FERRULE · 20 mm MDPE</text>

        {/* 2 · meter out into the sump */}
        <path className="draw pipe" pathLength="1" d="M148 518 H230 V530" />

        {/* 3 · suction, sump to pump */}
        <path className="draw pipe" pathLength="1" d="M360 620 H392" />

        {/* 4 · delivery: up the external riser to the tank */}
        <path className="draw pipe" pathLength="1" d="M424 556 V500 H482 V134 H370" />
        <text className="sect-t3 sect-halo" x="500" y="300">RISER · 25 mm</text>
        <path className="sect-lead" pathLength="1" d="M486 296 H494" />

        {/* 5 · tank down to the tap */}
        <path className="draw pipe" pathLength="1" d="M290 160 V396 H252" />

        {/* the tap, and the sink under it */}
        <g className="sect-tap">
          <path className="draw thin" pathLength="1" d="M252 390 h-18 v12 h18 z" />
          <path className="draw thin" pathLength="1" d="M234 396 h-12 v14" />
          <path className="draw thin" pathLength="1" d="M243 390 v-8 m-6 -8 h12" />
          <path className="sect-drip" d="M222 420 c0 1.8 -1.4 3.2 -3 3.2 s-3 -1.4 -3 -3.2 c0 -1.9 3 -5.2 3 -5.2 s3 3.3 3 5.2 z" />
          <path className="draw thin" pathLength="1" d="M196 428 h48 l-6 16 h-36 z" />
        </g>
        <text className="sect-t2 sect-halo" x="268" y="418">TAP</text>
        <text className="sect-t3 sect-halo" x="268" y="433">THE ONLY PART SHE SEES</text>
      </g>

      {/* ---- the main ---- */}
      <g className="sect-main" style={{ '--d': '1.55s' }}>
        <path className="draw main" pathLength="1" d={`M18 ${MAIN} H682`} />
        <text className="sect-t2 sect-halo" x="26" y={MAIN + 30}>MAIN A · 300 mm AC · LAID 1994</text>
        <text className="sect-t3 sect-halo" x="26" y={MAIN + 46}>SHARED WITH 12/09 AND 12/17</text>
      </g>

      {/* ---- the fault ---- */}
      <g className="sect-fault" style={{ '--d': '1.85s' }} transform={`translate(560 ${MAIN})`}>
        <circle r="19" />
        <path d="M-7 -7 L7 7 M7 -7 L-7 7" />
        <text className="sect-t3 sect-halo" y="-30" textAnchor="middle">AIR LOCK · UPSTREAM OF V-A2</text>
      </g>

      {/* ---- storey heights, in the left margin ---- */}
      <g className="sect-dim" style={{ '--d': '1.95s' }}>
        <path d="M60 160 V470" />
        <path d="M52 160 h16 M52 208 h16 M52 340 h16 M52 470 h16" />
        <text className="sect-t3" x="48" y="409" textAnchor="end">3.00</text>
        <text className="sect-t3" x="48" y="278" textAnchor="end">3.00</text>
        <text className="sect-t3" x="48" y="188" textAnchor="end">1.10</text>
      </g>

      {/* ---- the bracket that makes the point ---- */}
      <g className="sect-bracket" style={{ '--d': '2.1s' }}>
        <path className="bracket-seen" d={`M636 104 H646 V${G - 6} H636`} />
        <text className="sect-t2 seen" x="666" y="290" transform="rotate(-90 666 290)" textAnchor="middle">
          WHAT SHE CAN SEE
        </text>

        <path className="bracket-unseen" d={`M636 ${G + 6} H646 V812 H636`} />
        <text className="sect-t2 unseen" x="666" y="644" transform="rotate(-90 666 644)" textAnchor="middle">
          WHAT ACTUALLY FAILED
        </text>
      </g>
    </svg>
  )
}
