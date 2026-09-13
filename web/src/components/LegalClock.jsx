import { FILING } from '../data/case.js'

/**
 * The statutory window, drawn as a ruled scale rather than a
 * progress bar. Seven days is not progress; it is an obligation
 * with an edge, and the edge is the only part that matters.
 */
export default function LegalClock({ elapsed = 7 }) {
  const days = FILING.window_days
  const marks = Array.from({ length: days + 1 }, (_, i) => i)
  const breached = elapsed >= days

  return (
    <figure className="clock" data-breached={breached ? 'yes' : 'no'}>
      <figcaption className="clock-head">
        <span className="label">Statutory window</span>
        <span className="mono clock-rule">{FILING.rule}</span>
      </figcaption>

      <div className="clock-scale" style={{ '--days': days, '--elapsed': Math.min(elapsed, days) }}>
        <div className="clock-track" />
        <div className="clock-run" />
        <div className="clock-edge" />
        <ol className="clock-marks">
          {marks.map((d) => (
            <li key={d} className="clock-mark" data-major={d === 0 || d === days ? 'yes' : 'no'}>
              <span className="clock-tick" />
              <span className="mono clock-day">{d === 0 ? 'FILED' : `D${d}`}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="clock-feet">
        <span className="mono">
          10 SEP 09:14 · window opens
        </span>
        <span className={`mono ${breached ? 'ink-terracotta' : ''}`}>
          13 SEP 17:00 · {breached ? 'expired, fault live' : 'window closes'}
        </span>
      </div>
    </figure>
  )
}
