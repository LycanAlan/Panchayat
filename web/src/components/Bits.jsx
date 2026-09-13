/**
 * The small recurring furniture of the record: section headers that
 * read like filing headers, gutter annotations, and the two or three
 * text objects that appear on every page.
 */

export function SectionHead({ n, kicker, title, note }) {
  return (
    <div className="section-head">
      <div className="marginalia">
        {n && <b className="mono">{n}</b>}
        {kicker}
      </div>
      <div className="spread">
        <h2 className="head">{title}</h2>
        {note && <span className="meta section-head-note">{note}</span>}
      </div>
    </div>
  )
}

export function Margin({ children, note }) {
  return (
    <aside className="margin marginalia">
      {children}
      {note && <span className="hand">{note}</span>}
    </aside>
  )
}

export function Rule({ weight = 'hair' }) {
  return <hr className={weight === 'double' ? 'hr-double' : weight === 'full' ? 'hr' : 'hr-hair'} />
}

export function Ref({ children }) {
  return <span className="mono ref-token">{children}</span>
}

export function Status({ kind, children }) {
  return <span className={`status status-${kind}`}>{children}</span>
}

/** A pair of facing lists, set as two columns of a printed notice. */
export function Facing({ left, right }) {
  return (
    <div className="facing">
      <section className="facing-col">
        <h3 className="facing-head">{left.title}</h3>
        <ol className="facing-list">
          {left.items.map((t, i) => (
            <li key={t}>
              <span className="mono facing-n">{String(i + 1).padStart(2, '0')}</span>
              <span>{t}</span>
            </li>
          ))}
        </ol>
      </section>
      <div className="facing-spine" aria-hidden="true" />
      <section className="facing-col facing-col--neg">
        <h3 className="facing-head">{right.title}</h3>
        <ol className="facing-list">
          {right.items.map((t, i) => (
            <li key={t}>
              <span className="mono facing-n">{String(i + 1).padStart(2, '0')}</span>
              <span>{t}</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
