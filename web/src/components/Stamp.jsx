import { useId } from 'react'

/**
 * A rubber stamp, in sage ink.
 *
 * Deliberately static. A stamp is an act that already happened — it
 * does not arrive, it is found on the page. Animating this one would
 * make a false closure look like a flourish, and the false closure is
 * the thing the whole case turns on.
 *
 * The imperfection is three layers: a displacement map that roughens
 * every edge, a noise mask that lifts ink off in patches the way a
 * dry pad does, and a blurred underprint that reads as bleed into
 * the paper.
 */
export default function Stamp({
  text = 'RESOLVED',
  sub = 'BWSSB · MAHADEVAPURA',
  date = '13 SEP 2026',
  colour = 'var(--sage)',
  width = 330,
  rotate = -7,
  seed = 7,
}) {
  const uid = useId().replace(/:/g, '')
  const rough = `rough-${uid}`
  const patch = `patch-${uid}`
  const mask = `mask-${uid}`

  const W = 440
  const H = 190

  return (
    <span
      className="stamp"
      style={{ '--stamp-rot': `${rotate}deg`, transform: `rotate(${rotate}deg)`, width }}
      role="img"
      aria-label={`Rubber stamp reading ${text}, ${sub}, ${date}`}
    >
      <svg viewBox={`0 0 ${W} ${H}`} width={width} height={(width * H) / W}>
        <defs>
          {/* edge roughening — what a rubber die does to a straight line */}
          <filter id={rough} x="-12%" y="-24%" width="124%" height="148%">
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.045 0.07"
              numOctaves="4"
              seed={seed}
              result="n"
            />
            <feDisplacementMap
              in="SourceGraphic"
              in2="n"
              scale="3.4"
              xChannelSelector="R"
              yChannelSelector="G"
            />
          </filter>

          {/* dry-pad patchiness — luminance becomes alpha inside the mask */}
          <filter id={patch} x="0" y="0" width="100%" height="100%">
            <feTurbulence type="fractalNoise" baseFrequency="0.42" numOctaves="5" seed={seed + 3} />
            <feColorMatrix type="saturate" values="0" />
            <feComponentTransfer>
              <feFuncA type="discrete" tableValues="0 1 1 1 1" />
            </feComponentTransfer>
          </filter>

          <mask id={mask}>
            <rect width={W} height={H} fill="#fff" />
            <rect width={W} height={H} filter={`url(#${patch})`} opacity="0.34" />
            {/* a worn corner, where the die is lifted first */}
            <ellipse cx={W * 0.88} cy={H * 0.22} rx="72" ry="34" fill="#000" opacity="0.16" />
            <ellipse cx={W * 0.08} cy={H * 0.82} rx="54" ry="26" fill="#000" opacity="0.12" />
          </mask>

          <g id={`art-${uid}`}>
            <rect x="9" y="9" width={W - 18} height={H - 18} fill="none" strokeWidth="6" />
            <rect x="23" y="23" width={W - 46} height={H - 46} fill="none" strokeWidth="2" />
            <text
              x={W / 2}
              y="97"
              textAnchor="middle"
              fontFamily="'IBM Plex Sans', sans-serif"
              fontWeight="600"
              fontSize="58"
              letterSpacing="7"
              stroke="none"
            >
              {text}
            </text>
            <line x1="72" y1="118" x2={W - 72} y2="118" strokeWidth="1.6" />
            <text
              x={W / 2}
              y="141"
              textAnchor="middle"
              fontFamily="'IBM Plex Mono', monospace"
              fontSize="17"
              letterSpacing="3.2"
              stroke="none"
            >
              {sub}
            </text>
            <text
              x={W / 2}
              y="163"
              textAnchor="middle"
              fontFamily="'IBM Plex Mono', monospace"
              fontSize="15"
              letterSpacing="3.2"
              stroke="none"
            >
              {date}
            </text>
          </g>
        </defs>

        {/* bleed: the ink that soaked sideways into the fibre */}
        <g
          fill={colour}
          stroke={colour}
          opacity="0.2"
          style={{ filter: 'blur(2.6px)' }}
          transform="translate(1.4 1.2)"
        >
          <use href={`#art-${uid}`} />
        </g>

        {/* the impression itself */}
        <g fill={colour} stroke={colour} opacity="0.82" mask={`url(#${mask})`} filter={`url(#${rough})`}>
          <use href={`#art-${uid}`} />
        </g>
      </svg>
    </span>
  )
}
