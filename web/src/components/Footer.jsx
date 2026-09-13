import { Link } from 'react-router-dom'
import { MASTHEAD } from '../data/indic.js'

const COLOPHON = [
  'Deployed on Amazon Bedrock AgentCore Runtime · ap-south-2 · READY',
  'DynamoDB + EventBridge + Lambda · temporal path verified 13 Sep',
  '522 tests · both storage backends · ruff clean',
  'Institutions are calibrated simulators. Households are synthetic.',
]

const ELSEWHERE = [
  { to: '/case', label: 'The case' },
  { to: '/street', label: 'The street' },
  { to: '/process', label: 'The process' },
  { to: '/about', label: 'Boundaries' },
]

export default function Footer() {
  return (
    <footer className="colophon">
      <div className="page">
        <div className="colophon-top">
          <div className="colophon-mark">
            <span className="kn">{MASTHEAD.kn}</span>
            <span className="hi">{MASTHEAD.hi}</span>
            <span>{MASTHEAD.en}</span>
          </div>
          <nav className="colophon-nav" aria-label="Footer">
            {ELSEWHERE.map((e) => (
              <Link key={e.to} to={e.to} className="colophon-link">
                {e.label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="colophon-rule" />

        <dl className="colophon-grid">
          {COLOPHON.map((line, i) => (
            <div key={line} className="colophon-row">
              <dt className="mono colophon-n">{String(i + 1).padStart(2, '0')}</dt>
              <dd className="mono colophon-line">{line}</dd>
            </div>
          ))}
        </dl>

        <p className="colophon-close">
          We do not fix pipes.
          <br />
          We pursue resolution.
        </p>

        <p className="micro colophon-foot">
          Good Neighbor track · Ward 12, Doddanekkundi, Bengaluru · MMXXVI
        </p>
      </div>
    </footer>
  )
}
