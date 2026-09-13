import { useState } from 'react'
import { Link } from 'react-router-dom'
import StreetPlan from '../components/StreetPlan.jsx'
import Icon from '../components/Icon.jsx'
import { SectionHead } from '../components/Bits.jsx'
import { HOUSES, PLAN, byNumber, CORROBORATING, DECOY } from '../data/street.js'
import { useGsap, useMediaQuery, ScrollTrigger } from '../lib/motion.js'

// A pinned sheet plus a paragraph needs both height and width. Where
// there is not enough of either, the page does not pin at all — it
// shows the finished drawing and reads the four beats as prose. A
// half-pinned layout is how text ends up hidden behind a diagram.
const CANNOT_PIN = '(max-width: 900px), (max-height: 640px)'

const BEATS = [
  {
    stage: 0,
    n: '01',
    head: 'Twenty-four houses, in the order the numbers run.',
    body:
      'This is the street as everyone holds it in their head: a row of doors, 12/01 at one end and 12/24 at the other. Nothing in this picture can tell you which two households share a fault.',
  },
  {
    stage: 1,
    n: '02',
    head: 'Two mains, at two depths, laid seventeen years apart.',
    body:
      'Main A went in with the 1994 extension — 300 mm asbestos cement, 1.54 m down. Main B is 2011, ductile iron, deeper. Each property was teed into whichever was live the year it connected. Read the tag under each door number: that letter is the only thing that decides who shares a failure.',
  },
  {
    stage: 2,
    n: '03',
    head: 'Follow the feeder, not the footpath.',
    body:
      'Trace Main A and the households on it surface: 09, 12 and 17. They are not adjacent. Nobody living in them would describe the other two as neighbours. Hydraulically they are one household with three taps.',
  },
  {
    stage: 3,
    n: '04',
    head: 'Eleven has water. Eleven shares a wall with twelve.',
    body:
      'Number 11 is tagged B. Its service crosses over Main A without touching it and carries on down to its own feeder, and its supply never faltered. Any reading of this street that starts with proximity puts 11 in the cluster and leaves 17 out — and both of those are wrong.',
  },
]

export default function Street() {
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
          <p className="meta">Drawing PNC-W12-01 · sheet 1 of 1</p>
          <h1 className="display street-title">
            Geographic proximity
            <br />
            is not <em>infrastructure proximity.</em>
          </h1>
          <p className="lead">
            Two households can share a wall and not share a pipe. Two households four doors
            apart can share the same failure. Every clustering decision this system makes
            rests on the second ordering, and the second ordering is invisible from the
            street.
          </p>
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
            title="Pick a house. See where its water comes from."
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
                      <dt className="micro">Feeder</dt>
                      <dd className="mono">
                        Main {h.feeder} · {h.feeder === 'A' ? PLAN.mainA.spec : PLAN.mainB.spec}
                      </dd>
                    </div>
                    <div>
                      <dt className="micro">Invert</dt>
                      <dd className="mono">{h.feeder === 'A' ? PLAN.mainA.depth : PLAN.mainB.depth}</dd>
                    </div>
                    <div>
                      <dt className="micro">Doors either side</dt>
                      <dd className="mono">
                        {[h.n - 1, h.n + 1]
                          .filter((n) => n >= 1 && n <= 24)
                          .map((n) => `${String(n).padStart(2, '0')} — Main ${byNumber(n).feeder}`)
                          .join(' · ')}
                      </dd>
                    </div>
                    <div>
                      <dt className="micro">Shares this main with</dt>
                      <dd className="mono probe-shares">
                        {shares.map((n) => String(n).padStart(2, '0')).join(' · ')}
                      </dd>
                    </div>
                    <div>
                      <dt className="micro">State</dt>
                      <dd className={`mono ${CORROBORATING.includes(h.n) ? 'ink-terracotta' : ''}`}>
                        {CORROBORATING.includes(h.n)
                          ? 'live claim · supply failed'
                          : h.n === DECOY
                            ? 'supply normal · other main'
                            : 'supply normal'}
                      </dd>
                    </div>
                  </dl>
                </>
              ) : (
                <div className="probe-empty">
                  <Icon name="junction" size={30} />
                  <p className="sans dim">
                    Move across the elevation. Each property lights its own service line down
                    to whichever main it is teed into.
                  </p>
                  <p className="micro">
                    {onMainA} of {HOUSES.length} are on Main A. No two of them are next door
                    to each other.
                  </p>
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
              <p className="opener">
                Corroboration is the difference between one household with a story and a
                street with a fault. A single dry tap is answerable — bad motor, empty sump,
                unpaid bill. Three taps on one feeder is a hydraulic statement, and it is much
                harder for a closure to sit on top of.
              </p>
              <p>
                So the weight this system puts on topology is not decoration. Scoring on words
                alone would have found 11 and 12 — same street, same phrasing, same hour — and
                missed 17 entirely. The drawing is what stops that.
              </p>
              <p>
                It also stops the opposite error. The house on the other main scores zero on
                topology, so however similar its wording, it never joins the cluster. A
                pressure complaint in a building that simply forgot to pay does not get to
                stand behind somebody else&rsquo;s breach.
              </p>
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
