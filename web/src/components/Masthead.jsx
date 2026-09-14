import { NavLink, Link, useLocation } from 'react-router-dom'
import { MASTHEAD } from '../data/indic.js'
import { PROBLEMS } from '../data/scenarios.js'
import { useScenario } from '../lib/scenario.jsx'

const ENTRIES = [
  { to: '/case', n: '01', label: 'Case', sub: null },
  { to: '/street', n: '02', label: 'Street', sub: 'Ward 12 layout' },
  { to: '/process', n: '03', label: 'Process', sub: 'Seven stages' },
  { to: '/about', n: '04', label: 'About', sub: 'Boundaries' },
]

/**
 * A case index, not a navbar. The bar carries the same four things a
 * file cover carries: whose file, which ward, what state, what is in it.
 */
export default function Masthead() {
  const { pathname } = useLocation()
  const { problem, scenario, setProblem } = useScenario()
  const { CASE } = scenario

  return (
    <header className="masthead">
      <div className="masthead-strip">
        <div className="page masthead-strip-in">
          <span className="micro">Ward {CASE.ward} · {CASE.ward_name} · Bengaluru</span>
          <span className="micro masthead-strip-mid">Register of pursued complaints</span>
          {/* Which worked example the story pages tell. A report from the
              home page sets it too, for the service the household picked. */}
          <span className="micro problem-switch" role="group" aria-label="Worked example">
            {PROBLEMS.map((p) => (
              <button
                key={p.key}
                type="button"
                className="problem-switch-opt"
                aria-pressed={problem === p.key}
                onClick={() => setProblem(p.key)}
              >
                {p.switchLabel}
              </button>
            ))}
          </span>
          <span className="micro">
            File {CASE.id} · <span className="ink-terracotta">{CASE.status}</span>
          </span>
        </div>
      </div>

      <div className="page masthead-bar">
        <Link to="/" className="wordmark" aria-label="Panchayat — home">
          <span className="kn wordmark-kn">{MASTHEAD.kn}</span>
          <span className="wordmark-en">{MASTHEAD.en}</span>
        </Link>

        <nav className="index" aria-label="Case index">
          {ENTRIES.map((e) => (
            <NavLink
              key={e.to}
              to={e.to}
              className={({ isActive }) => `index-entry${isActive ? ' is-current' : ''}`}
            >
              <span className="index-n mono">{e.n}</span>
              <span className="index-label">{e.label}</span>
              <span className="index-sub">{e.sub ?? CASE.id}</span>
            </NavLink>
          ))}
        </nav>
      </div>

      <div className={`masthead-seam${pathname === '/' ? ' is-home' : ''}`} />
    </header>
  )
}
