import { useState } from 'react'
import { Link } from 'react-router-dom'
import HeroSection from '../components/HeroSection.jsx'
import StreetPlan from '../components/StreetPlan.jsx'
import ReportInput from '../components/ReportInput.jsx'
import Icon from '../components/Icon.jsx'
import { SectionHead } from '../components/Bits.jsx'
import { CASE } from '../data/case.js'
import { useGsap, gsap, ScrollTrigger, RISE } from '../lib/motion.js'

const COVER = [
  { k: 'File', v: CASE.id },
  { k: 'Ward', v: `${CASE.ward} · ${CASE.ward_name}` },
  { k: 'Opened', v: '06 SEP 2026' },
  { k: 'Status', v: CASE.status, tone: 'terracotta' },
]

const FIGURES = [
  {
    n: '15',
    unit: 'times',
    t: 'One pothole complaint in this city was opened and closed again, on the same stretch of road, with the road unchanged.',
  },
  {
    n: '7',
    unit: 'days',
    t: 'The statutory window a household is expected to count, unaided, while doing everything else a week contains.',
  },
  {
    n: '0',
    unit: 'work orders',
    t: 'Attached to the closure on this case. The ticket says the supply was restored. Nothing says anyone went.',
  },
]

const REGISTER = [
  {
    to: '/case',
    n: '01',
    title: 'The case',
    sub: 'PNC-2026-0912',
    line: 'Lakshmi reports on the third morning. Eleven entries later, the desk stamps it closed and three houses are still dry.',
    icon: 'document',
  },
  {
    to: '/street',
    n: '02',
    title: 'The street',
    sub: 'Ward 12 layout',
    line: 'Twenty-four properties, two mains. Read the drawing and the cluster stops being a coincidence.',
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

              <p className="lead plate-lead" data-rise>
                In Bengaluru, civic complaints are marked resolved with no work done.
                One pothole was closed fifteen times. Panchayat is what happens next.
              </p>

              <div data-rise>
                <ReportInput />
              </div>
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
              <p className="opener">
                When the water fails, the building group knows inside fifteen minutes. Nobody
                needs to be told. What nobody has is the stamina to file against the right
                body, hold a statutory clock for eleven weeks, notice the day it breaches, and
                climb to the next authority with the record intact.
              </p>
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
            kicker="Drawing PNC-W12-01"
            title="Next door is not the same as downstream."
            note="4th Cross · 24 properties · 2 mains"
          />

          <div className="preview-lead">
            <p className="sub preview-claim">
              Three households on this street share a fault. They are not neighbours.
              The house between two of them has water, because it is on the other main.
            </p>
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

          <p className="micro plan-caption">
            Fig. 1 — Water supply layout, 4th Cross. Properties 9, 12 and 17 are served by Main A.
            Property 11, which shares a wall with 12, is served by Main B and is unaffected.
          </p>
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
