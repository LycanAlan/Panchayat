/**
 * The streets a report can come from, exactly as data/jurisdiction/ward12.yaml
 * names them. The runtime refuses a report without one — `unrouted_reason:
 * no_segment` — because jurisdiction is looked up by segment, never guessed.
 *
 * Grouped by feeder, because the feeder decides who owes the duty: two
 * streets side by side can hang off different mains.
 */
export const SEGMENTS = [
  {
    feeder: 'bwssb-tm-14',
    label: 'BWSSB trunk main 14',
    streets: [
      { id: 'ward12-4thcross', name: '4th Cross' },
      { id: 'ward12-5thcross', name: '5th Cross' },
      { id: 'ward12-3rdcross', name: '3rd Cross' },
      { id: 'ward12-templestreet', name: 'Temple Street' },
      { id: 'ward12-mainroad', name: 'Main Road' },
    ],
  },
  {
    feeder: 'bwssb-tm-15',
    label: 'BWSSB trunk main 15',
    streets: [
      { id: 'ward12-6thmain', name: '6th Main' },
      { id: 'ward12-7thmain', name: '7th Main' },
      { id: 'ward12-8thmain', name: '8th Main' },
      { id: 'ward12-parkextension', name: 'Park Extension' },
      { id: 'ward12-lakeviewroad', name: 'Lake View Road' },
    ],
  },
  {
    feeder: 'bwssb-tm-16',
    label: 'BWSSB trunk main 16',
    streets: [
      { id: 'ward12-1ststage', name: '1st Stage' },
      { id: 'ward12-2ndstage', name: '2nd Stage' },
      { id: 'ward12-3rdstage', name: '3rd Stage' },
      { id: 'ward12-schoolstreet', name: 'School Street' },
      { id: 'ward12-hospitalroad', name: 'Hospital Road' },
    ],
  },
  {
    feeder: 'bwssb-tm-22',
    label: 'BWSSB trunk main 22',
    streets: [
      { id: 'ward12-stationroad', name: 'Station Road' },
      { id: 'ward12-marketroad', name: 'Market Road' },
      { id: 'ward12-busstandroad', name: 'Bus Stand Road' },
      { id: 'ward12-postofficelane', name: 'Post Office Lane' },
      { id: 'ward12-9thmain', name: '9th Main' },
      { id: 'ward12-libraryroad', name: 'Library Road' },
    ],
  },
  {
    feeder: 'bwssb-tm-23',
    label: 'BWSSB trunk main 23',
    streets: [
      { id: 'ward12-millroad', name: 'Mill Road' },
      { id: 'ward12-factorylane', name: 'Factory Lane' },
      { id: 'ward12-depotroad', name: 'Depot Road' },
      { id: 'ward12-warehousestreet', name: 'Warehouse Street' },
    ],
  },
  {
    feeder: 'bbmp-bore-07',
    label: 'BBMP borewell 07',
    streets: [
      { id: 'ward12-oldvillage', name: 'Old Village' },
      { id: 'ward12-keremohalla', name: 'Kere Mohalla' },
      { id: 'ward12-gunduthopelane', name: 'Gundu Thope Lane' },
    ],
  },
  {
    feeder: 'layout-internal',
    label: 'Private layouts, internal network',
    streets: [
      { id: 'ward12-greenmeadows', name: 'Green Meadows' },
      { id: 'ward12-sunriseenclave', name: 'Sunrise Enclave' },
      { id: 'ward12-brookefieldextn', name: 'Brookefield Extension' },
    ],
  },
]

export const DEFAULT_SEGMENT = 'ward12-4thcross'

/**
 * The streets with a curated roads entry in data/jurisdiction/ward12.yaml.
 * Every other street can still be picked for a pothole: the door answers that
 * Ward 12 has no curated roads authority there, rather than the page hiding
 * the street or the runtime inventing an office.
 */
export const ROADS_SEGMENTS = ['ward12-4thcross', 'ward12-1ststage', 'ward12-2ndstage', 'ward12-8thmain']

const NAMES = Object.fromEntries(SEGMENTS.flatMap((g) => g.streets.map((s) => [s.id, s.name])))

export function segmentName(id) {
  return NAMES[id] ?? id ?? '—'
}
