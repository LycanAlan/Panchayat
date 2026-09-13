/**
 * Ward 12 — 4th Cross, Doddanekkundi. Water supply layout.
 *
 * Drawn as a survey elevation: twenty-four properties above grade,
 * two distribution mains below it. The point the drawing has to make
 * is that the two orderings disagree — door numbers run along the
 * street, but water runs along the feeder, and a household's
 * neighbour on the street is often a stranger to its main.
 */

export const PLAN = {
  width: 1600,
  height: 648,
  grade: 268, // finished ground level
  chip: 276, // feeder tag row, immediately below grade
  brace: 312, // where the cluster is bracketed
  mainA: { y: 404, lane: 26, label: 'MAIN A', spec: '300 mm AC · 1994', depth: '1.54 m' },
  mainB: { y: 508, lane: 26, label: 'MAIN B', spec: '250 mm DI · 2011', depth: '2.70 m' },
}

// Which feeder each property is connected to. Not the order you would
// guess from the door numbers, which is the entire point.
const FEEDER = {
  1: 'B', 2: 'B', 3: 'A', 4: 'B', 5: 'B', 6: 'A',
  7: 'B', 8: 'B', 9: 'A', 10: 'B', 11: 'B', 12: 'A',
  13: 'B', 14: 'B', 15: 'B', 16: 'B', 17: 'A', 18: 'B',
  19: 'B', 20: 'B', 21: 'A', 22: 'B', 23: 'B', 24: 'A',
}

// Roof forms, so the elevation reads as a street and not a bar chart.
const ROOF = {
  flat: [1, 4, 5, 8, 10, 13, 15, 16, 19, 20, 22, 23],
  pitched: [2, 3, 6, 9, 11, 12, 14, 17, 18, 21, 24],
  tank: [3, 9, 12, 17, 21, 6], // overhead sintex tanks, drawn on top
}

const HEIGHTS = [88, 104, 96, 72, 110, 92, 80, 118, 98, 86, 74, 102,
  90, 112, 78, 94, 100, 84, 108, 76, 96, 88, 114, 92]

const MARGIN = 56
const PITCH = (PLAN.width - MARGIN * 2) / 24

export const HOUSES = Array.from({ length: 24 }, (_, i) => {
  const n = i + 1
  const x = MARGIN + i * PITCH + 6
  const w = PITCH - 16
  const h = HEIGHTS[i]
  return {
    n,
    door: `12/${String(n).padStart(2, '0')}`,
    x,
    w,
    h,
    top: PLAN.grade - h,
    cx: x + w / 2,
    feeder: FEEDER[n],
    roof: ROOF.pitched.includes(n) ? 'pitched' : 'flat',
    tank: ROOF.tank.includes(n),
  }
})

export const byNumber = (n) => HOUSES.find((h) => h.n === n)

/** The household whose case this is. */
export const SUBJECT = 12

/** Households with live, unresolved claims on the same fault. */
export const CORROBORATING = [9, 12, 17]

/**
 * The house that makes the argument. Number 11 shares a wall with
 * Lakshmi at 12 and has water. It is on the other main.
 */
export const DECOY = 11

/** Isolation valves along the two feeders. */
export const VALVES = [
  { id: 'V-A1', feeder: 'A', x: byNumber(4).cx + 18 },
  { id: 'V-A2', feeder: 'A', x: byNumber(8).cx + 10 },
  { id: 'V-A3', feeder: 'A', x: byNumber(19).cx - 4 },
  { id: 'V-B1', feeder: 'B', x: byNumber(5).cx + 14 },
  { id: 'V-B2', feeder: 'B', x: byNumber(16).cx + 8 },
]

/** Where the fault was eventually traced to. */
export const FAULT = {
  feeder: 'A',
  x: byNumber(7).cx - 6,
  note: 'Air lock / partial blockage upstream of V-A2',
}

export const INLET = {
  x: 18,
  label: 'FROM CAUVERY STAGE IV · TK HALLI',
}
