/**
 * Case PNC-2026-0912 — the record as it stands.
 *
 * Shapes follow core/types.py. Households are synthetic and the
 * institutions are calibrated simulators; the statutory windows,
 * the authorities and the citations are real.
 */

export const CASE = {
  id: 'PNC-2026-0912',
  opened: '2026-09-06',
  ward: 12,
  ward_name: 'Doddanekkundi',
  street: '4th Cross, Doddanekkundi',
  subject: 'Supply interruption — no pressure at household tank',
  household: { id: 'HH-12-0012', door: '12/12', name: 'Lakshmi' },
  status: 'DISPUTED',
  tier: 2,
}

export const FILING = {
  ref: 'BWSSB-100001',
  authority: 'BWSSB Sub-Division Office, Mahadevapura',
  channel: 'Grievance portal · Form GR-1',
  filed: '2026-09-10T09:14:00+05:30',
  rule: 'Karnataka Sakala Services Act, 2011 — Sch. II, Item 42',
  window_days: 7,
  due: '2026-09-13',
  signed_by: 'Lakshmi',
  signed_at: '2026-09-10T09:11:00+05:30',
}

/**
 * The statutory record. Terracotta is reserved for the breach and
 * everything downstream of it.
 */
export const TIMELINE = [
  {
    date: '06 SEP',
    time: '05:40',
    tone: 'plain',
    head: 'Reported',
    body: 'Tank empty on the third morning. Reported in Kannada, by voice note, to the street.',
    ref: 'CLM-4471',
  },
  {
    date: '08 SEP',
    time: '11:02',
    tone: 'plain',
    head: 'Jurisdiction resolved',
    body: 'Supply interruption on a BWSSB distribution main. Not BBMP. Not the RWA.',
    ref: 'JUR-BWSSB-02',
  },
  {
    date: '10 SEP',
    time: '09:11',
    tone: 'plain',
    head: 'Signed',
    body: 'Draft read back in Kannada. Approved by name before anything left the household.',
    ref: 'SIG-0912-A',
  },
  {
    date: '10 SEP',
    time: '09:14',
    tone: 'open',
    head: 'Filed',
    body: 'Lodged with BWSSB Mahadevapura. Ticket BWSSB-100001 issued. Statutory window opens.',
    ref: 'BWSSB-100001',
  },
  {
    date: '11 SEP',
    time: '—',
    tone: 'plain',
    head: 'Day 2 of 7',
    body: 'No site visit recorded. Two further households on the same feeder report the same fault.',
    ref: 'CLM-4488 · CLM-4501',
  },
  {
    date: '13 SEP',
    time: '00:00',
    tone: 'plain',
    head: 'Day 7 of 7',
    body: 'Last day of the statutory window. Case still TRACKING.',
    ref: null,
  },
  {
    date: '13 SEP',
    time: '09:15',
    tone: 'closed',
    head: 'Desk marks the ticket resolved',
    body: 'BWSSB-100001 closed. Remark: “Supply restored. No complaint pending.” No work order attached.',
    ref: 'BWSSB-100001',
  },
  {
    date: '13 SEP',
    time: '17:00',
    tone: 'breach',
    head: 'Deadline missed',
    body: 'Window expired with the fault live. The Watchdog wakes on the clock, not on a reply.',
    ref: 'SLA-BREACH',
  },
  {
    date: '13 SEP',
    time: '17:00',
    tone: 'breach',
    head: 'Escalated',
    body: 'Case climbs to tier 2 — Executive Engineer, BWSSB Division East. Tier-1 record carried forward.',
    ref: 'PNC-2026-0912/T2',
  },
  {
    date: '13 SEP',
    time: '17:04',
    tone: 'breach',
    head: 'Closure disputed',
    body: 'Three live claims contradict the closure. The case does not close on the desk’s word.',
    ref: 'DISPUTED',
  },
]

/** Live claims standing against the closure. */
export const CLAIMS = [
  { id: 'CLM-4471', house: 12, at: '06 SEP 05:40', text: 'No water in our tank for three days.' },
  { id: 'CLM-4488', house: 9, at: '11 SEP 07:12', text: 'Motor runs dry. Nothing in the line since Sunday.' },
  { id: 'CLM-4501', house: 17, at: '11 SEP 19:55', text: 'Tanker ordered again. Third one this week.' },
]

/**
 * Correlation as the ambient pass actually computed it. The semantic
 * term did not run — Bedrock's data plane is unavailable on this
 * account — so the score is renormalised over the components that did.
 * Saying so is not a caveat. A cluster that hides which terms ran is
 * claiming agreement it never computed.
 */
export const CORRELATION = {
  tau: 0.72,
  score: 0.94,
  semantic_available: false,
  components: [
    { name: 'topology', weight: 0.4, value: 1.0, ran: true, note: 'same feeder, same segment' },
    { name: 'recency', weight: 0.25, value: 0.86, ran: true, note: 'within 120 h' },
    { name: 'semantic', weight: 0.35, value: null, ran: false, note: 'embedding unavailable' },
  ],
  renormalised_over: ['topology', 'recency'],
  decoy: {
    house: 11,
    score: 0.21,
    note: 'adjacent property, other feeder — topology 0',
  },
}

/** What the ticket said, against what the street said. */
export const CONTRADICTION = {
  desk: {
    ref: 'BWSSB-100001',
    stamped: '13 SEP 2026',
    remark: 'Supply restored. No complaint pending.',
    work_order: null,
  },
  street: {
    live_claims: 3,
    latest: '13 SEP 06:20',
    houses: [9, 12, 17],
  },
  verdict: 'DISPUTED · watchdog → 3 live claim(s) contradict closure',
}

/** The seven stages the case actually moves through. */
export const SPINE = [
  { n: 1, name: 'SIGNAL', gloss: 'A household reports. In its own words, in its own language.', path: 'request' },
  { n: 2, name: 'DELIBERATE', gloss: 'What kind of fault is this, and whose statutory duty is it?', path: 'request' },
  { n: 3, name: 'REPRESENT', gloss: 'The complaint becomes a filing the receiving desk cannot misroute.', path: 'request' },
  { n: 4, name: 'ACT', gloss: 'A named person signs. Only then is anything lodged.', path: 'request' },
  { n: 5, name: 'TRACK', gloss: 'The statutory window is booked as a wake, not watched by a person.', path: 'temporal' },
  { n: 6, name: 'ESCALATE', gloss: 'The window expires. The case climbs, carrying its own record.', path: 'temporal' },
  { n: 7, name: 'CLOSE', gloss: 'Closed when the street agrees it is closed. Not when the desk says so.', path: 'temporal' },
]

/** Four execution paths. Only one of them is request-scoped. */
export const PATHS = [
  { name: 'Request', trigger: 'a household reports', runs: 'AgentCore Runtime · one graph', tone: 'indigo' },
  { name: 'Ambient', trigger: 'a claim row arrives', runs: 'Lambda on DynamoDB Streams', tone: 'marigold' },
  { name: 'Temporal', trigger: 'a deadline passes', runs: 'EventBridge Scheduler → Lambda', tone: 'terracotta' },
  { name: 'Institutions', trigger: 'called over A2A', runs: 'separate processes · their own state', tone: 'sage' },
]

export const DOES = [
  'Tracks the case.',
  'Files with the right authority.',
  'Watches statutory deadlines.',
  'Escalates missed deadlines.',
  'Connects corroborating reports.',
]

export const DOES_NOT = [
  'Fix pipes.',
  'File without your signature.',
  'Expose private household information.',
  'Speak for a household that withdrew.',
  'Promise anonymity.',
]
