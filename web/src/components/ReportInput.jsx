import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from './Icon.jsx'
import { prefersReducedMotion } from '../lib/motion.js'
import { outcomeUnknown, report } from '../lib/api.js'
import { DEFAULT_SEGMENT, SEGMENTS } from '../data/segments.js'
import '../styles/live.css'

const EXAMPLE = 'No water in our tank for three days'
const STEP_MS = 380

/**
 * The intake line. A real input, and a real request: submitting sends the
 * report to the deployed runtime and replays the trace the runtime wrote,
 * one transition at a time.
 *
 * It stops exactly where the real one stops — at a draft waiting for a
 * signature — and the signature is given on the live file, by name. Nothing
 * below the field is scripted. If no model ran the footer says so, and if an
 * agent is still stubbed it says which.
 *
 * The placeholder is a hint, never a report. An empty field sends nothing:
 * words the household did not write must not become a draft addressed to a
 * named officer.
 */
export default function ReportInput() {
  const [value, setValue] = useState('')
  const [segment, setSegment] = useState(DEFAULT_SEGMENT)
  // Unticked on purpose. Hard rule 7: aggregation happens only with the
  // household's say-so, and a pre-ticked box is a say-so nobody gave.
  const [joinCollective, setJoinCollective] = useState(false)
  // idle -> sending -> replay -> done, or sending -> failed
  const [phase, setPhase] = useState('idle')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [shown, setShown] = useState(0)
  const timers = useRef([])

  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  const submit = async (e) => {
    e.preventDefault()
    const text = value.trim()
    if (phase !== 'idle' || !text) return
    setPhase('sending')
    try {
      const r = await report({
        text,
        segment,
        consent: joinCollective ? ['join_collective'] : [],
      })
      const n = r?.trace?.transitions?.length ?? 0
      setResult(r)
      if (prefersReducedMotion() || n === 0) {
        setShown(n)
        setPhase('done')
        return
      }
      setPhase('replay')
      for (let i = 0; i < n; i += 1) {
        timers.current.push(setTimeout(() => setShown(i + 1), STEP_MS * i))
      }
      timers.current.push(setTimeout(() => setPhase('done'), STEP_MS * n))
    } catch (err) {
      setError({ code: err.message, unknown: outcomeUnknown(err) })
      setPhase('failed')
    }
  }

  const reset = () => {
    timers.current.forEach(clearTimeout)
    timers.current = []
    setPhase('idle')
    setResult(null)
    setError(null)
    setShown(0)
  }

  const busy = phase !== 'idle'
  const transitions = result?.trace?.transitions ?? []
  const tokens = result?.usage?.totalTokens ?? 0
  const stubbed = result?.stubbed_agents ?? []
  const opened = Boolean(result?.case_id && result?.case_status)

  return (
    <div className="intake" data-running={busy ? 'yes' : 'no'}>
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
            maxLength={2000}
            placeholder={EXAMPLE}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={busy}
          />
          <button type="submit" className="action intake-submit" disabled={busy || !value.trim()}>
            {phase === 'sending' ? 'Sending' : 'Report it'}
            <Icon name="arrowRight" size={15} />
          </button>
        </div>
        <p className="micro intake-consent">
          <label htmlFor="intake-join">
            <input
              id="intake-join"
              type="checkbox"
              checked={joinCollective}
              onChange={(e) => setJoinCollective(e.target.checked)}
              disabled={busy}
            />{' '}
            Count my household with neighbours reporting the same fault.
            Only the fault and the street are shared, never what is inside the house.
          </label>
        </p>
        <p className="micro intake-foot">
          <label htmlFor="intake-segment">Ward 12 · Bengaluru · street </label>
          <select
            id="intake-segment"
            className="intake-segment"
            value={segment}
            onChange={(e) => setSegment(e.target.value)}
            disabled={busy}
          >
            {SEGMENTS.map((g) => (
              <optgroup key={g.feeder} label={g.label}>
                {g.streets.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </p>
        <p className="micro intake-foot">
          English, ಕನ್ನಡ, हिंदी or தமிழ் — whichever you actually speak
        </p>
      </form>

      {busy && (
        <div className="intake-trace" aria-live="polite">
          {phase === 'sending' && (
            <ol className="intake-steps">
              <li className="intake-step">
                <span className="mono intake-step-k">SIGNAL</span>
                <span className="intake-step-v">
                  Sent to the runtime. A cold start takes a few seconds.
                </span>
              </li>
            </ol>
          )}

          {transitions.length > 0 && (
            <ol className="intake-steps">
              {transitions.slice(0, shown).map((t, i) => (
                <li key={`${i}-${t.status}`} className="intake-step" data-stub={t.stubbed ? 'yes' : 'no'}>
                  <span className="mono intake-step-k">{t.status}</span>
                  <span className="intake-step-v">
                    {t.agent} → {t.detail}
                    {t.citation && <span className="mono intake-cite"> [{t.citation}]</span>}
                  </span>
                </li>
              ))}
            </ol>
          )}

          {phase === 'done' && result && (
            <>
              <p className="micro intake-truth">
                {tokens > 0 ? `${tokens} model tokens spent` : 'No model ran'}
                {stubbed.length > 0 && ` · still stubbed: ${stubbed.join(', ')}`}
                {result.unrouted_reason && ` · not routed: ${result.unrouted_reason}`}
              </p>
              <div className="intake-done">
                {opened ? (
                  <Link to={`/live/${result.case_id}`} className="action action-indigo">
                    Open the live file
                    <Icon name="arrowRight" size={15} />
                  </Link>
                ) : (
                  <Link to="/case" className="action action-indigo">
                    Read how a case runs
                    <Icon name="arrowRight" size={15} />
                  </Link>
                )}
                <button type="button" className="micro intake-reset" onClick={reset}>
                  Clear
                </button>
              </div>
            </>
          )}

          {phase === 'failed' && error && (
            <>
              <p className="intake-step-v intake-failed">
                {error.unknown
                  ? `The runtime did not answer in time (${error.code}). The report may still have been filed, so look before sending it again.`
                  : `Refused before it reached the runtime (${error.code}). Nothing was filed.`}
              </p>
              <div className="intake-done">
                {error.unknown && (
                  <Link to="/live" className="action action-indigo">
                    Your reports
                    <Icon name="arrowRight" size={15} />
                  </Link>
                )}
                <button type="button" className="micro intake-reset" onClick={reset}>
                  {error.unknown ? 'Clear' : 'Try again'}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
