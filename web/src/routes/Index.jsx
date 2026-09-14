import { useState } from 'react'
import { Link } from 'react-router-dom'
import HeroSection from '../components/HeroSection.jsx'
import StreetPlan from '../components/StreetPlan.jsx'
import ReportInput from '../components/ReportInput.jsx'
import Icon from '../components/Icon.jsx'
import { SectionHead } from '../components/Bits.jsx'
import { useGsap, gsap, ScrollTrigger, RISE } from '../lib/motion.js'
import { useScenario } from '../lib/scenario.jsx'

/** The file's contents. The first two lines belong to the worked example. */
const register = (scenario) => [
  {
    to: '/case',
    n: '01',
    title: 'The case',
    sub: scenario.CASE.id,
    line: scenario.copy.registerCase,
    icon: 'document',
  },
  {
    to: '/street',
    n: '02',
    title: 'The street',
    sub: 'Ward 12 layout',
    line: scenario.copy.registerStreet,
    icon: 'houses',
  },
  {
    to: '/process',
    n: '03',
    title: 'The process',
    sub: 'Seven stages',
    line: 'Signal to close, and the three things that run when nobody is asking for anything.',
    icon: 'ladder',
  },
  {
    to: '/about',
    n: '04',
    title: 'Boundaries',
    sub: 'What it will not do',
    line: 'The refusals are load-bearing. Naming them is the only honest way to describe what is left.',
    icon: 'stamp',
  },
]

export default function Index() {
  const [stage, setStage] = useState(0)
  const { scenario } = useScenario()
  const { CASE, copy } = scenario
  const COVER = [
    { k: 'File', v: CASE.id },
    { k: 'Ward', v: `${CASE.ward} · ${CASE.ward_name}` },
    { k: 'Opened', v: copy.opened },
    { k: 'Status', v: CASE.status, tone: 'terracotta' },
  ]
  const FIGURES = copy.figures
  const REGISTER = register(scenario)

  const scope = useGsap((self, { reduced }) => {
    // Without the scroll triggers nothing would ever advance the
    // drawing, so it arrives already traced rather than blank.
    if (reduced) {
      setStage(2)
      return
    }

    gsap.from('[data-rise]', {
      ...RISE,
      delay: 0.15,
      stagger: 0.09,
    })

    gsap.from('.cover-cell', {
      opacity: 0,
      duration: 0.7,
      stagger: 0.07,
      ease: 'power1.out',
    })

    self.add(() => {
      gsap.utils.toArray('[data-fig]').forEach((el) => {
        gsap.from(el, {
          scrollTrigger: { trigger: el, start: 'top 82%' },
          y: 28,
          opacity: 0,
          duration: 0.85,
          ease: 'power2.out',
        })
      })

      const preview = document.querySelector('[data-street-preview]')
      if (!preview) return
      ScrollTrigger.create({
        trigger: preview,
        start: 'top 72%',
        onEnter: () => setStage(1),
      })
      ScrollTrigger.create({
        trigger: preview,
        start: 'top 38%',
        onEnter: () => setStage(2),
      })
    })
  }, [])

  return (
    <div ref={scope}>
      {/* ---- the plate ------------------------------------------- */}
      <section className="plate">
        <div className="page">
          <div className="cover" aria-label="File cover">
            {COVER.map((c) => (
              <div className="cover-cell" key={c.k}>
                <span className="micro">{c.k}</span>
                <span className={`mono cover-v${c.tone ? ` ink-${c.tone}` : ''}`}>{c.v}</span>
              </div>
            ))}
          </div>

          <div className="plate-grid">
            <div className="plate-left">
              <p className="meta plate-kicker" data-rise>
                <Icon name="survey" size={14} />
                Register of pursued complaints · opened 06 September 2026
              </p>

              <h1 className="colossal plate-statement" data-rise>
                A complaint closed
                <br />
                is not a problem
                <br />
                <em>fixed.</em>
              </h1>

              {/* Directly under the statement, so the one thing a visitor can
                  do here is on screen when the page opens, not below the fold. */}
              <div id="report" data-rise>
                <ReportInput />
              </div>

              <p className="lead plate-lead" data-rise>
                In Bengaluru, civic complaints are marked resolved with no work done.
                One pothole was closed fifteen times. Panchayat is what happens next.
              </p>
            </div>

            <div className="plate-right" data-rise>
              <HeroSection />
            </div>
          </div>
        </div>
      </section>

      {/* ---- the documented problem ------------------------------ */}
      <section className="band">
        <div className="page">
          <SectionHead
            n="§ 1"
            kicker="The record, not the pitch"
            title="This is documented, not invented."
            note="Sources: BBMP grievance data · resident reports"
          />

          <div className="ledger">
            <aside className="margin marginalia">
              <b>Note</b>
              Discovery is not the failure.
              <span className="hand">the street already knows</span>
            </aside>

            <div className="prose">
              <p className="opener">{copy.recordOpener}</p>
              <p>
                So complaints are filed and complaints are closed, and the two events have very
                little to do with each other. A ticket is a sentence written by a desk about
                itself. It is not evidence that anyone came.
              </p>
            </div>
          </div>

          <div className="figures">
            {FIGURES.map((f) => (
              <figure className="figure" key={f.n} data-fig>
                <div className="figure-n">
                  <span className="mono">{f.n}</span>
                  <span className="micro">{f.unit}</span>
                </div>
                <figcaption className="sans dim">{f.t}</figcaption>
              </figure>
            ))}
          </div>
        </div>
      </section>

      {/* ---- the street, in preview ------------------------------ */}
      <section className="band band-sunk">
        <div className="page">
          <SectionHead
            n="§ 2"
            kicker={copy.preview.kicker}
            title={copy.preview.title}
            note={copy.preview.note}
          />

          <div className="preview-lead">
            <p className="sub preview-claim">{copy.preview.claim}</p>
            <Link to="/street" className="action action-indigo preview-link">
              Open the drawing
              <Icon name="arrowRight" size={15} />
            </Link>
          </div>

          <div className="plan-frame overflow-x" data-street-preview>
            <div className="plan-scroll">
              <StreetPlan stage={stage} id="preview" />
            </div>
          </div>
          <p className="micro plan-hint">Drawing is wider than this screen — drag it sideways.</p>

          <p className="micro plan-caption">{copy.preview.caption}</p>
        </div>
      </section>

      {/* ---- the register ---------------------------------------- */}
      <section className="band">
        <div className="page">
          <SectionHead n="§ 3" kicker="Contents" title="What is in the file." note="Four parts" />

          <ol className="register">
            {REGISTER.map((r) => (
              <li key={r.to}>
                <Link to={r.to} className="register-row">
                  <span className="mono register-n">{r.n}</span>
                  <span className="register-icon">
                    <Icon name={r.icon} size={26} />
                  </span>
                  <span className="register-main">
                    <span className="register-title sub">{r.title}</span>
                    <span className="sans dim register-line">{r.line}</span>
                  </span>
                  <span className="mono register-sub">{r.sub}</span>
                  <span className="register-arrow">
                    <Icon name="arrowRight" size={18} />
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </div>
  )
}
