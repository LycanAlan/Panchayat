/**
 * A technical-drawing icon set, drawn for this project.
 *
 * All on a 24-unit grid, all monoline at 1.25, all inheriting
 * currentColor. No icon library: a borrowed set carries someone
 * else's drawing conventions, and the whole page is a drawing.
 */

const PATHS = {
  // a household tap, in elevation
  tap: (
    <>
      <path d="M4 9h7v4a3 3 0 0 0 3 3h1" />
      <path d="M11 9h4a2 2 0 0 1 2 2v1" />
      <path d="M13 5.5h4M15 5.5V9" />
      <path d="M4 7v4" />
      <path d="M15 19.5c0 .8-.6 1.5-1.4 1.5S12 20.3 12 19.5c0-.9 1.4-2.5 1.4-2.5s1.6 1.6 1.6 2.5Z" />
    </>
  ),
  // a tee junction on a main
  junction: (
    <>
      <path d="M2 14h20" />
      <path d="M12 14V5" />
      <path d="M9.5 14v-2.5h5V14" />
      <circle cx="12" cy="5" r="1.6" />
      <path d="M2 17h20" opacity=".4" />
    </>
  ),
  // a gate valve, plan symbol
  valve: (
    <>
      <path d="M2 12h4M18 12h4" />
      <path d="M6 7.5 18 16.5V7.5L6 16.5Z" />
      <path d="M12 12V6M9.5 6h5" />
    </>
  ),
  // a rubber stamp
  stamp: (
    <>
      <path d="M4 20.5h16" />
      <path d="M5.5 17.5h13v2.2h-13z" />
      <path d="M9 17.5v-2.2c0-1.4-1.8-2-1.8-4.6A4.8 4.8 0 0 1 12 5.8a4.8 4.8 0 0 1 4.8 4.9c0 2.6-1.8 3.2-1.8 4.6v2.2" />
    </>
  ),
  // a pen nib
  nib: (
    <>
      <path d="M12 3.5 6.5 14.5 12 20.5l5.5-6Z" />
      <path d="M12 3.5v17" />
      <path d="M6.9 13.6h10.2" />
      <circle cx="12" cy="12.4" r="1.5" />
    </>
  ),
  // a clock whose face is a deadline
  clock: (
    <>
      <circle cx="12" cy="13" r="8" />
      <path d="M12 8v5l3.5 2" />
      <path d="M9 3h6M12 3v2" />
      <path d="M19.5 6.5 21 5" opacity=".45" />
    </>
  ),
  // a filed document with a rule and a signature line
  document: (
    <>
      <path d="M5.5 3.5h9l4.5 4.5v12.5h-13.5Z" />
      <path d="M14.5 3.5V8H19" />
      <path d="M8.5 12h7M8.5 15h7M8.5 18h4" />
    </>
  ),
  // an envelope, sealed
  envelope: (
    <>
      <path d="M3 6h18v12H3Z" />
      <path d="m3 6.8 9 6.2 9-6.2" />
      <path d="m3 17.4 6.4-5M21 17.4l-6.4-5" opacity=".45" />
    </>
  ),
  // a row of houses, in elevation
  houses: (
    <>
      <path d="M2 20h20" />
      <path d="M3.5 20v-6l3-2.4 3 2.4v6" />
      <path d="M10.5 20v-8.5l3.5-2.8 3.5 2.8V20" />
      <path d="M18.5 20v-5l2-1.6 1.5 1.2" />
      <path d="M13.2 20v-3.3h1.6V20" />
    </>
  ),
  // an escalation ladder
  ladder: (
    <>
      <path d="M7.5 21V3M16.5 21V3" />
      <path d="M7.5 17.5h9M7.5 13h9M7.5 8.5h9" />
    </>
  ),
  // an overhead storage tank
  tank: (
    <>
      <path d="M6 8.5h12v9H6Z" />
      <path d="M6 11h12" />
      <path d="M9 21v-3.5M15 21v-3.5" />
      <path d="M12 8.5V5M9.5 5h5" />
    </>
  ),
  // a sightline / survey marker
  survey: (
    <>
      <path d="M12 2v20M2 12h20" opacity=".35" />
      <circle cx="12" cy="12" r="6.5" />
      <circle cx="12" cy="12" r="2" />
    </>
  ),
  arrowRight: (
    <>
      <path d="M3 12h17" />
      <path d="m14.5 6.5 6 5.5-6 5.5" />
    </>
  ),
  arrowDown: (
    <>
      <path d="M12 3v17" />
      <path d="m6.5 14.5 5.5 6 5.5-6" />
    </>
  ),
}

export default function Icon({ name, size = 22, stroke = 1.25, className = '', ...rest }) {
  const d = PATHS[name]
  if (!d) return null
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
      {...rest}
    >
      {d}
    </svg>
  )
}

export const ICON_NAMES = Object.keys(PATHS)
