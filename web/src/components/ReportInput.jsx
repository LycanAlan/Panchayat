import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from './Icon.jsx'
import { prefersReducedMotion } from '../lib/motion.js'

const STEPS = [
  { at: 0, k: 'SIGNAL', v: 'Report received. Held as a household position.' },
  { at: 700, k: 'DELIBERATE', v: 'Supply interruption, distribution main. Not a quality fault.' },
  { at: 1500, k: 'JURISDICTION', v: 'BWSSB Mahadevapura · Sakala Act 2011, Sch. II Item 42' },
  { at: 2400, k: 'REPRESENT', v: 'Draft filing prepared. Statutory window: 7 working days.' },
  { at: 3200, k: 'HOLD', v: 'Nothing is filed until a named person signs it.' },
]

/**
 * The intake line. A real input, because a fake one on a page about
 * complaints that go nowhere would be its own small joke.
 *
 * Submitting runs the request path locally against the fixture and
 * stops exactly where the real one stops: at a draft, waiting for a
 * signature. It does not file anything.
 */
export default function ReportInput() {
  const [value, setValue] = useState('')
  const [shown, setShown] = useState(0)
  const [started, setStarted] = useState(false)
  const timers = useRef([])

  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  const submit = (e) => {
    e.preventDefault()
    if (started) return
    setStarted(true)
    if (prefersReducedMotion()) {
      setShown(STEPS.length)
      return
    }
    STEPS.forEach((s, i) => {
      timers.current.push(setTimeout(() => setShown(i + 1), s.at))
    })
  }

  const reset = () => {
    timers.current.forEach(clearTimeout)
    timers.current = []
    setStarted(false)
    setShown(0)
  }

  return (
    <div className="intake" data-running={started ? 'yes' : 'no'}>
      <form className="intake-form" onSubmit={submit}>
        <label className="label intake-label" htmlFor="intake-field">
          What&rsquo;s broken?
        </label>
        <div className="intake-line">
          <Icon name="tap" size={22} className="intake-icon" />
          <input
            id="intake-field"
            className="intake-field"
            type="text"
            autoComplete="off"
            placeholder="No water in our tank for three days"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={started}
          />
          <button type="submit" className="action intake-submit" disabled={started}>
            Report it
            <Icon name="arrowRight" size={15} />
          </button>
        </div>
        <p className="micro intake-foot">
          Ward 12 · Bengaluru · English, ಕನ್ನಡ, हिंदी or தமிழ் — whichever you actually speak
        </p>
      </form>

      {started && (
        <div className="intake-trace" aria-live="polite">
          <ol className="intake-steps">
            {STEPS.slice(0, shown).map((s) => (
              <li key={s.k} className="intake-step">
                <span className="mono intake-step-k">{s.k}</span>
                <span className="intake-step-v">{s.v}</span>
              </li>
            ))}
          </ol>
          {shown >= STEPS.length && (
            <div className="intake-done">
              <Link to="/case" className="action action-indigo">
                Read what happened next
                <Icon name="arrowRight" size={15} />
              </Link>
              <button type="button" className="micro intake-reset" onClick={reset}>
                Clear
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
