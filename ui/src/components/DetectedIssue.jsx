import { useState } from 'react'

export default function DetectedIssue({ detectedIssue }) {
  const [expanded, setExpanded] = useState(false)
  const { error, component, host, environment, raw_message, itrs_context } = detectedIssue

  return (
    <section className="rounded-xl border border-hairline bg-surface p-6 shadow-sm">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted mb-2">Detected issue</h2>
      <p className="text-xl font-semibold text-ink leading-snug">{error.replace(/-/g, ' ')}</p>
      <p className="mt-1.5 text-sm text-muted">
        <span className="font-medium text-ink">{component}</span> on {host} · {environment}
      </p>
      {itrs_context && (
        <p className="mt-1.5 text-sm text-muted">
          <span className="font-medium text-ink">ITRS:</span> {itrs_context}
        </p>
      )}

      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="mt-3 text-xs font-medium text-navy hover:text-coral-deep transition-colors duration-150"
      >
        {expanded ? 'Hide raw log message ▴' : 'Show raw log message ▾'}
      </button>
      {expanded && (
        <pre className="mt-2 overflow-x-auto rounded-lg bg-navy-deep p-4 text-[13px] leading-relaxed font-mono text-slate-100 whitespace-pre-wrap">
          {raw_message}
        </pre>
      )}
    </section>
  )
}
