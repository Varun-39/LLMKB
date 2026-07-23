import { useState } from 'react'
import RichText from './RichText'

// Collapsed by default; State 5 (medium/low confidence) passes
// defaultExpanded so the caveat evidence is visible without an extra click.
export default function Evidence({ evidence, defaultExpanded = false }) {
  const [open, setOpen] = useState(defaultExpanded)

  return (
    <section className="rounded-xl border border-hairline bg-surface p-6 shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="text-sm font-semibold text-ink">
          Backed by {evidence.length} source{evidence.length === 1 ? '' : 's'}
        </span>
        <span className="text-xs text-muted">{open ? 'Hide ▴' : 'Show ▾'}</span>
      </button>

      {open && (
        <div className="mt-4 space-y-4 divide-y divide-hairline">
          {evidence.map((item, i) => (
            <div key={`${item.doc_id}-${i}`} className={i > 0 ? 'pt-4' : ''}>
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="font-mono text-xs font-semibold text-navy">{item.doc_id}</span>
                <span className="text-xs text-muted">{item.doc_type} · {item.section}</span>
              </div>
              {item.why_matched && (
                <p className="mt-1 text-xs italic text-muted">{item.why_matched}</p>
              )}
              <RichText text={item.snippet} className="mt-1.5 text-sm text-ink/90 [&_p]:text-sm [&_p]:my-1" />
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
