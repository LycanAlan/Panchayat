import Stamp from './Stamp.jsx'
import Icon from './Icon.jsx'

/**
 * A municipal sheet. Header block, ruled field rows, a body set
 * between rules, a signature well, and — if the desk has been at it —
 * a stamp lying across the whole thing.
 *
 * `tilt` is in degrees and small. Paper is never quite square in a file.
 */
export default function Document({
  kind = 'FORM GR-1',
  docRef,
  authority,
  fields = [],
  children,
  signature,
  stamp,
  annotation,
  tilt = 0,
  punched = false,
  creased = false,
  className = '',
}) {
  return (
    <article
      className={`doc perf-bottom${punched ? ' punched' : ''}${creased ? ' creased' : ''} ${className}`}
      style={tilt ? { transform: `rotate(${tilt}deg)` } : undefined}
    >
      <span className="crop crop-tl" />
      <span className="crop crop-tr" />

      <header className="doc-head">
        <div>
          <div className="micro doc-kind">{kind}</div>
          {authority && <div className="doc-authority">{authority}</div>}
        </div>
        {docRef && (
          <div className="doc-ref">
            <span className="micro">Ref</span>
            <span className="mono doc-ref-no">{docRef}</span>
          </div>
        )}
      </header>

      <div className="doc-body">
        {fields.length > 0 && (
          <dl className="doc-fields">
            {fields.map((f) => (
              <div className="field" key={f.k}>
                <dt>{f.k}</dt>
                <dd className={f.tone ? `ink-${f.tone}` : undefined}>{f.v}</dd>
              </div>
            ))}
          </dl>
        )}

        {children && <div className="doc-content ruled">{children}</div>}

        {signature && (
          <div className="doc-sign">
            <div className="doc-sign-well">
              <span className="doc-sign-mark" aria-hidden="true">
                {signature.name}
              </span>
              <span className="doc-sign-rule" />
              <span className="micro">Signature of applicant · {signature.at}</span>
            </div>
            <Icon name="nib" size={26} className="doc-sign-nib" />
          </div>
        )}

        {annotation && <p className="hand doc-annotation">{annotation}</p>}
      </div>

      {stamp && (
        <div className="doc-stamp" style={stamp.position}>
          <Stamp {...stamp} />
        </div>
      )}
    </article>
  )
}
