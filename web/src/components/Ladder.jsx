import { useScenario } from '../lib/scenario.jsx'

/**
 * The escalation ladder. A vertical stile with a rung per authority,
 * read bottom-up the way a case actually climbs. Not cards: a case
 * file does not come in cards, it comes in rungs with a rail through
 * them, and each rung carries the instrument it stands on.
 */
export default function Ladder() {
  const { scenario } = useScenario()
  const rungs = [...scenario.LADDER].reverse()

  return (
    <ol className="ladder" aria-label="Escalation ladder">
      {rungs.map((r) => (
        <li key={r.tier} className="rung" data-state={r.state}>
          <div className="rung-rail" aria-hidden="true">
            <span className="rung-node" />
          </div>

          <div className="rung-tier mono">
            <span className="rung-tier-n">T{r.tier}</span>
            <span className="rung-tier-state">{r.state}</span>
          </div>

          <div className="rung-body">
            <h3 className="rung-body-head sub">{r.body}</h3>
            <p className="mono rung-office">{r.office}</p>
            <dl className="rung-meta">
              {r.window && (
                <div>
                  <dt className="micro">Window</dt>
                  <dd className="mono">{r.window}</dd>
                </div>
              )}
              <div>
                <dt className="micro">Instrument</dt>
                <dd className="mono">{r.citation}</dd>
              </div>
            </dl>
            {r.note && <p className="rung-note dim">{r.note}</p>}
          </div>
        </li>
      ))}
    </ol>
  )
}
