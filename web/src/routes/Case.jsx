import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Document from '../components/Document.jsx'
import StreetPlan from '../components/StreetPlan.jsx'
import LegalClock from '../components/LegalClock.jsx'
import Ladder from '../components/Ladder.jsx'
import Icon from '../components/Icon.jsx'
import Stamp from '../components/Stamp.jsx'
import { SectionHead } from '../components/Bits.jsx'
import { CASE, FILING, TIMELINE, CLAIMS, CORRELATION, CONTRADICTION } from '../data/case.js'
import { REPORT, FORM, VOICES } from '../data/indic.js'
import { NOT_THESE } from '../data/authorities.js'
import { useGsap, gsap, ScrollTrigger } from '../lib/motion.js'

export default function Case() {
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
          <p className="meta">In the matter of a supply interruption · Ward {CASE.ward}</p>
          <h1 className="display case-title">
            Lakshmi&rsquo;s tap,
            <br />
            and the eleven weeks
            <br />
            <em>nobody was counting.</em>
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
            <span className="mono chapter-day">06</span>
            <span className="mono chapter-month">SEP</span>
            <span className="micro chapter-time">05:40</span>
          </div>

          <div className="chapter-body">
            <h2 className="display chapter-head">The tank is empty.</h2>
            <p className="lead">
              Third morning. The motor runs and pulls nothing. She checks the sump, the
              valve, the neighbour&rsquo;s line. Then she says it out loud, in the language
              she says everything else in.
            </p>

            <blockquote className="quote">
              <p className="kn quote-kn">{REPORT.kn}</p>
              <p className="sans dim quote-gloss">{REPORT.gloss}</p>
              <footer className="micro">{REPORT.by}</footer>
            </blockquote>

            <p className="sans dim chapter-note">
              This is a household position. It stays inside the household — her name, her
              door number, what else is going on in that house. Only a claim crosses out of
              it, and only once she has agreed to send one.
            </p>
          </div>
        </div>
      </section>

      {/* ---- jurisdiction --------------------------------------- */}
      <section className="band band-sunk">
        <div className="page">
          <SectionHead n="§ 1" kicker="08 SEP · 11:02" title="Whose duty is this?" note="Looked up. Never generated." />

          <div className="ledger">
            <aside className="margin marginalia">
              <b>Rule 3</b>
              A hallucinated authority reproduces the exact failure this exists to catch.
              <span className="hand">cite or return nothing</span>
            </aside>

            <div className="jur">
              <div className="jur-hit" data-entry>
                <span className="micro">Correct body</span>
                <h3 className="sub">BWSSB — Sub-Division Office, Mahadevapura</h3>
                <p className="mono jur-cite">{FILING.rule}</p>
                <p className="mono jur-cite dim">Window: {FILING.window_days} working days from receipt</p>
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
          <SectionHead n="§ 2" kicker="10 SEP · 09:11" title="Her words become a filing." note="Form GR-1" />

          <div className="transform">
            <div className="transform-a" data-entry>
              <Document kind="HOUSEHOLD POSITION · HELD" docRef="HH-12-0012" tilt={-0.6} creased>
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
                  { k: FORM.fields[0].en, v: 'Lakshmi (applicant)' },
                  { k: FORM.fields[1].en, v: `${CASE.household.door}, ${CASE.street}, ${FORM.ward.en}` },
                  { k: 'Nature of grievance', v: 'Complete loss of supply at premises — distribution main' },
                  { k: 'Duration', v: 'Continuous since 04 SEP 2026 (06 days at filing)' },
                  { k: 'Instrument', v: FILING.rule },
                  { k: 'Relief sought', v: 'Site inspection, trace of feeder, restoration of supply' },
                ]}
              >
                <p>
                  The premises has had no supply for six days. Neighbouring properties on the
                  same distribution main report the same failure. A trace of the feeder
                  upstream of the isolation valve is requested.
                </p>
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
              <p className="meta">10 SEP · 09:11</p>
              <h2 className="display">Nothing is filed<br />until she signs it.</h2>
              <p className="lead">
                The draft is read back to her in Kannada, in full, including the sentence that
                names her street. She can change it, hold it, or drop it. The liability for a
                filing against a public body lands on the household, so the household decides.
              </p>
              <p className="sans dim">
                A withdrawn household is not spoken for afterwards. Its claim leaves the
                cluster, and anything already filed carries a correction.
              </p>
            </div>

            <div className="sign-doc" data-beat>
              <Document
                kind="DECLARATION"
                docRef="SIG-0912-A"
                authority="Read back in Kannada before signature"
                tilt={-1.1}
                signature={{ name: 'ಲಕ್ಷ್ಮಿ', at: '10 SEP 2026 · 09:11 IST' }}
                annotation="read to me in full — I agree to send it"
                fields={[
                  { k: 'Applicant', v: 'Lakshmi · 12/12' },
                  { k: 'Consent', v: 'Given, by name, before lodgement' },
                  { k: 'Scope', v: 'Supply fault only. No income, health or arrears data.' },
                ]}
              />
            </div>
          </div>
        </div>
      </section>

      {/* ---- the clock ------------------------------------------ */}
      <section className="band" data-clock-track>
        <div className="page">
          <SectionHead n="§ 3" kicker="10–13 SEP" title="The statutory clock." note="7 working days" />

          <div className="clock-grid">
            <div className="clock-pin">
              <LegalClock elapsed={elapsed} />
              <div className="clock-readout">
                <span className="micro">Elapsed</span>
                <span className="mono clock-readout-n" data-breach={elapsed >= 7 ? 'yes' : 'no'}>
                  {String(elapsed).padStart(2, '0')} / 07
                </span>
                <span className="micro">
                  {elapsed >= 7 ? 'window expired · fault live' : 'window open · no site visit recorded'}
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
            <span className="mono chapter-day">13</span>
            <span className="mono chapter-month">SEP</span>
            <span className="micro chapter-time">17:00</span>
          </div>
          <div>
            <h2 className="display ink-terracotta">Day 7 of 7.<br />Nobody came.</h2>
            <p className="lead">
              The window expires with the fault live. This is the moment the clock earns its
              keep: no reply arrived, so nothing prompted anyone. The wake fires anyway,
              reads the case, finds it still tracking, and marks the breach on the record.
            </p>
            <p className="mono breach-line">SLA-BREACH · 13 SEP 2026 17:00 IST · tier 1 · BWSSB-100001</p>
          </div>
        </div>
      </section>

      {/* ---- escalation ----------------------------------------- */}
      <section className="band band-sunk">
        <div className="page">
          <SectionHead n="§ 4" kicker="13 SEP · 17:00" title="The case climbs." note="Tier 1 → Tier 2" />
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
          <SectionHead n="§ 5" kicker="13 SEP · 09:15" title="The desk answers." note="Eight hours before the deadline" />

          <div className="closure-grid">
            <div className="closure-doc" data-beat>
              <Document
                kind="DISPOSAL MEMORANDUM"
                docRef={CONTRADICTION.desk.ref}
                authority="BWSSB Sub-Division Office, Mahadevapura"
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
                  sub: 'BWSSB · MAHADEVAPURA',
                  date: '13 SEP 2026',
                  width: 300,
                  rotate: -7,
                }}
              />
            </div>

            <div className="closure-say" data-beat>
              <p className="meta">What the ticket now says</p>
              <p className="sub closure-quote">&ldquo;{CONTRADICTION.desk.remark}&rdquo;</p>
              <p className="sans dim">
                In the grievance portal this case is finished. It leaves the pending queue, it
                stops counting against anyone&rsquo;s numbers, and it will appear in a
                quarterly figure as a complaint attended within the statutory window.
              </p>
              <p className="sans dim">
                A household reading that page has no way to argue with it. It knows its own
                tap is dry, and one dry tap against an official closure is a story about a
                faulty motor.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ---- the contradiction ---------------------------------- */}
      <section className="band" data-contradiction>
        <div className="page">
          <SectionHead n="§ 6" kicker="13 SEP · 17:04" title="Except the street disagrees." note="3 live claims" />

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
              <figure key={v.house} className="voice" data-ran={v.house === '12/11' ? 'other' : 'same'} data-entry>
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
              You know your own tap.
              <br />
              <em>You do not know your neighbours&rsquo;.</em>
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
              <p className="opener">
                The closure is recorded, and so is the contradiction. Both sit in the file,
                and the file went up a tier rather than out of the system. The next window is
                fifteen days, and it is already being counted.
              </p>
              <p>
                What changed is not that a pipe was mended. It is that a stamp is no longer
                the last word on it.
              </p>
            </div>
          </div>

          <div className="standing">
            <Stamp
              text="DISPUTED"
              sub="PANCHAYAT · WARD 12"
              date="13 SEP 2026"
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
