import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Document from '../components/Document.jsx'
import Icon from '../components/Icon.jsx'
import { SectionHead } from '../components/Bits.jsx'
import { approve, getCase, identity, listCases } from '../lib/api.js'
import { segmentName } from '../data/segments.js'
import { SCENARIOS } from '../data/scenarios.js'
import { useScenario } from '../lib/scenario.jsx'
import '../styles/live.css'

/**
 * The live file. Every other route renders a fixture shaped after
 * core/types.py; this one reads the deployed runtime.
 *
 *   /live            the open cases this browser's household is on
 *   /live/:caseId    one case, its filings, and anything waiting to be signed
 *
 * It says so on the page. A reader arriving from the story at /case must be
 * able to tell a record the system wrote from one we drew.
 */

/** A draft on a case in one of these states must not be offered for signing. */
const LAPSED = new Set(['dormant', 'withdrawn', 'resolved'])

/**
 * The Watchdog files a signed draft about 100 s after the signature (a cold
 * start plus a model call), so the page keeps reading while one is on its way.
 * Past the cap a desk is probably down, and "Read it again" is the honest control.
 */
const WATCH_MS = 180_000
const POLL_MS = 5_000

/** Tier 4 is an RTI. agents/watchdog.py drafts it and never files it, so no ticket is coming. */
const RTI_TIER = 4

function onItsWay(f) {
  return Boolean(f.signed_by) && !f.external_ref && f.tier < RTI_TIER
}

/** The Watchdog tried, the desk did not take it, and a retry is booked with the clock held. */
function notTaken(c) {
  return c.status === 'escalating' && c.sla_paused
}

/**
 * The desk's refusals, oldest first. agents/watchdog.py appends one line per
 * refusal to the filing's `response`, in the desk text protocol: the outcome
 * word first, then ": reason". The reason is the only part a household can
 * act on, so it is the part shown.
 */
function refusals(f) {
  return (f.response ?? '')
    .split('\n')
    .filter((line) => line.startsWith('REJECTED'))
    .map((line) => line.slice(line.indexOf(':') + 1).trim() || 'no reason given')
}

/** Mirrors agents/watchdog.py::REJECTIONS_BEFORE_HUMAN: one resend, then a person. */
const REFUSALS_BEFORE_HUMAN = 2

function ticket(f, c, watching) {
  if (f.external_ref) return { v: f.external_ref }
  const refused = refusals(f)
  if (onItsWay(f) && refused.length >= REFUSALS_BEFORE_HUMAN) {
    return { v: `— refused ${refused.length}× · ${refused.at(-1)} · needs a person to resubmit —`, tone: 'terracotta' }
  }
  if (onItsWay(f) && refused.length > 0) {
    return { v: `— refused · ${refused.at(-1)} · resending once tomorrow —`, tone: 'terracotta' }
  }
  if (onItsWay(f) && notTaken(c)) return { v: '— desk did not take it · retry booked —', tone: 'terracotta' }
  if (onItsWay(f) && watching) return { v: 'filing now…' }
  return { v: '— none issued —' }
}

const IST = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata',
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

function when(iso) {
  if (!iso) return '—'
  // The runtime writes naive UTC (core/clock.py). Say so to the parser, and
  // trim microseconds, which not every browser's Date will read.
  const trimmed = iso.replace(/(\.\d{3})\d+/, '$1')
  const d = new Date(/(Z|[+-]\d\d:\d\d)$/.test(trimmed) ? trimmed : `${trimmed}Z`)
  return Number.isNaN(d.getTime()) ? iso : `${IST.format(d)} IST`
}

const HINTS = {
  no_such_case: 'No case with that id on this runtime. Case ids come from a report made on this site.',
  runtime_unavailable:
    'The runtime did not answer in time. A cold start can take a few seconds. If you were signing, read the file again first: the signature may have landed.',
  runtime_not_configured: 'The web Lambda has no runtime to call. That is a deploy problem, not yours.',
  not_yours_to_sign: 'Only the household chosen to carry this filing can sign it, and that is not this browser.',
  case_lapsed: 'This case has lapsed, so its draft can no longer be signed.',
  nothing_to_sign: 'That draft is no longer waiting for a signature. Read the file again.',
}

function Failure({ code }) {
  return (
    <div className="live-failure">
      <p className="mono ink-terracotta">{code}</p>
      <p className="sans dim">{HINTS[code] ?? 'The request did not complete.'}</p>
    </div>
  )
}

function Fact({ k, v, status }) {
  return (
    <div>
      <dt className="micro">{k}</dt>
      <dd className="mono" data-status={status}>{v}</dd>
    </div>
  )
}

export default function Live() {
  const { caseId } = useParams()

  return (
    <div className="live">
      <section className="band band-tight live-cover">
        <div className="page">
          <p className="meta">Live record · read from the deployed runtime</p>
          <p className="sans dim live-honest">
            Not a fixture. Everything below came back from AgentCore when this page last read it.
            The household is this browser, and the institutions are calibrated simulators,
            so nothing here reaches a real authority.
          </p>
          {caseId ? <CaseFile key={caseId} caseId={caseId} /> : <MyCases />}
        </div>
      </section>
    </div>
  )
}

function MyCases() {
  const [cases, setCases] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let current = true
    listCases()
      .then((d) => current && setCases(d.cases))
      .catch((err) => current && setError(err.message))
    return () => {
      current = false
    }
  }, [])

  return (
    <>
      <h1 className="display live-title">Your reports.</h1>
      {error && <Failure code={error} />}
      {!error && !cases && <p className="micro">Reading the file…</p>}
      {cases && cases.length === 0 && (
        <p className="lead">
          Nothing open for this household yet.{' '}
          <Link to="/" className="action action-indigo">
            Report something
            <Icon name="arrowRight" size={15} />
          </Link>
        </p>
      )}
      {cases && cases.length > 0 && (
        <ol className="live-list">
          {cases.map((c) => (
            <li key={c.case_id}>
              <Link to={`/live/${c.case_id}`} className="live-row">
                <span className="mono">{c.case_id}</span>
                <span className="mono" data-status={c.status}>{c.status}</span>
                <span className="sans">{c.authority ?? 'not routed'} · {segmentName(c.segment)}</span>
                {c.awaiting_signature > 0 ? (
                  <span className="micro live-badge">awaiting signature</span>
                ) : (
                  <span />
                )}
              </Link>
            </li>
          ))}
        </ol>
      )}
      <p className="micro live-note">
        Open cases only. A case that lapsed or resolved does not list here yet.
      </p>
    </>
  )
}

function CaseFile({ caseId }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [signing, setSigning] = useState(null)
  // Bumped by each signature so the watch restarts; expiredWatch records which one ran out.
  const [watch, setWatch] = useState(0)
  const [expiredWatch, setExpiredWatch] = useState(-1)
  const latest = useRef(0)

  // Only the newest request may write, so a slow poll cannot put older state
  // back over the reload a signature triggered. A quiet poll that fails keeps
  // what is on screen and tries again; it does not raise a banner.
  const load = useCallback(
    async ({ quiet = false } = {}) => {
      const mine = ++latest.current
      try {
        const next = await getCase(caseId)
        if (mine !== latest.current) return
        setData(next)
        if (!quiet) setError(null)
      } catch (err) {
        if (mine === latest.current && !quiet) setError(err.message)
      }
    },
    [caseId],
  )

  useEffect(() => {
    load()
  }, [load])

  // A live roads case links to "How a case runs"; the story it opens should
  // be the pothole one, not Lakshmi's tank.
  const { setProblem } = useScenario()
  const service = data?.case?.service
  useEffect(() => {
    if (service && SCENARIOS[service]) setProblem(service)
  }, [service, setProblem])

  const watching = Boolean(
    data &&
      expiredWatch !== watch &&
      !LAPSED.has(data.case.status) &&
      !notTaken(data.case) &&
      data.filings.some(onItsWay),
  )

  // Above the early return, or React throws on the first render with data.
  // A setTimeout chain rather than setInterval, so a slow cold start never
  // stacks requests: each is a Lambda call against an account capped at 10
  // concurrent executions, shared with the Watchdog filing this very ticket.
  // Skipped while the tab is hidden for the same reason, and hidden time does
  // not count toward the cap: someone who signs, switches tabs and comes back
  // must still see the ticket land.
  useEffect(() => {
    if (!watching) return undefined
    let reads = 0
    let timer
    let stopped = false
    const tick = async () => {
      if (document.visibilityState === 'visible') {
        if (reads * POLL_MS >= WATCH_MS) {
          setExpiredWatch(watch)
          return
        }
        reads += 1
        await load({ quiet: true })
      }
      if (!stopped) timer = setTimeout(tick, POLL_MS)
    }
    timer = setTimeout(tick, POLL_MS)
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [watching, watch, load])

  const sign = async (key) => {
    setSigning(key)
    try {
      await approve(caseId, key)
      await load()
      setWatch((w) => w + 1)
    } catch (err) {
      setError(err.message)
    } finally {
      setSigning(null)
    }
  }

  if (!data) {
    return error ? <Failure code={error} /> : <p className="micro">Reading the file…</p>
  }

  const { case: c, filings, awaiting_signature: awaiting } = data
  const lapsed = LAPSED.has(c.status)
  const me = identity()

  return (
    <>
      <h1 className="display live-title">{c.case_id}</h1>
      <dl className="live-facts">
        <Fact k="State" v={c.status} status={c.status} />
        <Fact k="Authority" v={c.authority ?? 'not routed'} />
        <Fact k="Tier" v={c.escalation_tier} />
        <Fact k="Street" v={segmentName(c.segment)} />
        <Fact k="Statutory deadline" v={when(c.sla_deadline)} />
        <Fact k="Households on it" v={c.corroboration} />
      </dl>

      {error && <Failure code={error} />}

      <SectionHead
        n="§ 1"
        kicker="Rule 4"
        title="Nothing is filed until a person signs."
        note={awaiting.length ? `${awaiting.length} waiting` : 'nothing waiting'}
      />
      {awaiting.length === 0 && (
        <p className="sans dim live-note">No draft is waiting for a signature on this case.</p>
      )}
      {awaiting.map((a) => (
        <div key={a.idempotency_key} className="live-sign" data-lapsed={lapsed ? 'yes' : 'no'}>
          <p className="meta">Tier {a.tier} · {a.authority}</p>
          <p className="sub">{a.message}</p>
          <blockquote className="sans live-sign-quote">{a.body}</blockquote>
          {lapsed ? (
            <p className="sans dim">
              This case is {c.status}. The draft lapsed unsigned, and signing it now would file a
              complaint the case has already let go.
            </p>
          ) : a.yours === false ? (
            <p className="sans dim">
              Waiting on the household chosen to carry this filing, which is not this browser.
            </p>
          ) : (
            <button
              type="button"
              className="action action-indigo"
              disabled={signing !== null}
              onClick={() => sign(a.idempotency_key)}
            >
              {signing === a.idempotency_key ? 'Signing' : `Sign as ${me.member_id}`}
              <Icon name="arrowRight" size={15} />
            </button>
          )}
        </div>
      ))}

      <SectionHead
        n="§ 2"
        kicker="On file"
        title="What goes out over a name."
        note={`${filings.length} filing${filings.length === 1 ? '' : 's'}`}
      />
      {filings.length === 0 && (
        <p className="sans dim live-note">
          {c.authority ? 'No filing drafted yet.' : 'Not routed, so there is no one to write to.'}
        </p>
      )}
      <div className="live-filings">
        {filings.map((f) => (
          <Document
            key={f.idempotency_key}
            kind={`FILING · TIER ${f.tier}`}
            docRef={f.external_ref ?? f.idempotency_key.slice(0, 10)}
            authority={f.authority}
            fields={[
              { k: 'Signed by', v: f.signed_by ?? '— not signed —', tone: f.signed_by ? undefined : 'terracotta' },
              { k: 'Signed at', v: when(f.signed_at) },
              { k: 'Submitted', v: f.submitted_at ? when(f.submitted_at) : '— not yet —' },
              { k: 'Ticket', ...ticket(f, c, watching) },
            ]}
          >
            <p className="live-body-text">{f.body}</p>
          </Document>
        ))}
      </div>

      <div className="live-actions">
        <button type="button" className="micro live-refresh" onClick={() => load()}>
          Read it again
        </button>
        <Link to="/live" className="action">
          Your reports
          <Icon name="arrowRight" size={15} />
        </Link>
        <Link to="/case" className="action">
          How a case runs
          <Icon name="arrowRight" size={15} />
        </Link>
      </div>
    </>
  )
}
