import { useState } from 'react'
import { Link } from 'react-router-dom'
import StreetPlan from '../components/StreetPlan.jsx'
import Icon from '../components/Icon.jsx'
import { SectionHead } from '../components/Bits.jsx'
import { useScenario } from '../lib/scenario.jsx'
import { useGsap, useMediaQuery, ScrollTrigger } from '../lib/motion.js'

// A pinned sheet plus a paragraph needs both height and width. Where
// there is not enough of either, the page does not pin at all — it
// shows the finished drawing and reads the four beats as prose. A
// half-pinned layout is how text ends up hidden behind a diagram.
const CANNOT_PIN = '(max-width: 900px), (max-height: 640px)'

export default function Street() {
  const { scenario } = useScenario()
  const { HOUSES, PLAN, byNumber, CORROBORATING, DECOY } = scenario.DRAWING
  const words = scenario.copy.street
  const BEATS = words.beats.map((b, i) => ({ ...b, stage: i, n: String(i + 1).padStart(2, '0') }))
  const stacked = useMediaQuery(CANNOT_PIN)
  const [stage, setStage] = useState(0)
  const [probe, setProbe] = useState(null)

  const scope = useGsap((self, { reduced }) => {
    if (reduced || stacked) {
      setStage(3)
      return
    }
    setStage(0)
    self.add(() => {
      document.querySelectorAll('[data-beat-stage]').forEach((el) => {
        const s = Number(el.dataset.beatStage)
        ScrollTrigger.create({
          trigger: el,
          start: 'top 58%',
          end: 'bottom 58%',
          onEnter: () => setStage(s),
          onEnterBack: () => setStage(s),
        })
      })
    })
  }, [stacked])

  const beat = BEATS[stage] ?? BEATS[0]
  const onMainA = HOUSES.filter((o) => o.feeder === 'A').length
  const h = probe ? byNumber(probe) : null
  const shares = h ? HOUSES.filter((o) => o.feeder === h.feeder && o.n !== h.n).map((o) => o.n) : []

  return (
    <div ref={scope} className="street">
      <section className="band band-tight">
        <div className="page">
          <p className="meta">{words.meta}</p>
          <h1 className="display street-title">
            {words.title[0]}
            <br />
            {words.title[1]}<em>{words.title[2]}</em>
          </h1>
          <p className="lead">{words.lead}</p>
        </div>
      </section>

      {/* ---- the reveal -----------------------------------------
          Pinned: the drawing holds the top of the frame and the
          caption sits under it inside the same sticky block, so no
          text ever travels behind the sheet. The rail below is
          empty — it only gives the section the scroll length the
          four beats need.
          Stacked: no pinning, the finished drawing once, then the
          beats as ordinary prose. */}
      {stacked ? (
        <section className="street-flat">
          <div className="page">
            <div className="plan-frame overflow-x">
              <div className="plan-scroll">
                <StreetPlan stage={3} id="street" />
              </div>
            </div>
            <p className="micro plan-hint">
              Drawing is wider than this screen — drag it sideways.
            </p>

            <ol className="street-flat-beats">
              {BEATS.map((b) => (
                <li key={b.n} className="street-say">
                  <span className="mono street-beat-n">{b.n}</span>
                  <h2 className="sub street-beat-head">{b.head}</h2>
                  <p className="sans street-beat-body">{b.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>
      ) : (
        <section className="street-scroll">
          <div className="street-stage">
            <div className="page street-stage-in">
              <div className="plan-frame plan-frame--sticky overflow-x">
                <div className="plan-scroll">
                  <StreetPlan stage={stage} id="street" />
                </div>
              </div>

              <div className="street-caption">
                <ol className="street-track" aria-hidden="true">
                  {BEATS.map((b) => (
                    <li key={b.n} className="mono" data-on={stage >= b.stage ? 'yes' : 'no'}>
                      {b.n}
                    </li>
                  ))}
                </ol>

                <div className="street-say" key={beat.n} aria-live="polite">
                  <span className="mono street-beat-n">{beat.n}</span>
                  <h2 className="sub street-beat-head">{beat.head}</h2>
                  <p className="sans street-beat-body">{beat.body}</p>
                </div>
              </div>
            </div>
          </div>

          <div className="street-rail" aria-hidden="true">
            {BEATS.map((b) => (
              <div key={b.n} className="street-rung" data-beat-stage={b.stage} />
            ))}
          </div>
        </section>
      )}

      {/* ---- read it by hand ------------------------------------ */}
      <section className="band band-sunk">
        <div className="page">
          <SectionHead
            n="§ 2"
            kicker="Read it yourself"
            title={words.probeTitle}
            note="Hover, or tab through"
          />

          <div className="probe-grid">
            <div>
              <div className="plan-frame overflow-x">
                <div className="plan-scroll">
                  <StreetPlan stage={2} probe={probe} onProbe={setProbe} id="probe" />
                </div>
              </div>
              <p className="micro plan-hint">
                Drawing is wider than this screen — drag it sideways.
              </p>
            </div>

            <aside className="probe-out" aria-live="polite">
              {h ? (
                <>
                  <p className="label">Property</p>
                  <p className="mono probe-door">{h.door}</p>
                  <dl className="probe-facts">
                    <div>
                      <dt className="micro">{words.probe.line}</dt>
                      <dd className="mono">{words.probe.lineValue(h, PLAN)}</dd>
                    </div>
                    <div>
                      <dt className="micro">{words.probe.depth}</dt>
                      <dd className="mono">{h.feeder === 'A' ? PLAN.mainA.depth : PLAN.mainB.depth}</dd>
                    </div>
                    <div>
                      <dt className="micro">Doors either side</dt>
                      <dd className="mono">
                        {[h.n - 1, h.n + 1]
                          .filter((n) => n >= 1 && n <= 24)
                          .map((n) => `${String(n).padStart(2, '0')} — ${words.probe.either(byNumber(n).feeder)}`)
                          .join(' · ')}
                      </dd>
                    </div>
                    <div>
                      <dt className="micro">{words.probe.shares}</dt>
                      <dd className="mono probe-shares">
                        {shares.map((n) => String(n).padStart(2, '0')).join(' · ')}
                      </dd>
                    </div>
                    <div>
                      <dt className="micro">State</dt>
                      <dd className={`mono ${CORROBORATING.includes(h.n) ? 'ink-terracotta' : ''}`}>
                        {CORROBORATING.includes(h.n)
                          ? words.probe.claim
                          : h.n === DECOY
                            ? words.probe.decoy
                            : words.probe.plain}
                      </dd>
                    </div>
                  </dl>
                </>
              ) : (
                <div className="probe-empty">
                  <Icon name="junction" size={30} />
                  <p className="sans dim">{words.probe.empty}</p>
                  <p className="micro">{words.probe.count(onMainA, HOUSES.length)}</p>
                </div>
              )}
            </aside>
          </div>
        </div>
      </section>

      {/* ---- why it matters ------------------------------------- */}
      <section className="band">
        <div className="page">
          <SectionHead n="§ 3" kicker="Consequence" title="Why the drawing decides the case." note="Topology term · weight 0.40" />

          <div className="ledger">
            <aside className="margin marginalia">
              <b>Ambient</b>
              Runs when a claim row arrives. Nothing asked it to.
              <span className="hand">no model on a quiet street</span>
            </aside>

            <div className="prose">
              <p className="opener">{words.why[0]}</p>
              <p>{words.why[1]}</p>
              <p>{words.why[2]}</p>
            </div>
          </div>

          <div className="street-foot">
            <Link to="/case" className="action action-indigo">
              Back to the case
              <Icon name="arrowRight" size={15} />
            </Link>
            <Link to="/process" className="action">
              How the pursuit runs
              <Icon name="arrowRight" size={15} />
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}
