import { Link } from 'react-router-dom'
import Icon from '../components/Icon.jsx'
import Ladder from '../components/Ladder.jsx'
import { SectionHead } from '../components/Bits.jsx'
import { SPINE, PATHS } from '../data/case.js'
import { JURISDICTION_NOTE } from '../data/authorities.js'
import { useGsap, gsap } from '../lib/motion.js'

const STAGE_ICON = {
  SIGNAL: 'tap',
  DELIBERATE: 'survey',
  REPRESENT: 'document',
  ACT: 'nib',
  TRACK: 'clock',
  ESCALATE: 'ladder',
  CLOSE: 'stamp',
}

export default function Process() {
  const scope = useGsap((self, { reduced }) => {
    if (reduced) return
    self.add(() => {
      gsap.utils.toArray('[data-stage-row]').forEach((el, i) => {
        gsap.from(el, {
          scrollTrigger: { trigger: el, start: 'top 86%' },
          x: -18,
          opacity: 0,
          duration: 0.7,
          delay: (i % 3) * 0.04,
          ease: 'power2.out',
        })
      })
      gsap.utils.toArray('[data-path-row]').forEach((el) => {
        gsap.from(el, {
          scrollTrigger: { trigger: el, start: 'top 88%' },
          y: 22,
          opacity: 0,
          duration: 0.7,
          ease: 'power2.out',
        })
      })
    })
  }, [])

  return (
    <div ref={scope} className="process">
      <section className="band band-tight">
        <div className="page">
          <p className="meta">Standing orders · Ward 12</p>
          <h1 className="display">
            One household is enough
            <br />
            to run the whole <em>procedure.</em>
          </h1>
          <p className="lead">
            The individual case is the product and it is complete on its own. Clustering does
            not gate it, does not start it, and on a quiet street does not run for weeks at a
            time. What follows happens whether or not anybody else on the road reports
            anything.
          </p>
        </div>
      </section>

      {/* ---- the spine ------------------------------------------ */}
      <section className="band band-sunk">
        <div className="page">
          <SectionHead n="§ 1" kicker="The spine" title="Seven stages, in order." note="Signal → Close" />

          <ol className="spine">
            {SPINE.map((s, i) => (
              <li key={s.name} className="spine-row" data-path={s.path} data-stage-row>
                <span className="mono spine-n">{String(s.n).padStart(2, '0')}</span>
                <span className="spine-icon">
                  <Icon name={STAGE_ICON[s.name]} size={24} />
                </span>
                <span className="spine-name mono">{s.name}</span>
                <span className="spine-gloss sans">{s.gloss}</span>
                <span className="micro spine-path">{s.path}</span>
                {i < SPINE.length - 1 && <span className="spine-link" aria-hidden="true" />}
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ---- four paths ----------------------------------------- */}
      <section className="band">
        <div className="page">
          <SectionHead
            n="§ 2"
            kicker="Execution"
            title="Only one of these is asked for."
            note="Four paths · one table"
          />

          <div className="ledger">
            <aside className="margin marginalia">
              <b>Consequence</b>
              A request cannot wait seven days, so waiting is not part of the request.
              <span className="hand">the clock lives elsewhere</span>
            </aside>

            <div>
              <div className="overflow-x">
                <table className="paths">
                  <thead>
                    <tr>
                      <th className="micro">Path</th>
                      <th className="micro">Begins when</th>
                      <th className="micro">Runs on</th>
                    </tr>
                  </thead>
                  <tbody>
                    {PATHS.map((p) => (
                      <tr key={p.name} data-tone={p.tone} data-path-row>
                        <td>
                          <span className="paths-name">{p.name}</span>
                        </td>
                        <td className="sans dim">{p.trigger}</td>
                        <td className="mono">{p.runs}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <p className="sans dim paths-note">
                The separation is not an implementation detail. A household&rsquo;s request
                finishes in seconds; a statutory window finishes in a week; institutions keep
                their own records and are reached across a boundary rather than through a
                shared table. Collapsing any of those into the others is how the waiting
                quietly stops happening.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ---- jurisdiction --------------------------------------- */}
      <section className="band band-sunk">
        <div className="page">
          <SectionHead n="§ 3" kicker="Routing" title="Looked up, never generated." note="31 curated entries" />
          <div className="ledger">
            <aside className="margin marginalia">
              <b>Hard rule 3</b>
              Every routing decision carries a citation.
            </aside>
            <div className="prose">
              <p className="opener">{JURISDICTION_NOTE}</p>
              <p>
                A confidently wrong authority is worse than no answer at all. It produces a
                filing that is received, logged, and closed as misdirected — which looks from
                the outside exactly like a household that was attended to, and burns the
                statutory window on the way.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ---- the ladder ----------------------------------------- */}
      <section className="band">
        <div className="page">
          <SectionHead n="§ 4" kicker="Escalation" title="Where a case can climb." note="Five rungs" />
          <Ladder />
          <p className="micro ladder-foot">
            Each rung is an authority with a window and an instrument behind it. A case
            climbs on a breach, never on impatience, and it arrives carrying the whole record
            of the rung below.
          </p>
        </div>
      </section>

      {/* ---- idempotence ---------------------------------------- */}
      <section className="band band-sunk">
        <div className="page">
          <SectionHead n="§ 5" kicker="Discipline" title="Filed once, however many times it retries." note="Institutional actions" />
          <div className="ledger">
            <aside className="margin marginalia">
              <b>Hard rule 5</b>
              A duplicate reads as spam, and gets both copies closed.
            </aside>
            <div className="prose">
              <p className="opener">
                A scheduled wake that fires twice must not produce two filings. The second
                copy does not double the pressure — it gives the receiving desk a reason to
                dispose of both, and it costs the household the credibility the first one had.
              </p>
              <p>
                So every action against a public body is keyed and checked before it is sent,
                and a retry that finds its own earlier work simply reports it. The same
                discipline covers merges: a cluster that joins two cases keeps the provenance
                to take them apart again, because a household that is merged in error must be
                able to leave with its own claims and nobody else&rsquo;s.
              </p>
            </div>
          </div>

          <div className="street-foot">
            <Link to="/case" className="action action-indigo">
              See it run on one case
              <Icon name="arrowRight" size={15} />
            </Link>
            <Link to="/about" className="action">
              What it will not do
              <Icon name="arrowRight" size={15} />
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}
