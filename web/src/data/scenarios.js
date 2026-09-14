/**
 * The two worked examples the story pages can tell, keyed by the service a
 * household picks on the home page: `water` (Lakshmi's tank) and `roads` (the
 * pothole outside 12/14).
 *
 * The template does not change between them — same sections, same drawings,
 * same seven stages. What changes is everything that is actually about the
 * case: the household, the authority, the ladder, the record and the words.
 * The water copy is the site's existing text, moved here verbatim.
 *
 * These are the only two because they are the only two services Ward 12's
 * jurisdiction table routes today. The spine handles any service; a third
 * example is curated data and copy, not a new page.
 */

import * as water from './case.js'
import * as waterAuthorities from './authorities.js'
import * as waterIndic from './indic.js'
import * as street from './street.js'
import * as roads from './roads.js'

export const DEFAULT_PROBLEM = 'water'

const WATER_DRAWING = {
  PLAN: street.PLAN,
  HOUSES: street.HOUSES,
  byNumber: street.byNumber,
  SUBJECT: street.SUBJECT,
  CORROBORATING: street.CORROBORATING,
  DECOY: street.DECOY,
  VALVES: street.VALVES,
  FAULT: street.FAULT,
  INLET: street.INLET,
  text: {
    aria:
      'Engineering layout of 4th Cross, Ward 12: twenty-four properties above grade, each tagged A or B for the water main it is connected to, and two distribution mains below grade. Numbers 9, 12 and 17 are on Main A. Number 11, next door to 12, is on Main B.',
    t1: 'WARD 12 · 4TH CROSS, DODDANEKKUNDI',
    t2: 'WATER SUPPLY LAYOUT · ELEVATION + BURIED SERVICES',
    t3: 'DRG. PNC-W12-01 · SHEET 1 OF 1 · N.T.S.',
    keyA: `MAIN A · ${street.PLAN.mainA.spec} · INVERT ${street.PLAN.mainA.depth}`,
    keyB: `MAIN B · ${street.PLAN.mainB.spec} · INVERT ${street.PLAN.mainB.depth}`,
    chip: 'FEEDER TAG',
    valve: 'VALVE',
    tee: 'SERVICE TEE',
    subject: '12/12 — THIS CASE',
    mainA: `MAIN A · 300 mm AC · INVERT ${street.PLAN.mainA.depth}`,
    mainB: `MAIN B · 250 mm DI · INVERT ${street.PLAN.mainB.depth}`,
    cluster: '09 · 12 · 17 — ONE FEEDER, ONE FAULT',
    decoy: '11 — NEXT DOOR TO 12. CROSSES MAIN A. TEED INTO MAIN B. HAS WATER.',
    dims: ['1.54', '2.70'],
    houseAria: (h) => `Number ${h.door}, connected to Main ${h.feeder}`,
  },
}

export const SCENARIOS = {
  water: {
    key: 'water',
    label: 'Water supply',
    switchLabel: 'Water · Lakshmi',
    ...water,
    LADDER: waterAuthorities.LADDER,
    NOT_THESE: waterAuthorities.NOT_THESE,
    JURISDICTION_NOTE: waterAuthorities.JURISDICTION_NOTE,
    REPORT: waterIndic.REPORT,
    VOICES: waterIndic.VOICES.map((v) => ({ ...v, decoy: v.house === '12/11' })),
    DRAWING: WATER_DRAWING,
    hero: 'water',
    copy: {
      opened: '06 SEP 2026',
      figures: [
        {
          n: '15',
          unit: 'times',
          t: 'One pothole complaint in this city was opened and closed again, on the same stretch of road, with the road unchanged.',
        },
        {
          n: '7',
          unit: 'days',
          t: 'The statutory window a household is expected to count, unaided, while doing everything else a week contains.',
        },
        {
          n: '0',
          unit: 'work orders',
          t: 'Attached to the closure on this case. The ticket says the supply was restored. Nothing says anyone went.',
        },
      ],
      registerCase:
        'Lakshmi reports on the third morning. Eleven entries later, the desk stamps it closed and three houses are still dry.',
      registerStreet:
        'Twenty-four properties, two mains. Read the drawing and the cluster stops being a coincidence.',
      recordOpener:
        'When the water fails, the building group knows inside fifteen minutes. Nobody needs to be told. What nobody has is the stamina to file against the right body, hold a statutory clock for eleven weeks, notice the day it breaches, and climb to the next authority with the record intact.',
      preview: {
        kicker: 'Drawing PNC-W12-01',
        title: 'Next door is not the same as downstream.',
        note: '4th Cross · 24 properties · 2 mains',
        claim:
          'Three households on this street share a fault. They are not neighbours. The house between two of them has water, because it is on the other main.',
        caption:
          'Fig. 1 — Water supply layout, 4th Cross. Properties 9, 12 and 17 are served by Main A. Property 11, which shares a wall with 12, is served by Main B and is unaffected.',
      },
      caseFile: {
        meta: 'In the matter of a supply interruption',
        title: ['Lakshmi’s tap,', 'and the eleven weeks', 'nobody was counting.'],
        chapter: { day: '06', month: 'SEP', time: '05:40' },
        chapterHead: 'The tank is empty.',
        chapterLead:
          'Third morning. The motor runs and pulls nothing. She checks the sump, the valve, the neighbour’s line. Then she says it out loud, in the language she says everything else in.',
        chapterNote:
          'This is a household position. It stays inside the household — her name, her door number, what else is going on in that house. Only a claim crosses out of it, and only once she has agreed to send one.',
        jurKicker: '08 SEP · 11:02',
        correctBody: 'BWSSB — Sub-Division Office, Mahadevapura',
        windowLine: `Window: ${water.FILING.window_days} working days from receipt`,
        filingKicker: '10 SEP · 09:11',
        filingTitle: 'Her words become a filing.',
        filingNote: 'Form GR-1',
        filingFields: [
          { k: 'Nature of grievance', v: 'Complete loss of supply at premises — distribution main' },
          { k: 'Duration', v: 'Continuous since 04 SEP 2026 (06 days at filing)' },
          { k: 'Instrument', v: water.FILING.rule },
          { k: 'Relief sought', v: 'Site inspection, trace of feeder, restoration of supply' },
        ],
        filingBody:
          'The premises has had no supply for six days. Neighbouring properties on the same distribution main report the same failure. A trace of the feeder upstream of the isolation valve is requested.',
        signMeta: '10 SEP · 09:11',
        signHead: ['Nothing is filed', 'until she signs it.'],
        signLead:
          'The draft is read back to her in Kannada, in full, including the sentence that names her street. She can change it, hold it, or drop it. The liability for a filing against a public body lands on the household, so the household decides.',
        signRef: 'SIG-0912-A',
        signName: 'ಲಕ್ಷ್ಮಿ',
        signAt: '10 SEP 2026 · 09:11 IST',
        signScope: 'Supply fault only. No income, health or arrears data.',
        clockKicker: '10–13 SEP',
        clockTitle: 'The statutory clock.',
        clockNote: '7 working days',
        readoutExpired: 'window expired · fault live',
        readoutOpen: 'window open · no site visit recorded',
        breach: { day: '13', month: 'SEP', time: '17:00' },
        breachHead: ['Day 7 of 7.', 'Nobody came.'],
        breachLead:
          'The window expires with the fault live. This is the moment the clock earns its keep: no reply arrived, so nothing prompted anyone. The wake fires anyway, reads the case, finds it still tracking, and marks the breach on the record.',
        breachLine: 'SLA-BREACH · 13 SEP 2026 17:00 IST · tier 1 · BWSSB-100001',
        climbKicker: '13 SEP · 17:00',
        closureKicker: '13 SEP · 09:15',
        closureNote: 'Eight hours before the deadline',
        closureAuthority: 'BWSSB Sub-Division Office, Mahadevapura',
        closureStampSub: 'BWSSB · MAHADEVAPURA',
        closureSay: [
          'In the grievance portal this case is finished. It leaves the pending queue, it stops counting against anyone’s numbers, and it will appear in a quarterly figure as a complaint attended within the statutory window.',
          'A household reading that page has no way to argue with it. It knows its own tap is dry, and one dry tap against an official closure is a story about a faulty motor.',
        ],
        contraKicker: '13 SEP · 17:04',
        climax: ['You know your own tap.', 'You do not know your neighbours’.'],
        standsOpener:
          'The closure is recorded, and so is the contradiction. Both sit in the file, and the file went up a tier rather than out of the system. The next window is fifteen days, and it is already being counted.',
        standsNext: 'What changed is not that a pipe was mended. It is that a stamp is no longer the last word on it.',
        standsStampDate: '13 SEP 2026',
      },
      clock: {
        label: 'Statutory window',
        opens: '10 SEP 09:14 · window opens',
        closes: '13 SEP 17:00',
        expired: 'expired, fault live',
      },
      street: {
        meta: 'Drawing PNC-W12-01 · sheet 1 of 1',
        title: ['Geographic proximity', 'is not ', 'infrastructure proximity.'],
        lead:
          'Two households can share a wall and not share a pipe. Two households four doors apart can share the same failure. Every clustering decision this system makes rests on the second ordering, and the second ordering is invisible from the street.',
        beats: [
          {
            head: 'Twenty-four houses, in the order the numbers run.',
            body: 'This is the street as everyone holds it in their head: a row of doors, 12/01 at one end and 12/24 at the other. Nothing in this picture can tell you which two households share a fault.',
          },
          {
            head: 'Two mains, at two depths, laid seventeen years apart.',
            body: 'Main A went in with the 1994 extension — 300 mm asbestos cement, 1.54 m down. Main B is 2011, ductile iron, deeper. Each property was teed into whichever was live the year it connected. Read the tag under each door number: that letter is the only thing that decides who shares a failure.',
          },
          {
            head: 'Follow the feeder, not the footpath.',
            body: 'Trace Main A and the households on it surface: 09, 12 and 17. They are not adjacent. Nobody living in them would describe the other two as neighbours. Hydraulically they are one household with three taps.',
          },
          {
            head: 'Eleven has water. Eleven shares a wall with twelve.',
            body: 'Number 11 is tagged B. Its service crosses over Main A without touching it and carries on down to its own feeder, and its supply never faltered. Any reading of this street that starts with proximity puts 11 in the cluster and leaves 17 out — and both of those are wrong.',
          },
        ],
        probeTitle: 'Pick a house. See where its water comes from.',
        probe: {
          line: 'Feeder',
          lineValue: (h, plan) => `Main ${h.feeder} · ${h.feeder === 'A' ? plan.mainA.spec : plan.mainB.spec}`,
          depth: 'Invert',
          either: (letter) => `Main ${letter}`,
          shares: 'Shares this main with',
          claim: 'live claim · supply failed',
          decoy: 'supply normal · other main',
          plain: 'supply normal',
          empty:
            'Move across the elevation. Each property lights its own service line down to whichever main it is teed into.',
          count: (n, total) => `${n} of ${total} are on Main A. No two of them are next door to each other.`,
        },
        why: [
          'Corroboration is the difference between one household with a story and a street with a fault. A single dry tap is answerable — bad motor, empty sump, unpaid bill. Three taps on one feeder is a hydraulic statement, and it is much harder for a closure to sit on top of.',
          'So the weight this system puts on topology is not decoration. Scoring on words alone would have found 11 and 12 — same street, same phrasing, same hour — and missed 17 entirely. The drawing is what stops that.',
          'It also stops the opposite error. The house on the other main scores zero on topology, so however similar its wording, it never joins the cluster. A pressure complaint in a building that simply forgot to pay does not get to stand behind somebody else’s breach.',
        ],
      },
      process: { routingNote: '31 curated entries' },
      doesNotFirst: 'Fix pipes.',
      footerClose: 'We do not fix pipes.',
    },
  },

  roads: {
    key: 'roads',
    label: 'Roads & potholes',
    switchLabel: 'Roads · Ramesh',
    CASE: roads.CASE,
    FILING: roads.FILING,
    TIMELINE: roads.TIMELINE,
    CLAIMS: roads.CLAIMS,
    CORRELATION: roads.CORRELATION,
    CONTRADICTION: roads.CONTRADICTION,
    SPINE: water.SPINE,
    PATHS: water.PATHS,
    DOES: water.DOES,
    DOES_NOT: water.DOES_NOT,
    LADDER: roads.LADDER,
    NOT_THESE: roads.NOT_THESE,
    JURISDICTION_NOTE: roads.JURISDICTION_NOTE,
    REPORT: roads.REPORT,
    VOICES: roads.VOICES,
    DRAWING: roads.DRAWING,
    hero: 'roads',
    copy: {
      opened: '05 SEP 2026',
      figures: [
        {
          n: '15',
          unit: 'times',
          t: 'One pothole complaint in this city was opened and closed again, on the same stretch of road, with the road unchanged.',
        },
        {
          n: '7',
          unit: 'days',
          t: 'The turnaround BBMP gives itself for a pothole. Not a statute — so nobody but the household is counting it.',
        },
        {
          n: '0',
          unit: 'work orders',
          t: 'Attached to the closure on this case. The ticket says the pothole was filled. Nothing says the base was ever repaired.',
        },
      ],
      registerCase:
        'Ramesh reports the morning the patch lifts again. Six days later the desk stamps it filled, and that night it rains.',
      registerStreet:
        'Twenty-four properties, two streets behind one row. Read the drawing and the cluster stops being a coincidence.',
      recordOpener:
        'When a road fails, the whole street has driven through it by evening. Nobody needs to be told. What nobody has is the stamina to file against the right body, hold a clock for eleven weeks, notice the day it breaches, and climb to the next authority with the record intact.',
      preview: {
        kicker: 'Drawing PNC-W12-R1',
        title: 'Next door is not the same road.',
        note: '4th Cross · 24 properties · 2 streets',
        claim:
          'Three households on this street report one hole. They are not neighbours. The house between two of them has no complaint, because its gate opens onto the other street.',
        caption:
          'Fig. 1 — Road access layout, 4th Cross. Properties 8, 14 and 20 open onto 4th Cross. Property 13, which shares a wall with 14, opens onto 5th Cross and is unaffected.',
      },
      caseFile: {
        meta: 'In the matter of a road defect',
        title: ['Ramesh’s gate,', 'and a hole closed', 'with the road unchanged.'],
        chapter: { day: '05', month: 'SEP', time: '07:50' },
        chapterHead: 'The hole is back.',
        chapterLead:
          'Two days of rain. The patch from June has lifted and the hole outside the gate is full of water, so nobody can see how deep it is. In the morning he says it out loud, in the language he says everything else in.',
        chapterNote:
          'This is a household position. It stays inside the household — his name, his door number, what else is going on in that house. Only a claim crosses out of it, and only once he has agreed to send one.',
        jurKicker: '05 SEP · 08:02',
        correctBody: 'BBMP — Assistant Engineer, Ward 12 office',
        windowLine: 'Window: 7 days · BBMP’s own stated turnaround, not a statutory count',
        filingKicker: '05 SEP · 09:31',
        filingTitle: 'His words become a filing.',
        filingNote: 'Ward grievance counter',
        filingFields: [
          { k: 'Nature of grievance', v: 'Pothole in the carriageway, about 450 × 300 mm and 90 mm deep, outside 12/14' },
          { k: 'Duration', v: 'Open again since 04 SEP 2026, after three fills since June' },
          { k: 'Instrument', v: roads.FILING.rule },
          { k: 'Relief sought', v: 'Cut, clean and relay the failed patch to the base course — not another surface fill' },
        ],
        filingBody:
          'The fill outside 12/14 has failed for the third time. Households along the same stretch of 4th Cross report the same hole. A repair down to the base course, not another cold-mix fill, is requested.',
        signMeta: '05 SEP · 09:31',
        signHead: ['Nothing is filed', 'until he signs it.'],
        signLead:
          'The draft is read back to him in Kannada, in full, including the sentence that names his gate. He can change it, hold it, or drop it. The liability for a filing against a public body lands on the household, so the household decides.',
        signRef: 'SIG-0914-A',
        signName: 'ರಮೇಶ್',
        signAt: '05 SEP 2026 · 09:31 IST',
        signScope: 'Road defect only. No income, health or arrears data.',
        clockKicker: '05–12 SEP',
        clockTitle: 'The chase clock.',
        clockNote: '7 days · not statutory',
        readoutExpired: 'window expired · hole open',
        readoutOpen: 'window open · no site visit recorded',
        breach: { day: '12', month: 'SEP', time: '09:40' },
        breachHead: ['Day 7 of 7.', 'The hole is still there.'],
        breachLead:
          'The window expires with the hole open. The desk had already closed the ticket, so nothing prompted anyone. The wake fires anyway, reads the case, finds three live claims against the closure, and marks the breach on the record.',
        breachLine: 'SLA-BREACH · 12 SEP 2026 09:40 IST · tier 1 · WARD-100001',
        climbKicker: '12 SEP · 09:40',
        closureKicker: '11 SEP · 16:40',
        closureNote: 'The day before the deadline',
        closureAuthority: 'BBMP Ward 12 office, Doddanekkundi',
        closureStampSub: 'BBMP · WARD 12',
        closureSay: [
          'In the grievance portal this case is finished. It leaves the pending queue, it stops counting against anyone’s numbers, and it will appear in a monthly figure as a pothole attended within the week.',
          'A household reading that page has no way to argue with it. It knows the hole at its own gate is back, and one complaint against an official closure is a story about a bad week of rain.',
        ],
        contraKicker: '12 SEP · 09:44',
        climax: ['You know the hole at your gate.', 'You do not know who else fell in.'],
        standsOpener:
          'The closure is recorded, and so is the contradiction. Both sit in the file, and the file went up a tier rather than out of the system. The next window is seven days at the zone, and it is already being counted.',
        standsNext:
          'What changed is not that a road was relaid. It is that a stamp is no longer the last word on it.',
        standsStampDate: '12 SEP 2026',
      },
      clock: {
        label: 'Chase window · BBMP’s own turnaround, not a statute',
        opens: '05 SEP 09:40 · window opens',
        closes: '12 SEP 09:40',
        expired: 'expired, hole open',
      },
      street: {
        meta: 'Drawing PNC-W12-R1 · sheet 1 of 1',
        title: ['A shared wall', 'is not ', 'a shared road.'],
        lead:
          'Two households can share a wall and not share a road. Two households six doors apart can drive over the same hole every day. Every clustering decision this system makes rests on the second ordering, and the second ordering is invisible from the pavement.',
        beats: [
          {
            head: 'Twenty-four houses, in the order the numbers run.',
            body: 'This is the street as everyone holds it in their head: a row of doors, 12/01 at one end and 12/24 at the other. Nothing in this picture can tell you which households drive over the same hole.',
          },
          {
            head: 'Two streets, one row of plots.',
            body: 'The row sits back to back between 4th Cross and 5th Cross. Each plot has one gate, and it opens onto one of them. Read the tag under each door number: A is 4th Cross, B is 5th Cross. That letter is the only thing that decides which road a household uses every day.',
          },
          {
            head: 'Follow the road, not the wall.',
            body: 'Trace Road A and the households reporting on it surface: 08, 14 and 20. They are not adjacent. Nobody living in them would describe the other two as neighbours. On 4th Cross they are three households with one hole.',
          },
          {
            head: 'Thirteen shares a wall with fourteen. Its road is fine.',
            body: 'Number 13 is tagged B. Its gate opens onto 5th Cross, and the carriageway outside it has no hole. Any reading of this street that starts with proximity puts 13 in the cluster and leaves 20 out — and both of those are wrong.',
          },
        ],
        probeTitle: 'Pick a house. See which road its gate opens onto.',
        probe: {
          line: 'Access',
          lineValue: (h, plan) => `Road ${h.feeder} · ${h.feeder === 'A' ? plan.mainA.spec : plan.mainB.spec}`,
          depth: 'Carriageway width',
          either: (letter) => `Road ${letter}`,
          shares: 'Shares this road with',
          claim: 'live claim · hole open',
          decoy: 'road fine · other street',
          plain: 'no complaint',
          empty:
            'Move across the elevation. Each property lights its access line down to whichever street its gate opens onto.',
          count: (n, total) => `${n} of ${total} open onto 4th Cross. No two of them are next door to each other.`,
        },
        why: [
          'Corroboration is the difference between one household with a story and a street with a fault. A single complaint about a hole is answerable — one night, one scooter, one careless rider. Three households on one road reporting one hole is a statement about the road, and it is much harder for a closure to sit on top of.',
          'So the weight this system puts on topology is not decoration. For roads the topology is the street itself. Scoring on words alone would have found 13 and 14 — same wall, same rain, same hour — and missed 20 entirely. The drawing is what stops that.',
          'It also stops the opposite error. A hole on 5th Cross scores 0.15 on topology against this one, so however similar its wording, it never joins the cluster. A complaint about somebody else’s road does not get to stand behind this street’s breach.',
        ],
      },
      process: { routingNote: '4 road segments · 31 water entries' },
      doesNotFirst: 'Fill potholes.',
      footerClose: 'We do not fill potholes.',
    },
  },
}

export const PROBLEMS = Object.values(SCENARIOS).map((s) => ({ key: s.key, label: s.label, switchLabel: s.switchLabel }))
