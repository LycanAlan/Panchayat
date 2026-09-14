import { Link } from 'react-router-dom'
import Icon from '../components/Icon.jsx'
import { SectionHead, Facing } from '../components/Bits.jsx'
import { DOES, DOES_NOT } from '../data/case.js'
import { useScenario } from '../lib/scenario.jsx'
import { useGsap, gsap } from '../lib/motion.js'

const PRINCIPLES = [
  {
    n: '01',
    head: 'A draft is not a filing.',
    body:
      'No filing against a public body leaves a household without a named person approving it first, read back in the language they speak. The liability lands on the household, so the decision is theirs and it is taken before anything is sent.',
  },
  {
    n: '02',
    head: 'Pressure points outward.',
    body:
      'Collective weight may be assembled against an institution and never against a person or a household. There is no version of this that helps neighbours file against each other, and the aggregation is built so that it cannot be turned that way.',
  },
  {
    n: '03',
    head: 'What a household says stays with the household.',
    body:
      'A position is held privately; only a claim ever crosses out of it, and a claim carries the fault and nothing else. Income, health, arrears and schooling do not travel, at any threshold, for any reason.',
  },
  {
    n: '04',
    head: 'Withdrawal is real.',
    body:
      'A household that pulls out leaves the cluster, is not spoken for afterwards, and anything already filed on its behalf carries a correction. Nothing continues on the strength of a consent that has been taken back.',
  },
  {
    n: '05',
    head: 'Merges come apart again.',
    body:
      'When two cases join, the record of which claims came from where is kept. A merge made in error has to be reversible, or a household ends up holding somebody else’s complaint.',
  },
  {
    n: '06',
    head: 'Nothing is filed with the police.',
    body:
      'Read, track and advise only. There is no autonomous route from this system into a criminal complaint against anybody, and adding one is not a feature waiting to be built.',
  },
]

export default function About() {
  const { scenario } = useScenario()
  // The first refusal names the worked example's own trade, so it reads true
  // on whichever case the reader came from.
  const doesNot = [scenario.copy.doesNotFirst, ...DOES_NOT.slice(1)]
  const scope = useGsap((self, { reduced }) => {
    if (reduced) return
    self.add(() => {
      gsap.utils.toArray('[data-principle]').forEach((el) => {
        gsap.from(el, {
          scrollTrigger: { trigger: el, start: 'top 88%' },
          y: 24,
          opacity: 0,
          duration: 0.75,
          ease: 'power2.out',
        })
      })
    })
  }, [])

  return (
    <div ref={scope} className="about">
      <section className="band band-tight">
        <div className="page">
          <p className="meta">Boundaries · standing text</p>
          <h1 className="display">
            The refusals are
            <br />
            <em>load-bearing.</em>
          </h1>
          <p className="lead">
            Naming what something will not do is the only honest way to describe what is left.
            Every line below is a constraint the implementation actually enforces, not an
            aspiration attached to it afterwards.
          </p>
        </div>
      </section>

      {/* ---- does / does not ------------------------------------ */}
      <section className="band band-sunk">
        <div className="page">
          <SectionHead n="§ 1" kicker="Scope" title="Both columns are the product." note="Read them together" />
          <Facing
            left={{ title: 'What this does', items: DOES }}
            right={{ title: 'What it does not', items: doesNot }}
          />
        </div>
      </section>

      {/* ---- principles ----------------------------------------- */}
      <section className="band">
        <div className="page">
          <SectionHead n="§ 2" kicker="Standing rules" title="Six that cannot be traded away." note="Enforced, not intended" />

          <ol className="principles">
            {PRINCIPLES.map((p) => (
              <li key={p.n} className="principle" data-principle>
                <span className="mono principle-n">{p.n}</span>
                <div>
                  <h3 className="sub principle-head">{p.head}</h3>
                  <p className="sans principle-body">{p.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ---- minimisation --------------------------------------- */}
      <section className="band band-sunk">
        <div className="page">
          <SectionHead n="§ 3" kicker="Privacy" title="Minimisation, not anonymity." note="Said plainly" />
          <div className="ledger">
            <aside className="margin marginalia">
              <b>Careful</b>
              Eight houses on a cross street.
              <span className="hand">precise enough to file = precise enough to identify</span>
            </aside>
            <div className="prose">
              <p className="opener">
                A complaint precise enough to act on is precise enough to identify the house
                it came from. On a street of eight properties, naming the feeder and the week
                narrows it to one or two doors, and no amount of careful wording changes that
                arithmetic. Promising anonymity here would be a lie with a technical
                vocabulary attached.
              </p>
              <p>
                What is actually guaranteed is narrower and true: the fault crosses, and
                nothing else does. Income, health, arrears and schooling never leave the
                household, and no aggregate is ever assembled that would let them be inferred
                from what did.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ---- built / not built ---------------------------------- */}
      <section className="band">
        <div className="page">
          <SectionHead n="§ 4" kicker="State of the work" title="Built, and not built." note="Five days" />

          <div className="built">
            <section data-principle>
              <h3 className="label">Built and running</h3>
              <ul className="built-list">
                <li>The institutional tail, end to end, for water and for roads, on one ward of curated routing data.</li>
                <li>Text intake in four languages, nine coordinating parts, one household graph.</li>
                <li>The temporal path: scheduled wakes, breach detection, escalation, closure checks.</li>
                <li>Calibrated institution simulators, reached across a boundary, holding their own state.</li>
                <li>An evaluation harness, and the same suite green against both storage backends.</li>
              </ul>
            </section>

            <section data-principle>
              <h3 className="label">Designed, drawn, not built</h3>
              <ul className="built-list built-list--open">
                <li>Mutual-aid and shared-cost tails, where a street funds its own interim fix.</li>
                <li>Voice and vernacular intake. Today the four languages are typed, not spoken.</li>
                <li>Per-member privacy inside a household, rather than at the household edge.</li>
                <li>Cross-neighbourhood federation, where wards corroborate each other.</li>
              </ul>
              <p className="micro built-note">
                Naming your own compromises reads as judgement. Claiming them as shipped reads
                as something else.
              </p>
            </section>
          </div>
        </div>
      </section>

      {/* ---- honesty about the stack ---------------------------- */}
      <section className="band band-sunk">
        <div className="page">
          <SectionHead n="§ 5" kicker="Provenance" title="What you are looking at." note="Say it out loud" />
          <div className="ledger">
            <aside className="margin marginalia">
              <b>Fixtures</b>
              This site reads from the case file, not from production.
            </aside>
            <div className="prose">
              <p className="opener">
                Ward 12 is a real ward and the statutory windows, authorities and citations on
                these pages are real. The households are synthetic and the receiving desks are
                calibrated simulators, which is the only responsible way to demonstrate a
                system that files against public bodies.
              </p>
              <p>
                The semantic term in the correlation score genuinely did not run: model access
                on this account is refused at the account level, so every cluster shown here
                formed on topology and recency alone, renormalised. That is reported on the
                case page rather than hidden, because a cluster that does not say which terms
                ran is claiming agreement it never computed.
              </p>
            </div>
          </div>

          <div className="street-foot">
            <Link to="/" className="action action-indigo">
              Back to the file
              <Icon name="arrowRight" size={15} />
            </Link>
            <Link to="/case" className="action">
              Read the case
              <Icon name="arrowRight" size={15} />
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}
