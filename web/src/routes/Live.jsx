import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Document from '../components/Document.jsx'
import Icon from '../components/Icon.jsx'
import { SectionHead } from '../components/Bits.jsx'
import { approve, getCase, identity, listCases } from '../lib/api.js'
import { segmentName } from '../data/segments.js'
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
  runtime_unavailable: 'The runtime did not answer. A cold start can take a few seconds, so try again.',
  runtime_not_configured: 'The web Lambda has no runtime to call. That is a deploy problem, not yours.',
}

function Failure({ code }) {
  return (
    <div className="live-failure">
      <p className="mono ink-terracotta">{code}</p>
      <p className="sans dim">{HINTS[code] ?? 'The request did not complete. Nothing was signed or filed.'}</p>
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
            Not a fixture. Everything below came back from AgentCore when this page loaded.
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

  const load = useCallback(async () => {
    try {
      setData(await getCase(caseId))
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }, [caseId])

  useEffect(() => {
    load()
  }, [load])

  const sign = async (key) => {
    setSigning(key)
    try {
      await approve(key)
      await load()
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
              { k: 'Ticket', v: f.external_ref ?? '— none issued —' },
            ]}
          >
            <p className="live-body-text">{f.body}</p>
          </Document>
        ))}
      </div>

      <div className="live-actions">
        <button type="button" className="micro live-refresh" onClick={load}>
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
