import { PLAN, HOUSES, VALVES, FAULT, INLET, SUBJECT, CORROBORATING, DECOY } from '../data/street.js'

const { width: W, height: H, grade, chip, brace, mainA, mainB } = PLAN

const feederY = (f) => (f === 'A' ? mainA.y : mainB.y)

// Where a service drop leaves the property: below the feeder tag, so
// the two never sit on top of each other.
const DROP_TOP = chip + 16

/**
 * Ward 12, 4th Cross — water supply layout.
 *
 * Drawn rather than rendered: every line here is a decision about what
 * a survey sheet shows. Twenty-four properties in elevation, two mains
 * below grade, and the service connection that decides which of them
 * share a fault.
 *
 * The drawing has to be readable without tracing a hairline across a
 * metre of paper, so it says which feeder a house is on three separate
 * ways: a lettered tag under every door number, a lane band behind
 * each main, and — once the feeder is traced — everything off Main A
 * steps back so the family that matters is the one you see.
 *
 * Stages, set by the page rather than the drawing:
 *   0  elevation only — a street, in the order the door numbers run
 *   1  below grade — the two mains and every service drop appear
 *   2  the feeder is traced — three houses, not three neighbours
 *   3  the closure is disputed — the same three, still dry
 */
export default function StreetPlan({ stage = 3, probe = null, onProbe, id = 'plan' }) {
  const lit = new Set(CORROBORATING)

  const houseState = (h) => {
    if (probe === h.n) return 'probe'
    if (stage >= 2 && lit.has(h.n)) return stage >= 3 ? 'dispute' : 'claim'
    if (stage >= 2 && h.n === DECOY) return 'decoy'
    return 'plain'
  }

  const subject = HOUSES[SUBJECT - 1]
  const first = HOUSES[CORROBORATING[0] - 1]
  const last = HOUSES[CORROBORATING[CORROBORATING.length - 1] - 1]

  return (
    <svg
      className={`plan${onProbe ? ' plan--live' : ''}`}
      data-stage={stage}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Engineering layout of 4th Cross, Ward 12: twenty-four properties above grade, each tagged A or B for the water main it is connected to, and two distribution mains below grade. Numbers 9, 12 and 17 are on Main A. Number 11, next door to 12, is on Main B."
    >
      <defs>
        <pattern id={`${id}-hatch`} width="9" height="9" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
          <line x1="0" y1="0" x2="0" y2="9" stroke="var(--rule)" strokeWidth="1" />
        </pattern>
        <pattern id={`${id}-soil`} width="30" height="30" patternUnits="userSpaceOnUse">
          <circle cx="5" cy="7" r="0.9" fill="var(--rule-strong)" />
          <circle cx="20" cy="17" r="0.7" fill="var(--rule-strong)" />
          <circle cx="11" cy="25" r="0.6" fill="var(--rule-strong)" />
          <circle cx="26" cy="4" r="0.55" fill="var(--rule-strong)" />
        </pattern>
      </defs>

      {/* ---- plate furniture ------------------------------------ */}
      <g className="plan-plate">
        <rect x="10" y="10" width={W - 20} height={H - 20} fill="none" />
        <path d="M10 34 H34 M10 10 V34" className="plan-corner" />
        <path d={`M${W - 10} 34 H${W - 34} M${W - 10} 10 V34`} className="plan-corner" />
        <path d={`M10 ${H - 34} H34 M10 ${H - 10} V${H - 34}`} className="plan-corner" />
        <path d={`M${W - 10} ${H - 34} H${W - 34} M${W - 10} ${H - 10} V${H - 34}`} className="plan-corner" />
      </g>

      {/* ---- title block ---------------------------------------- */}
      <g className="plan-title" transform="translate(34 40)">
        <text className="plan-t1" y="0">WARD 12 · 4TH CROSS, DODDANEKKUNDI</text>
        <text className="plan-t2" y="18">WATER SUPPLY LAYOUT · ELEVATION + BURIED SERVICES</text>
        <text className="plan-t3" y="34">DRG. PNC-W12-01 · SHEET 1 OF 1 · N.T.S.</text>
      </g>

      {/* ---- legend: the drawing explains its own notation ------ */}
      <g className="plan-key" transform={`translate(${W - 364} 32)`}>
        <line className="key-a" x1="0" y1="0" x2="32" y2="0" />
        <text className="plan-t2" x="44" y="4">MAIN A · {mainA.spec} · INVERT {mainA.depth}</text>

        <line className="key-b" x1="0" y1="18" x2="32" y2="18" />
        <line className="key-b" x1="0" y1="23" x2="32" y2="23" />
        <text className="plan-t2" x="44" y="25">MAIN B · {mainB.spec} · INVERT {mainB.depth}</text>

        <g transform="translate(0 46)">
          <rect className="key-chip" x="0" y="-10" width="16" height="15" rx="2" />
          <text className="key-chip-t" x="8" y="1.4" textAnchor="middle">A</text>
          <text className="plan-t3" x="26" y="1.4">FEEDER TAG</text>
          <path className="key-valve" d="M150 -9 L164 1 L164 -9 L150 1 Z" />
          <text className="plan-t3" x="171" y="1.4">VALVE</text>
          <circle className="key-tee" cx="240" cy="-4" r="3.6" />
          <text className="plan-t3" x="250" y="1.4">SERVICE TEE</text>
        </g>
      </g>

      {/* ---- grade, soil, and a lane for each main -------------- */}
      <g className="plan-ground">
        <rect x="18" y={grade + 1} width={W - 36} height={H - grade - 30} fill={`url(#${id}-soil)`} opacity="0.5" />
        <rect x="18" y={grade + 1} width={W - 36} height="9" fill={`url(#${id}-hatch)`} opacity="0.7" />
        <rect className="lane" data-feeder="A" x="18" y={mainA.y - mainA.lane} width={W - 36} height={mainA.lane * 2} />
        <rect className="lane" data-feeder="B" x="18" y={mainB.y - mainB.lane} width={W - 36} height={mainB.lane * 2} />
        <line x1="18" y1={grade} x2={W - 18} y2={grade} className="plan-grade-line" pathLength="1" />
        {/* below the chip row, clear of the first door number */}
        <text className="plan-t3 plan-fgl" x="24" y={grade + 36}>FGL ± 0.00</text>
      </g>

      {/* ---- properties, in elevation --------------------------- */}
      <g className="plan-houses">
        {HOUSES.map((h) => {
          const st = houseState(h)
          const roof =
            h.roof === 'pitched'
              ? `M${h.x - 4} ${h.top} L${h.cx} ${h.top - 16} L${h.x + h.w + 4} ${h.top} Z`
              : `M${h.x - 4} ${h.top} H${h.x + h.w + 4} V${h.top - 5} H${h.x - 4} Z`

          return (
            <g
              key={h.n}
              className="house"
              data-state={st}
              data-feeder={h.feeder}
              tabIndex={onProbe ? 0 : -1}
              role={onProbe ? 'button' : undefined}
              aria-label={`Number ${h.door}, connected to Main ${h.feeder}`}
              onMouseEnter={onProbe ? () => onProbe(h.n) : undefined}
              onMouseLeave={onProbe ? () => onProbe(null) : undefined}
              onFocus={onProbe ? () => onProbe(h.n) : undefined}
              onBlur={onProbe ? () => onProbe(null) : undefined}
            >
              <rect className="house-hit" x={h.x - 6} y={h.top - 26} width={h.w + 12} height={h.h + 54} />
              <rect className="house-body" x={h.x} y={h.top} width={h.w} height={h.h} />
              <path className="house-roof" d={roof} />
              <rect className="house-detail" x={h.x + 6} y={h.top + 15} width={10} height={10} />
              <rect className="house-detail" x={h.x + h.w - 18} y={grade - 20} width={12} height={20} />
              {h.tank && (
                <g className="house-tank">
                  <rect x={h.cx - 9} y={h.top - (h.roof === 'pitched' ? 30 : 19)} width={18} height={13} />
                  <line
                    x1={h.cx}
                    y1={h.top - (h.roof === 'pitched' ? 17 : 6)}
                    x2={h.cx}
                    y2={h.top - (h.roof === 'pitched' ? 12 : 1)}
                  />
                </g>
              )}
              <text className="house-no" x={h.cx} y={grade - 7} textAnchor="middle">
                {String(h.n).padStart(2, '0')}
              </text>

              {/* the feeder tag — the whole drawing in one letter */}
              <g className="chip">
                <rect x={h.cx - 8} y={chip} width={16} height={15} rx="2" />
                <text x={h.cx} y={chip + 11.4} textAnchor="middle">
                  {h.feeder}
                </text>
              </g>
            </g>
          )
        })}

        {/* which house this file is about */}
        <g className="subject-flag">
          <path d={`M${subject.cx - 16} 126 V${subject.top - 16}`} />
          <text x={subject.cx - 16} y="116" textAnchor="middle">12/12 — THIS CASE</text>
        </g>
      </g>

      {/* ---- service connections -------------------------------- */}
      <g className="plan-services">
        {HOUSES.map((h, i) => {
          const y = feederY(h.feeder)
          const st = houseState(h)
          // A Main B service has to cross Main A to reach its own
          // feeder. The hop is the drawing convention for that, and
          // it is also the whole argument in one gesture.
          const d =
            h.feeder === 'B'
              ? `M${h.cx} ${DROP_TOP} V${mainA.y - 8} A 8 8 0 0 1 ${h.cx} ${mainA.y + 8} V${y}`
              : `M${h.cx} ${DROP_TOP} V${y}`
          return (
            <g
              key={h.n}
              className="service"
              data-state={st}
              data-feeder={h.feeder}
              style={{ '--i': i }}
            >
              <path className="service-line" d={d} pathLength="1" />
              <circle className="service-tee" cx={h.cx} cy={y} r="3.4" />
            </g>
          )
        })}
      </g>

      {/* ---- the two mains -------------------------------------- */}
      <g className="plan-mains">
        <g className="main" data-feeder="A">
          <line className="main-line" x1="18" y1={mainA.y} x2={W - 18} y2={mainA.y} pathLength="1" />
          <text className="plan-t3 main-label" x="26" y={mainA.y - 13}>
            MAIN A · 300 mm AC · INVERT {mainA.depth}
          </text>
        </g>

        {/* Main B is drawn as a double line: a different pipe class,
            legible as different even in one colour. */}
        <g className="main" data-feeder="B">
          <line className="main-line" x1="18" y1={mainB.y - 2.5} x2={W - 18} y2={mainB.y - 2.5} pathLength="1" />
          <line className="main-line" x1="18" y1={mainB.y + 2.5} x2={W - 18} y2={mainB.y + 2.5} pathLength="1" />
          <text className="plan-t3 main-label" x="26" y={mainB.y - 15}>
            MAIN B · 250 mm DI · INVERT {mainB.depth}
          </text>
        </g>

        <g className="plan-inlet">
          <path d={`M${INLET.x} ${mainA.y} h18 m-7 -5 l7 5 -7 5`} />
          <path d={`M${INLET.x} ${mainB.y} h18 m-7 -5 l7 5 -7 5`} />
          <text className="plan-t3" x={INLET.x + 2} y={mainB.y + 32}>
            {INLET.label}
          </text>
        </g>

        {VALVES.map((v) => {
          const y = feederY(v.feeder)
          return (
            <g key={v.id} className="valve" data-feeder={v.feeder} transform={`translate(${v.x} ${y})`}>
              <path d="M-9 -7 L9 7 L9 -7 L-9 7 Z" />
              <line x1="0" y1="0" x2="0" y2="-14" />
              <line x1="-5" y1="-14" x2="5" y2="-14" />
              <text className="plan-t3" y="23" textAnchor="middle">{v.id}</text>
            </g>
          )
        })}

        <g className="plan-fault" transform={`translate(${FAULT.x} ${mainA.y})`}>
          <circle r="16" />
          <path d="M-6 -6 L6 6 M6 -6 L-6 6" />
          <text className="plan-t3" y="-42" textAnchor="middle">{FAULT.note}</text>
        </g>
      </g>

      {/* ---- the annotation that carries the argument ----------- */}
      <g className="plan-argument">
        <g className="ann ann-cluster">
          <path
            className="ann-brace"
            pathLength="1"
            d={
              `M${first.cx} ${brace - 10} v10 ` +
              `M${first.cx} ${brace} H${last.cx} ` +
              `M${subject.cx} ${brace} v-10 ` +
              `M${last.cx} ${brace - 10} v10`
            }
          />
          <text x={(first.cx + last.cx) / 2} y={brace + 19} textAnchor="middle">
            09 · 12 · 17 — ONE FEEDER, ONE FAULT
          </text>
        </g>

        <g className="ann ann-decoy" transform={`translate(${HOUSES[DECOY - 1].cx} ${mainB.y})`}>
          <path d="M0 16 v28" className="ann-leader" />
          <text y="58" textAnchor="middle">
            11 — NEXT DOOR TO 12. CROSSES MAIN A. TEED INTO MAIN B. HAS WATER.
          </text>
        </g>
      </g>

      {/* ---- depth dimension ------------------------------------ */}
      <g className="plan-dim">
        <line x1={W - 30} y1={grade} x2={W - 30} y2={mainB.y} />
        <line x1={W - 36} y1={grade} x2={W - 24} y2={grade} />
        <line x1={W - 36} y1={mainA.y} x2={W - 24} y2={mainA.y} />
        <line x1={W - 36} y1={mainB.y} x2={W - 24} y2={mainB.y} />
        <text className="plan-t3" x={W - 42} y={(grade + mainA.y) / 2} textAnchor="end">1.54</text>
        <text className="plan-t3" x={W - 42} y={(mainA.y + mainB.y) / 2} textAnchor="end">2.70</text>
      </g>
    </svg>
  )
}
