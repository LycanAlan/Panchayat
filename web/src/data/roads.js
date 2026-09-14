/**
 * Case PNC-2026-0914 — the pothole outside 12/14, 4th Cross.
 *
 * The second worked example, shaped exactly like case.js so every page can
 * tell either story with the same template. Households are synthetic and the
 * ward desk is a calibrated simulator. The authorities, the ladder and the
 * citations mirror data/jurisdiction/ward12.yaml, which is what the runtime
 * actually routes a roads report with — read against the Bruhat Bengaluru
 * Mahanagara Palike Act, 2020.
 *
 * One thing is said plainly because it differs from water: there is no
 * statutory day count for a pothole at ward level. The seven days is BBMP's
 * own stated turnaround, used as the chase window, and labelled as such.
 */

import { HOUSES as WATER_HOUSES, PLAN as WATER_PLAN } from './street.js'

export const CASE = {
  id: 'PNC-2026-0914',
  opened: '2026-09-05',
  ward: 12,
  ward_name: 'Doddanekkundi',
  street: '4th Cross, Doddanekkundi',
  subject: 'Road defect — pothole on the carriageway outside 12/14',
  household: { id: 'HH-12-0014', door: '12/14', name: 'Ramesh' },
  status: 'DISPUTED',
  tier: 2,
}

export const FILING = {
  ref: 'WARD-100001',
  authority: 'BBMP Assistant Engineer, Ward 12 office',
  channel: 'Ward grievance counter',
  filed: '2026-09-05T09:40:00+05:30',
  rule: 'Bruhat Bengaluru Mahanagara Palike Act, 2020 — s.211(1)',
  window_days: 7,
  due: '2026-09-12',
  signed_by: 'Ramesh',
  signed_at: '2026-09-05T09:31:00+05:30',
}

export const TIMELINE = [
  {
    date: '05 SEP',
    time: '07:50',
    tone: 'plain',
    head: 'Reported',
    body: 'The patch from June has lifted again after two days of rain. Reported in Kannada, by voice note, to the street.',
    ref: 'CLM-5102',
  },
  {
    date: '05 SEP',
    time: '08:02',
    tone: 'plain',
    head: 'Jurisdiction resolved',
    body: 'A defect in the carriageway of a public street. BBMP. Not BWSSB, though the hole is full of water.',
    ref: 'JUR-BBMP-RD-04',
  },
  {
    date: '05 SEP',
    time: '09:31',
    tone: 'plain',
    head: 'Signed',
    body: 'Draft read back in Kannada. Approved by name before anything left the household.',
    ref: 'SIG-0914-A',
  },
  {
    date: '05 SEP',
    time: '09:40',
    tone: 'open',
    head: 'Filed',
    body: 'Lodged at the Ward 12 office. Ticket WARD-100001 issued. Chase window opens.',
    ref: 'WARD-100001',
  },
  {
    date: '08 SEP',
    time: '—',
    tone: 'plain',
    head: 'Day 3 of 7',
    body: 'No site visit recorded. Two further households on 4th Cross report the same hole.',
    ref: 'CLM-5117 · CLM-5123',
  },
  {
    date: '11 SEP',
    time: '16:40',
    tone: 'closed',
    head: 'Desk marks the ticket resolved',
    body: 'WARD-100001 closed. Remark: “Pothole filled. Complaint closed.” A cold-mix fill; no work order attached.',
    ref: 'WARD-100001',
  },
  {
    date: '12 SEP',
    time: '06:10',
    tone: 'plain',
    head: 'Open again',
    body: 'Rain overnight. The fill has washed out and the hole is back to its old depth.',
    ref: 'CLM-5102',
  },
  {
    date: '12 SEP',
    time: '09:40',
    tone: 'breach',
    head: 'Deadline missed',
    body: 'Window expired with the hole open. The Watchdog wakes on the clock, not on a reply.',
    ref: 'SLA-BREACH',
  },
  {
    date: '12 SEP',
    time: '09:40',
    tone: 'breach',
    head: 'Escalated',
    body: 'Case climbs to tier 2 — Executive Engineer, BBMP zonal office. Tier-1 record carried forward.',
    ref: 'PNC-2026-0914/T2',
  },
  {
    date: '12 SEP',
    time: '09:44',
    tone: 'breach',
    head: 'Closure disputed',
    body: 'Three live claims contradict the closure. The case does not close on the desk’s word.',
    ref: 'DISPUTED',
  },
]

export const CLAIMS = [
  { id: 'CLM-5102', house: 14, at: '05 SEP 07:50', text: 'Pothole outside our gate. Closed three times, open again.' },
  { id: 'CLM-5117', house: 8, at: '08 SEP 07:15', text: 'My son fell off his scooter in it last night.' },
  { id: 'CLM-5123', house: 20, at: '08 SEP 18:05', text: 'Autos swerve into our gate to miss it. After rain you cannot see it.' },
]

/** Same renormalisation as water: semantic did not run, so it is dropped. */
export const CORRELATION = {
  tau: 0.72,
  score: 0.93,
  semantic_available: false,
  components: [
    { name: 'topology', weight: 0.4, value: 1.0, ran: true, note: 'same street · bbmp-rd-4thcross' },
    { name: 'recency', weight: 0.25, value: 0.81, ran: true, note: 'within 120 h' },
    { name: 'semantic', weight: 0.35, value: null, ran: false, note: 'embedding unavailable' },
  ],
  renormalised_over: ['topology', 'recency'],
  decoy: {
    house: 13,
    score: 0.4,
    note: 'shares a wall, gate on 5th Cross — topology 0.15',
  },
}

export const CONTRADICTION = {
  desk: {
    ref: 'WARD-100001',
    stamped: '11 SEP 2026',
    remark: 'Pothole filled. Complaint closed.',
    work_order: null,
  },
  street: {
    live_claims: 3,
    latest: '12 SEP 06:10',
    houses: [8, 14, 20],
  },
  verdict: 'DISPUTED · watchdog → 3 live claim(s) contradict closure',
}

/** Mirrors the bbmp_roads ladder in data/jurisdiction/ward12.yaml. */
export const LADDER = [
  {
    tier: 0,
    body: 'Resident Welfare Association',
    office: '4th Cross RWA, Doddanekkundi',
    window: null,
    citation: 'No statutory duty. Courtesy notification only.',
    state: 'informed',
    note: 'Told, not filed against. An RWA cannot be in breach of a window it does not hold.',
  },
  {
    tier: 1,
    body: 'BBMP — Assistant Engineer',
    office: 'Ward 12 office, Doddanekkundi',
    window: '7 days · BBMP’s stated turnaround, not a statute',
    citation: 'BBMP Act, 2020 · s.211(1) — streets to be levelled and repaired',
    state: 'breached',
    note: 'Filed 05 SEP. Closed 11 SEP on a cold-mix fill. Open again 12 SEP.',
  },
  {
    tier: 2,
    body: 'BBMP — Executive Engineer',
    office: 'Zonal office, Mahadevapura',
    window: '7 days',
    citation: 'BBMP Act, 2020 · s.210(3) — public streets under the Zonal Commissioner',
    state: 'current',
    note: 'Case climbed here on the breach, carrying the tier-1 record forward.',
  },
  {
    tier: 3,
    body: 'BBMP — Grievance Redressal Authority',
    office: 'Quasi-judicial authority under the Act',
    window: '90 days · s.369(4)(a)',
    citation: 'BBMP Act, 2020 · s.368 — a grievance includes maintenance of road',
    state: 'pending',
    note: '₹250 a day, up to ₹25,000, on an officer who wilfully neglected the duty.',
  },
  {
    tier: 4,
    body: 'RTI application',
    office: 'Public Information Officer, BBMP',
    window: '30 days',
    citation: 'Right to Information Act, 2005 · s.6',
    state: 'pending',
    note: 'Asks for the work order and site photographs behind the closure. A household files it; Panchayat drafts.',
  },
]

export const NOT_THESE = [
  {
    body: 'BWSSB',
    reason: 'Owns the water mains under the road, not the carriageway. A hole full of water is still a road defect.',
  },
  {
    body: 'BESCOM',
    reason: 'Supplies power to the street lights along the kerb. The road surface is not theirs.',
  },
  {
    body: 'Karnataka PWD',
    reason: 'Builds and maintains state highways. A ward cross street is BBMP’s.',
  },
]

export const JURISDICTION_NOTE =
  'Four curated road segments for this ward, beside thirty-one water entries. Every routing ' +
  'decision returns a citation or returns nothing. A pothole on any other street is answered ' +
  '“not routable here” rather than sent to a plausible office.'

export const REPORT = {
  kn: 'ಮನೆ ಮುಂದೆ ರಸ್ತೆ ಗುಂಡಿ. ಮೂರು ಬಾರಿ ಮುಚ್ಚಿದರು, ಮತ್ತೆ ತೆರೆದುಕೊಂಡಿದೆ.',
  gloss: 'A pothole in front of the house. They closed it three times; it has opened again.',
  by: 'Ramesh · 12/14 · voice note, 07:50',
}

export const VOICES = [
  {
    script: 'kn',
    tag: 'ಕನ್ನಡ',
    text: 'ರಾತ್ರಿ ಗುಂಡಿ ಕಾಣಿಸುವುದಿಲ್ಲ. ನನ್ನ ಮಗ ಸ್ಕೂಟರ್‌ನಿಂದ ಬಿದ್ದ.',
    gloss: 'You cannot see the hole at night. My son fell off his scooter.',
    house: '12/08',
  },
  {
    script: 'ta',
    tag: 'தமிழ்',
    text: 'மழை பெய்தால் குழி தெரியாது. ஆட்டோக்கள் எங்கள் வாசலுக்குள் திரும்புகின்றன.',
    gloss: 'When it rains you cannot see the hole. Autos swerve into our gate.',
    house: '12/20',
  },
  {
    script: 'hi',
    tag: 'हिन्दी',
    text: 'हमारे गेट के बाहर सड़क ठीक है। हमारा गेट पाँचवीं क्रॉस पर खुलता है।',
    gloss: 'The road outside our gate is fine. Our gate opens onto 5th Cross.',
    house: '12/13',
    decoy: true,
  },
]

// ---------------------------------------------------------------- drawing

/**
 * Which street each plot's gate opens onto. The row sits back to back
 * between 4th Cross (A) and 5th Cross (B), so a neighbour through the wall
 * can use a different road every day. Same geometry as the water sheet;
 * only the tag, and what it means, changes.
 */
const FRONTAGE = {
  1: 'B', 2: 'A', 3: 'B', 4: 'B', 5: 'A', 6: 'B',
  7: 'B', 8: 'A', 9: 'B', 10: 'B', 11: 'A', 12: 'B',
  13: 'B', 14: 'A', 15: 'B', 16: 'A', 17: 'B', 18: 'B',
  19: 'B', 20: 'A', 21: 'B', 22: 'B', 23: 'A', 24: 'B',
}

const HOUSES = WATER_HOUSES.map((h) => ({ ...h, feeder: FRONTAGE[h.n] }))
const byNumber = (n) => HOUSES.find((h) => h.n === n)

export const DRAWING = {
  PLAN: {
    ...WATER_PLAN,
    mainA: { ...WATER_PLAN.mainA, label: 'ROAD A', spec: '4TH CROSS · BC 40 mm · RELAID 2019', depth: '6.0 m' },
    mainB: { ...WATER_PLAN.mainB, label: 'ROAD B', spec: '5TH CROSS · BC 40 mm · RELAID 2021', depth: '7.5 m' },
  },
  HOUSES,
  byNumber,
  SUBJECT: 14,
  CORROBORATING: [8, 14, 20],
  DECOY: 13,
  VALVES: [],
  FAULT: {
    feeder: 'A',
    x: byNumber(14).cx + 22,
    note: 'POTHOLE P-1 · 450 × 300 × 90 mm · FILLED 3× SINCE JUNE',
  },
  INLET: { x: 18, label: 'TRAFFIC FROM OUTER RING ROAD' },
  text: {
    aria:
      'Road access layout of 4th Cross, Ward 12: twenty-four properties above grade, each tagged A or B for the street its gate opens onto, and the two carriageways below. Numbers 8, 14 and 20 open onto 4th Cross, where the pothole is. Number 13, next door to 14, opens onto 5th Cross.',
    t1: 'WARD 12 · 4TH CROSS, DODDANEKKUNDI',
    t2: 'ROAD ACCESS LAYOUT · ELEVATION + CARRIAGEWAYS (SCHEMATIC)',
    t3: 'DRG. PNC-W12-R1 · SHEET 1 OF 1 · N.T.S.',
    keyA: 'ROAD A · 4TH CROSS · WIDTH 6.0 m',
    keyB: 'ROAD B · 5TH CROSS · WIDTH 7.5 m',
    chip: 'FRONTAGE TAG',
    valve: null,
    tee: 'GATE',
    subject: '12/14 — THIS CASE',
    mainA: 'ROAD A · 4TH CROSS CARRIAGEWAY · BBMP',
    mainB: 'ROAD B · 5TH CROSS CARRIAGEWAY · BBMP',
    cluster: '08 · 14 · 20 — ONE ROAD, ONE HOLE',
    decoy: '13 — NEXT DOOR TO 14. GATE ON 5TH CROSS. NO HOLE OUTSIDE IT.',
    dims: null,
    houseAria: (h) => `Number ${h.door}, gate on ${h.feeder === 'A' ? '4th' : '5th'} Cross`,
  },
}
