import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Document from '../components/Document.jsx'
import StreetPlan from '../components/StreetPlan.jsx'
import LegalClock from '../components/LegalClock.jsx'
import Ladder from '../components/Ladder.jsx'
import Icon from '../components/Icon.jsx'
import Stamp from '../components/Stamp.jsx'
import { SectionHead } from '../components/Bits.jsx'
import { FORM } from '../data/indic.js'
import { useScenario } from '../lib/scenario.jsx'
import { useGsap, gsap, ScrollTrigger } from '../lib/motion.js'

export default function Case() {
  // Everything about the case comes from the worked example the reader is
  // on; the template, the drawing stages and the scroll choreography do not.
  const { scenario } = useScenario()
  const { CASE, FILING, TIMELINE, CLAIMS, CORRELATION, CONTRADICTION, REPORT, VOICES, NOT_THESE } = scenario
  const c = scenario.copy.caseFile
  const [elapsed, setElapsed] = useState(0)
  const [planStage, setPlanStage] = useState(2)

  const scope = useGsap((self, { reduced }) => {
    if (reduced) {
      setElapsed(7)
      setPlanStage(3)
      return
    }

    self.add(() => {
      // Each entry of the record arrives on its own, the way a page
      // is turned rather than the way a list renders.
      gsap.utils.toArray('[data-entry]').forEach((el) => {
        gsap.from(el, {
          scrollTrigger: { trigger: el, start: 'top 88%' },
          y: 26,
          opacity: 0,
          duration: 0.7,
          ease: 'power2.out',
        })
      })

      gsap.utils.toArray('[data-beat]').forEach((el) => {
        gsap.from(el, {
          scrollTrigger: { trigger: el, start: 'top 80%' },
          y: 34,
          opacity: 0,
          duration: 0.95,
          ease: 'power2.out',
        })
      })

      // the clock advances with the reader, one whole day at a time
      const clockTrack = document.querySelector('[data-clock-track]')
      if (clockTrack) {
        ScrollTrigger.create({
          trigger: clockTrack,
          start: 'top 62%',
          end: 'bottom 75%',
          scrub: true,
          onUpdate: (t) => setElapsed(Math.round(t.progress * 7)),
        })
      }

      // the drawing turns from corroboration to contradiction
      const contra = document.querySelector('[data-contradiction]')
      if (contra) {
        ScrollTrigger.create({
          trigger: contra,
          start: 'top 60%',
          onEnter: () => setPlanStage(3),
          onLeaveBack: () => setPlanStage(2),
        })
      }

      // the climax holds still while the page keeps moving past it
      const climax = document.querySelector('[data-climax]')
      if (!climax) return

      if (window.innerWidth > 900) {
        ScrollTrigger.create({
          trigger: climax,
          start: 'top top',
          end: '+=70%',
          pin: '[data-climax-inner]',
          pinSpacing: true,
        })
      }

      ScrollTrigger.create({
        trigger: climax,
        start: 'top 72px',
        end: 'bottom 72px',
        onToggle: (t) => {
          document.documentElement.dataset.plate = t.isActive ? 'ink' : ''
        },
      })
    })
  }, [])

  // The dark masthead belongs to this page only; a route change while
  // the climax is on screen must not leave it stuck.
  useEffect(() => () => {
    document.documentElement.dataset.plate = ''
  }, [])

  return (
    <div ref={scope} className="case">
      {/* ---- file header ---------------------------------------- */}
      <section className="band band-tight case-cover">
        <div className="page">
          <p className="micro worked-example">
            Worked example · synthetic household · simulated desk · not live data
          </p>
          <p className="meta">{c.meta} · Ward {CASE.ward}</p>
          <h1 className="display case-title">
            {c.title[0]}
            <br />
            {c.title[1]}
            <br />
            <em>{c.title[2]}</em>
          </h1>
          <dl className="case-facts">
            <div><dt className="micro">File</dt><dd className="mono">{CASE.id}</dd></div>
            <div><dt className="micro">Household</dt><dd className="mono">{CASE.household.door} · {CASE.household.id}</dd></div>
            <div><dt className="micro">Subject</dt><dd className="mono">{CASE.subject}</dd></div>
            <div><dt className="micro">Ticket</dt><dd className="mono">{FILING.ref}</dd></div>
            <div><dt className="micro">State</dt><dd className="mono ink-terracotta">{CASE.status}</dd></div>
          </dl>
        </div>
      </section>

      {/* ---- 06 September --------------------------------------- */}
      <section className="band chapter" data-beat>
        <div className="page chapter-grid">
          <div className="chapter-date">
            <span className="mono chapter-day">{c.chapter.day}</span>
            <span className="mono chapter-month">{c.chapter.month}</span>
            <span className="micro chapter-time">{c.chapter.time}</span>
          </div>

          <div className="chapter-body">
            <h2 className="display chapter-head">{c.chapterHead}</h2>
            <p className="lead">{c.chapterLead}</p>

            <blockquote className="quote">
              <p className="kn quote-kn">{REPORT.kn}</p>
              <p className="sans dim quote-gloss">{REPORT.gloss}</p>
              <footer className="micro">{REPORT.by}</footer>
            </blockquote>

            <p className="sans dim chapter-note">{c.chapterNote}</p>
          </div>
        </div>
      </section>

      {/* ---- jurisdiction --------------------------------------- */}
      <section className="band band-sunk">
        <div className="page">
          <SectionHead n="§ 1" kicker={c.jurKicker} title="Whose duty is this?" note="Looked up. Never generated." />

          <div className="ledger">
            <aside className="margin marginalia">
              <b>Rule 3</b>
              A hallucinated authority reproduces the exact failure this exists to catch.
              <span className="hand">cite or return nothing</span>
            </aside>

            <div className="jur">
              <div className="jur-hit" data-entry>
                <span className="micro">Correct body</span>
                <h3 className="sub">{c.correctBody}</h3>
                <p className="mono jur-cite">{FILING.rule}</p>
                <p className="mono jur-cite dim">{c.windowLine}</p>
              </div>

              <ul className="jur-not">
                {NOT_THESE.map((b) => (
                  <li key={b.body} data-entry>
                    <span className="mono jur-not-body">{b.body}</span>
                    <span className="sans dim">{b.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ---- the filing ----------------------------------------- */}
      <section className="band">
        <div className="page">
          <SectionHead n="§ 2" kicker={c.filingKicker} title={c.filingTitle} note={c.filingNote} />

          <div className="transform">
            <div className="transform-a" data-entry>
              <Document kind="HOUSEHOLD POSITION · HELD" docRef={CASE.household.id} tilt={-0.6} creased>
                <p className="kn">{REPORT.kn}</p>
                <p className="sans dim">{REPORT.gloss}</p>
              </Document>
              <p className="micro transform-cap">Never leaves the household.</p>
            </div>

            <div className="transform-arrow" aria-hidden="true">
              <Icon name="arrowRight" size={30} />
              <span className="micro">represent</span>
            </div>

            <div className="transform-b" data-entry>
              <Document
                kind={`${FORM.title.kn} · ${FORM.title.en}`}
                docRef={FILING.ref}
                authority={FILING.authority}
                tilt={0.5}
                punched
                fields={[
                  { k: FORM.fields[0].en, v: `${CASE.household.name} (applicant)` },
                  { k: FORM.fields[1].en, v: `${CASE.household.door}, ${CASE.street}, ${FORM.ward.en}` },
                  ...c.filingFields,
                ]}
              >
                <p>{c.filingBody}</p>
              </Document>
              <p className="micro transform-cap">Filed against a body that owes a duty.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ---- the signature -------------------------------------- */}
      <section className="band band-sunk">
        <div className="page">
          <div className="sign-grid">
            <div data-beat>
              <p className="meta">{c.signMeta}</p>
              <h2 className="display">{c.signHead[0]}<br />{c.signHead[1]}</h2>
              <p className="lead">{c.signLead}</p>
              <p className="sans dim">
                A withdrawn household is not spoken for afterwards. Its claim leaves the
                cluster, and anything already filed carries a correction.
              </p>
            </div>

            <div className="sign-doc" data-beat>
              <Document
                kind="DECLARATION"
                docRef={c.signRef}
                authority="Read back in Kannada before signature"
                tilt={-1.1}
                signature={{ name: c.signName, at: c.signAt }}
                annotation="read to me in full — I agree to send it"
                fields={[
                  { k: 'Applicant', v: `${CASE.household.name} · ${CASE.household.door}` },
                  { k: 'Consent', v: 'Given, by name, before lodgement' },
                  { k: 'Scope', v: c.signScope },
                ]}
              />
            </div>
          </div>
        </div>
      </section>

      {/* ---- the clock ------------------------------------------ */}
      <section className="band" data-clock-track>
        <div className="page">
          <SectionHead n="§ 3" kicker={c.clockKicker} title={c.clockTitle} note={c.clockNote} />

          <div className="clock-grid">
            <div className="clock-pin">
              <LegalClock elapsed={elapsed} />
              <div className="clock-readout">
                <span className="micro">Elapsed</span>
                <span className="mono clock-readout-n" data-breach={elapsed >= 7 ? 'yes' : 'no'}>
                  {String(elapsed).padStart(2, '0')} / 07
                </span>
                <span className="micro">
                  {elapsed >= 7 ? c.readoutExpired : c.readoutOpen}
                </span>
              </div>
              <p className="micro clock-fine">
                The window is booked as a wake on a scheduler, not watched by a person.
                Nothing needs to remember it. Nothing needs to stay awake.
              </p>
            </div>

            <ol className="record">
              {TIMELINE.map((t, i) => (
                <li key={`${t.date}-${t.head}`} className="entry" data-tone={t.tone} data-entry>
                  <div className="entry-when mono">
                    <span className="entry-date">{t.date}</span>
                    <span className="entry-time">{t.time}</span>
                  </div>
                  <div className="entry-node" aria-hidden="true" />
                  <div className="entry-body">
                    <h3 className="entry-head">{t.head}</h3>
                    <p className="sans entry-text">{t.body}</p>
                    {t.ref && <span className="mono entry-ref">{t.ref}</span>}
                  </div>
                  <span className="mono entry-n">{String(i + 1).padStart(2, '0')}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      {/* ---- the breach ----------------------------------------- */}
      <section className="band breach-band" data-beat>
        <div className="page breach-grid">
          <div className="breach-date">
            <span className="mono chapter-day">{c.breach.day}</span>
            <span className="mono chapter-month">{c.breach.month}</span>
            <span className="micro chapter-time">{c.breach.time}</span>
          </div>
          <div>
            <h2 className="display ink-terracotta">{c.breachHead[0]}<br />{c.breachHead[1]}</h2>
            <p className="lead">{c.breachLead}</p>
            <p className="mono breach-line">{c.breachLine}</p>
          </div>
        </div>
      </section>

      {/* ---- escalation ----------------------------------------- */}
      <section className="band band-sunk">
        <div className="page">
          <SectionHead n="§ 4" kicker={c.climbKicker} title="The case climbs." note="Tier 1 → Tier 2" />
          <div className="ledger">
            <aside className="margin marginalia">
              <b>Carried up</b>
              Ticket, dates, breach, and every claim behind it.
              <span className="hand">the record goes with it</span>
            </aside>
            <Ladder />
          </div>
        </div>
      </section>

      {/* ---- the false closure ---------------------------------- */}
      <section className="band closure-band">
        <div className="page">
          <SectionHead n="§ 5" kicker={c.closureKicker} title="The desk answers." note={c.closureNote} />

          <div className="closure-grid">
            <div className="closure-doc" data-beat>
              <Document
                kind="DISPOSAL MEMORANDUM"
                docRef={CONTRADICTION.desk.ref}
                authority={c.closureAuthority}
                tilt={-1.4}
                punched
                creased
                fields={[
                  { k: 'Ticket', v: CONTRADICTION.desk.ref },
                  { k: 'Disposal date', v: CONTRADICTION.desk.stamped },
                  { k: 'Remark', v: CONTRADICTION.desk.remark },
                  { k: 'Work order', v: '— none attached —', tone: 'terracotta' },
                  { k: 'Site visit', v: '— no record —', tone: 'terracotta' },
                ]}
                stamp={{
                  text: 'RESOLVED',
                  sub: c.closureStampSub,
                  date: CONTRADICTION.desk.stamped,
                  width: 300,
                  rotate: -7,
                }}
              />
            </div>

            <div className="closure-say" data-beat>
              <p className="meta">What the ticket now says</p>
              <p className="sub closure-quote">&ldquo;{CONTRADICTION.desk.remark}&rdquo;</p>
              <p className="sans dim">{c.closureSay[0]}</p>
              <p className="sans dim">{c.closureSay[1]}</p>
            </div>
          </div>
        </div>
      </section>

      {/* ---- the contradiction ---------------------------------- */}
      <section className="band" data-contradiction>
        <div className="page">
          <SectionHead n="§ 6" kicker={c.contraKicker} title="Except the street disagrees." note={`${CONTRADICTION.street.live_claims} live claims`} />

          <div className="plan-frame overflow-x">
            <div className="plan-scroll">
              <StreetPlan stage={planStage} id="case" />
            </div>
          </div>
          <p className="micro plan-hint">Drawing is wider than this screen — drag it sideways.</p>

          <div className="contra-grid">
            <ul className="contra-claims">
              {CLAIMS.map((c) => (
                <li key={c.id} data-entry>
                  <span className="mono contra-id">{c.id}</span>
                  <span className="mono contra-house">12/{String(c.house).padStart(2, '0')}</span>
                  <span className="contra-text">&ldquo;{c.text}&rdquo;</span>
                  <span className="mono contra-at">{c.at}</span>
                </li>
              ))}
            </ul>

            <aside className="corr" data-entry>
              <p className="label">Correlation · ambient pass</p>
              <dl className="corr-terms">
                {CORRELATION.components.map((c) => (
                  <div key={c.name} data-ran={c.ran ? 'yes' : 'no'}>
                    <dt className="mono">{c.name}</dt>
                    <dd className="mono">
                      {c.ran ? c.value.toFixed(2) : 'UNAVAILABLE'}
                      <span className="micro corr-note">{c.note}</span>
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="mono corr-score">
                score {CORRELATION.score.toFixed(2)} · τ {CORRELATION.tau.toFixed(2)} · CLUSTERED
              </p>
              <p className="micro corr-honest">
                The semantic term did not run. It is dropped and the score renormalised over
                the terms that did, because scoring a missing term as zero would sink a real
                cluster below the threshold and nothing would say why. A cluster that hides
                which terms ran is claiming agreement it never computed.
              </p>
              <p className="mono corr-decoy">
                12/{CORRELATION.decoy.house} · {CORRELATION.decoy.score.toFixed(2)} · not clustered
                <span className="micro corr-note">{CORRELATION.decoy.note}</span>
              </p>
            </aside>
          </div>

          <div className="voices">
            {VOICES.map((v) => (
              <figure key={v.house} className="voice" data-ran={v.decoy ? 'other' : 'same'} data-entry>
                <p className={`${v.script} voice-text`}>{v.text}</p>
                <figcaption>
                  <span className="sans dim">{v.gloss}</span>
                  <span className="micro">{v.house} · {v.tag}</span>
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      </section>

      {/* ---- the climax ----------------------------------------- */}
      <section className="climax" data-climax>
        <div className="climax-inner" data-climax-inner>
          <div className="page">
            <p className="climax-kicker micro">Finding</p>
            <p className="colossal climax-line">
              {c.climax[0]}
              <br />
              <em>{c.climax[1]}</em>
            </p>
            <p className="mono climax-verdict">{CONTRADICTION.verdict}</p>
          </div>
        </div>
      </section>

      {/* ---- where it stands ------------------------------------ */}
      <section className="band">
        <div className="page">
          <SectionHead n="§ 7" kicker="Current state" title="Where the file stands." note="Open · tier 2" />
          <div className="ledger">
            <aside className="margin marginalia">
              <b>Not closed</b>
              A case closes when the street agrees it is closed.
            </aside>
            <div className="prose">
              <p className="opener">{c.standsOpener}</p>
              <p>{c.standsNext}</p>
            </div>
          </div>

          <div className="standing">
            <Stamp
              text="DISPUTED"
              sub="PANCHAYAT · WARD 12"
              date={c.standsStampDate}
              colour="var(--terracotta)"
              width={300}
              rotate={-5}
              seed={19}
            />
            <div className="standing-next">
              <Link to="/street" className="action">
                Read the drawing
                <Icon name="arrowRight" size={15} />
              </Link>
              <Link to="/process" className="action">
                How the pursuit runs
                <Icon name="arrowRight" size={15} />
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
