/**
 * The escalation ladder for a water supply interruption in Ward 12.
 *
 * Jurisdiction is looked up, never generated. A hallucinated authority
 * reproduces the exact failure this exists to catch, so every rung
 * carries the instrument it stands on.
 */

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
    body: 'BWSSB — Assistant Executive Engineer',
    office: 'Sub-Division, Mahadevapura',
    window: '7 working days',
    citation: 'Karnataka Sakala Services Act, 2011 · Sch. II, Item 42',
    state: 'breached',
    note: 'Filed 10 SEP. Window expired 13 SEP with the fault live.',
  },
  {
    tier: 2,
    body: 'BWSSB — Executive Engineer',
    office: 'Division East',
    window: '15 days',
    citation: 'Sakala Act, 2011 · s.5(1) — first appellate authority',
    state: 'current',
    note: 'Case climbed here on the breach, carrying the tier-1 record forward.',
  },
  {
    tier: 3,
    body: 'BWSSB — Chief Engineer (Maintenance)',
    office: 'Cauvery Bhavan, Bengaluru',
    window: '30 days',
    citation: 'Sakala Act, 2011 · s.6(1) — second appellate authority',
    state: 'pending',
    note: null,
  },
  {
    tier: 4,
    body: 'Karnataka State Consumer Disputes Redressal Commission',
    office: 'Bengaluru Urban District Commission',
    window: 'Statutory limitation: 2 years',
    citation: 'Consumer Protection Act, 2019 · s.35 — deficiency in service',
    state: 'pending',
    note: 'A household files here. Panchayat drafts and tracks; it does not appear.',
  },
]

/** Bodies that do not own this fault, and the reason they do not. */
export const NOT_THESE = [
  {
    body: 'BBMP',
    reason: 'Owns roads, drains and solid waste in this ward. Distribution mains are not theirs.',
  },
  {
    body: 'BESCOM',
    reason: 'The pumping station is on their supply. The fault is hydraulic, not electrical.',
  },
  {
    body: 'KSPCB',
    reason: 'Quality and contamination. This is a pressure failure, not a quality failure.',
  },
]

export const JURISDICTION_NOTE =
  'Thirty-one curated entries for this ward. Every routing decision returns a citation ' +
  'or returns nothing. It is better to say “unknown body” than to invent a plausible one.'
