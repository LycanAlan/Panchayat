import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from './Icon.jsx'
import { prefersReducedMotion } from '../lib/motion.js'
import { outcomeUnknown, report } from '../lib/api.js'
import { DEFAULT_SEGMENT, ROADS_SEGMENTS, SEGMENTS } from '../data/segments.js'
import { SCENARIOS } from '../data/scenarios.js'
import { useScenario } from '../lib/scenario.jsx'
import '../styles/live.css'

/** A hint for each service, never a report. See the note on the component. */
const EXAMPLE = {
  water: 'No water in our tank for three days',
  roads: 'Deep pothole outside our gate',
}

/**
 * Words that suggest a road problem while Water is picked. Only ever a hint
 * with a button: the household confirms the service. Guessing it silently
 * would be a misroute nobody sees, which is the failure this exists to catch.
 */
const ROAD_WORDS = /\b(pot ?holes?|road|roads|tar\b|footpath|speed ?breaker|ಗುಂಡಿ|ರಸ್ತೆ|सड़क|गड्ढा)/i
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
  const { problem, setProblem } = useScenario()
  const [value, setValue] = useState('')
  const [segment, setSegment] = useState(DEFAULT_SEGMENT)
  // Starts on whichever example the reader is looking at, and then it is
  // the household's own choice.
  const [service, setService] = useState(problem)
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
        service,
        consent: joinCollective ? ['join_collective'] : [],
      })
      const n = r?.trace?.transitions?.length ?? 0
      setResult(r)
      // Every story page now tells the example for what was just reported.
      setProblem(service)
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
      setError({ code: err.message, unknown: outcomeUnknown(err), message: err.data?.message })
      if (err.message === 'not_routable_here') setProblem(service)
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
  const suggestRoads = service === 'water' && ROAD_WORDS.test(value)
  const curatedHere = service !== 'roads' || ROADS_SEGMENTS.includes(segment)

  return (
    <div className="intake" data-running={busy ? 'yes' : 'no'}>
      <form className="intake-form" onSubmit={submit}>
        <label className="label intake-label" htmlFor="intake-field">
          What&rsquo;s broken?
        </label>
        <div className="intake-line">
          <Icon name={service === 'roads' ? 'survey' : 'tap'} size={22} className="intake-icon" />
          <input
            id="intake-field"
            className="intake-field"
            type="text"
            autoComplete="off"
            maxLength={2000}
            placeholder={EXAMPLE[service]}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={busy}
          />
          <button type="submit" className="action intake-submit" disabled={busy || !value.trim()}>
            {phase === 'sending' ? 'Sending' : 'Report it'}
            <Icon name="arrowRight" size={15} />
          </button>
        </div>
        {suggestRoads && !busy && (
          <p className="micro intake-hint">
            Sounds like a road problem?{' '}
            <button type="button" className="intake-hint-switch" onClick={() => setService('roads')}>
              Report it under Roads &amp; potholes
            </button>
          </p>
        )}
        <p className="micro intake-foot intake-service">
          <label htmlFor="intake-service">Problem </label>
          <select
            id="intake-service"
            className="intake-segment"
            value={service}
            onChange={(e) => setService(e.target.value)}
            disabled={busy}
          >
            {Object.values(SCENARIOS).map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </p>
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
            {service === 'roads' ? (
              <>
                <optgroup label="Curated for roads">
                  {SEGMENTS.flatMap((g) => g.streets)
                    .filter((s) => ROADS_SEGMENTS.includes(s.id))
                    .map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                </optgroup>
                <optgroup label="Not curated for roads yet">
                  {SEGMENTS.flatMap((g) => g.streets)
                    .filter((s) => !ROADS_SEGMENTS.includes(s.id))
                    .map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                </optgroup>
              </>
            ) : (
              SEGMENTS.map((g) => (
                <optgroup key={g.feeder} label={g.label}>
                  {g.streets.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </optgroup>
              ))
            )}
          </select>
        </p>
        {!curatedHere && !busy && (
          <p className="micro intake-foot intake-uncurated">
            No curated roads authority on this street yet. Panchayat will say so rather than guess.
          </p>
        )}
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
                {error.code === 'not_routable_here' && error.message
                  ? `${error.message} Nothing was filed.`
                  : error.unknown
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
