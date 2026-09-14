/**
 * Section B–B through the carriageway outside 12/14, 4th Cross.
 *
 * The roads counterpart of the water section, drawn to the same sheet and
 * the same conventions. A Bengaluru street is built up in layers: a 40 mm
 * bituminous wearing course on a binder course, on a granular base, on a
 * sub-base, on the soil. The desk's fill sits in the top one. The failure is
 * two layers down, where standing water from a silted side drain has soaked
 * the base and washed out its fines — which is why the hole comes back.
 *
 * Layer thicknesses are exaggerated for legibility; the labels carry the
 * real ones. The bracket on the right is the whole argument, as it is on
 * the water sheet: what the ticket fixed is at the surface, and what failed
 * is below it.
 */

const G = 400 // finished road level
const BC = 440 // bottom of the wearing course
const DBM = 480 // bottom of the binder course
const WMM = 600 // bottom of the granular base
const GSB = 690 // bottom of the sub-base
const KERB = 262 // carriageway edge, road side of the drain
const ROAD = 322 // start of the carriageway proper

export default function RoadSection() {
  return (
    <svg
      className="sect"
      viewBox="0 0 700 880"
      role="img"
      aria-label="Section through the carriageway outside house 12/14 on 4th Cross: the gate and footpath, a silted side drain, and the road built up in layers from the bituminous surface down through the binder course, the granular base and the sub-base to the soil. A pothole cuts through the top two layers and holds water. The cold-mix fill placed on 11 September sat only in the surface layer and washed out on 12 September. Below the hole the base is saturated and has lost its fines. A bracket marks the surface as what the ticket fixed and the base below as what actually failed."
    >
      <defs>
        <pattern id="rd-poche" width="6" height="6" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
          <line x1="0" y1="0" x2="0" y2="6" stroke="var(--rule-strong)" strokeWidth="1.1" />
        </pattern>
        <pattern id="rd-bc" width="5" height="5" patternTransform="rotate(-45)" patternUnits="userSpaceOnUse">
          <line x1="0" y1="0" x2="0" y2="5" stroke="var(--ink-muted)" strokeWidth="1.1" />
        </pattern>
        <pattern id="rd-dbm" width="9" height="9" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="3" r="1" fill="var(--ink-faint)" />
          <circle cx="6.5" cy="7" r="0.8" fill="var(--ink-faint)" />
        </pattern>
        <pattern id="rd-wmm" width="18" height="16" patternUnits="userSpaceOnUse">
          <circle cx="4" cy="4" r="2.4" fill="none" stroke="var(--rule-strong)" strokeWidth="0.9" />
          <circle cx="13" cy="11" r="1.8" fill="none" stroke="var(--rule-strong)" strokeWidth="0.9" />
        </pattern>
        <pattern id="rd-gsb" width="22" height="20" patternUnits="userSpaceOnUse">
          <circle cx="6" cy="6" r="1.2" fill="var(--rule-strong)" />
          <circle cx="16" cy="14" r="1" fill="var(--rule-strong)" />
        </pattern>
        <pattern id="rd-soil" width="26" height="26" patternUnits="userSpaceOnUse">
          <circle cx="4" cy="6" r="0.85" fill="var(--rule-strong)" />
          <circle cx="17" cy="16" r="0.7" fill="var(--rule-strong)" />
          <circle cx="9" cy="22" r="0.6" fill="var(--rule-strong)" />
        </pattern>
        <clipPath id="rd-road">
          {/* everything outside the hole: the layers stop where the pothole is cut */}
          <path d={`M${ROAD} ${G} H420 L432 422 L440 452 L462 500 L492 522 L540 518 L566 492 L576 450 L582 ${G} H682 V846 H${ROAD} Z`} />
        </clipPath>
      </defs>

      {/* ---- sheet furniture ---- */}
      <g className="sect-plate">
        <path d="M8 30 H30 M8 8 V30" />
        <path d="M692 30 H670 M692 8 V30" />
        <path d="M8 850 H30 M8 872 V850" />
        <path d="M692 850 H670 M692 872 V850" />
      </g>
      <text className="sect-t1" x="26" y="40">SECTION B–B · CARRIAGEWAY AT 12/14</text>
      <text className="sect-t3" x="26" y="56">ROAD BUILD-UP · DRG. PNC-W12-R4 · 12 SEP 2026</text>

      {/* ---- rain, the night before ---- */}
      <g className="sect-rain" style={{ '--d': '0.1s' }}>
        {[380, 430, 480, 530, 580, 630].map((x, i) => (
          <path key={x} className="draw thin" pathLength="1" d={`M${x} ${110 + (i % 2) * 18} l-10 26`} />
        ))}
        <text className="sect-t3 sect-halo" x="392" y="96">RAIN · 11–12 SEP</text>
      </g>

      {/* ---- the plot edge: wall, gate, footpath ---- */}
      <g className="sect-shell" style={{ '--d': '0.3s' }}>
        <rect className="poche" x="40" y="236" width="18" height={G - 236} />
        <path className="draw thin" pathLength="1" d="M58 262 H196 M58 392 H196" />
        {[78, 98, 118, 138, 158, 178].map((x) => (
          <path key={x} className="draw thin" pathLength="1" d={`M${x} 262 V392`} />
        ))}
        <rect className="draw" pathLength="1" x="196" y="236" width="14" height={G - 236} />
        <text className="sect-t2 sect-halo" x="66" y="226">GATE · 12/14</text>
        {/* footpath slab over the drain */}
        <rect className="poche" x="40" y="392" width={KERB - 40} height="8" />
        <rect className="poche" x={KERB - 10} y="378" width="10" height="30" />
        <text className="sect-t3 sect-halo" x="60" y="420">FOOTPATH</text>
      </g>

      {/* ---- side drain, silted ---- */}
      <g className="sect-drain" style={{ '--d': '0.5s' }}>
        <path className="draw" pathLength="1" d={`M${KERB} ${G} V470 H${ROAD} V${G}`} />
        <path className="sect-empty" d={`M${KERB + 6} 452 H${ROAD - 6}`} />
        <rect className="fade" x={KERB + 2} y="452" width={ROAD - KERB - 4} height="16" fill="url(#rd-soil)" />
        <text className="sect-t3 sect-halo" x="232" y="492" textAnchor="middle">SIDE DRAIN</text>
        <text className="sect-t3 sect-halo bad" x="232" y="506" textAnchor="middle">SILTED · WATER STANDS</text>
      </g>

      {/* ---- the road, in layers ---- */}
      <g className="sect-ground" style={{ '--d': '0.15s' }}>
        <rect className="fade" x="18" y={G} width={ROAD - 18 - (ROAD - KERB)} height={846 - G} fill="url(#rd-soil)" opacity="0.45" />
        <g clipPath="url(#rd-road)">
          <rect className="fade" x={ROAD} y={G} width={682 - ROAD} height={BC - G} fill="url(#rd-bc)" />
          <rect className="fade" x={ROAD} y={BC} width={682 - ROAD} height={DBM - BC} fill="url(#rd-dbm)" />
          <rect className="fade" x={ROAD} y={DBM} width={682 - ROAD} height={WMM - DBM} fill="url(#rd-wmm)" />
          <rect className="fade" x={ROAD} y={WMM} width={682 - ROAD} height={GSB - WMM} fill="url(#rd-gsb)" />
          <rect className="fade" x={ROAD} y={GSB} width={682 - ROAD} height={846 - GSB} fill="url(#rd-soil)" opacity="0.5" />
        </g>
        <path className="draw heavy" pathLength="1" d={`M18 ${G} H${KERB} M${ROAD} ${G} H420 M582 ${G} H682`} />
        <path className="draw thin" pathLength="1" d={`M${ROAD} ${BC} H682 M${ROAD} ${DBM} H682 M${ROAD} ${WMM} H682 M${ROAD} ${GSB} H682`} />
        <text className="sect-t3 sect-halo" x="24" y={G + 44}>FRL ± 0.00</text>
      </g>

      {/* ---- layer schedule ---- */}
      <g className="sect-layers" style={{ '--d': '0.7s' }}>
        <text className="sect-t3 sect-halo" x={ROAD + 8} y={G + 25}>BC 40</text>
        <text className="sect-t3 sect-halo" x={ROAD + 8} y={BC + 25}>DBM 50</text>
        <text className="sect-t3 sect-halo" x={ROAD + 8} y={DBM + 34}>WMM 250</text>
        <text className="sect-t3 sect-halo" x={ROAD + 8} y={WMM + 34}>GSB 200</text>
        <text className="sect-t3 sect-halo" x={ROAD + 8} y={GSB + 34}>SUBGRADE</text>
        <text className="sect-t3 sect-halo" x={ROAD + 8} y={GSB + 48}>LAYERS IN mm</text>
      </g>

      {/* ---- the pothole ---- */}
      <g className="sect-hole" style={{ '--d': '1.0s' }}>
        <path
          className="draw heavy"
          pathLength="1"
          d={`M420 ${G} L432 422 L440 452 L462 500 L492 522 L540 518 L566 492 L576 450 L582 ${G}`}
        />
        {/* standing water, the reason nobody can see how deep it is */}
        <path className="draw pipe" pathLength="1" d={`M424 ${G + 12} H578`} />
        <text className="sect-t2 sect-halo" x="404" y="330">POTHOLE P-1</text>
        <text className="sect-t3 sect-halo" x="404" y="345">450 × 300 · 90 mm DEEP</text>
        <text className="sect-t3 sect-halo bad" x="404" y="359">FULL OF WATER</text>
        <path className="sect-lead" pathLength="1" d={`M500 366 V${G + 10}`} />
      </g>

      {/* ---- the fill that was, and is not ---- */}
      <g className="sect-fill" style={{ '--d': '1.3s' }}>
        <path className="sect-empty" d={`M424 ${G + 2} H580 L572 ${BC - 6} H430 Z`} />
        <text className="sect-t3 sect-halo bad" x="120" y="560">COLD-MIX FILL · 11 SEP</text>
        <text className="sect-t3 sect-halo bad" x="120" y="574">SURFACE COURSE ONLY</text>
        <text className="sect-t3 sect-halo bad" x="120" y="588">WASHED OUT · 12 SEP</text>
        <path className="sect-lead" pathLength="1" d="M236 556 L426 430" />
      </g>

      {/* ---- water into the base ---- */}
      <g className="sect-seep" style={{ '--d': '1.55s' }}>
        <path className="draw pipe" pathLength="1" d={`M${ROAD - 4} 462 C360 470 400 520 462 548`} strokeDasharray="4 4" />
        <path className="sect-empty" d="M438 540 C470 590 560 596 600 548" />
        <text className="sect-t3 sect-halo bad" x="120" y="640">WMM BASE SATURATED</text>
        <text className="sect-t3 sect-halo bad" x="120" y="654">FINES WASHED OUT</text>
        <path className="sect-lead" pathLength="1" d="M226 636 L452 586" />
      </g>

      {/* ---- the fault ---- */}
      <g className="sect-fault" style={{ '--d': '1.85s' }} transform="translate(512 568)">
        <circle r="19" />
        <path d="M-7 -7 L7 7 M7 -7 L-7 7" />
        <text className="sect-t3 sect-halo" y="44" textAnchor="middle">BASE FAILURE · UNDER P-1</text>
      </g>

      {/* ---- the bracket that makes the point ---- */}
      <g className="sect-bracket" style={{ '--d': '2.1s' }}>
        <path className="bracket-seen" d={`M636 250 H646 V${BC} H636`} />
        <text className="sect-t2 seen" x="666" y="345" transform="rotate(-90 666 345)" textAnchor="middle">
          WHAT THE TICKET FIXED
        </text>

        <path className="bracket-unseen" d={`M636 ${BC + 6} H646 V812 H636`} />
        <text className="sect-t2 unseen" x="666" y="630" transform="rotate(-90 666 630)" textAnchor="middle">
          WHAT ACTUALLY FAILED
        </text>
      </g>
    </svg>
  )
}
