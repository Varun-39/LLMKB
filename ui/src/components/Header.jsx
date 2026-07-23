const STATUS_STYLE = {
  ok: { dot: 'bg-success', label: 'Connected' },
  degraded: { dot: 'bg-caution', label: 'Degraded' },
  down: { dot: 'bg-danger', label: 'Unreachable' },
  checking: { dot: 'bg-white/40 animate-pulse', label: 'Checking…' },
}

export default function Header({ health }) {
  const s = STATUS_STYLE[health] || STATUS_STYLE.checking
  return (
    <header
      className="text-white"
      style={{ background: 'linear-gradient(115deg, var(--color-navy-deep), var(--color-navy) 55%, var(--color-navy-light))' }}
    >
      <div className="mx-auto max-w-[880px] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-coral" aria-hidden="true" />
          <span className="text-[15px] font-semibold tracking-wide">Optimum Solutions</span>
          <span className="mx-2 h-4 w-px bg-white/20" aria-hidden="true" />
          <span className="text-[15px] font-medium text-white/90">AI Runbook Assistant</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-white/80">
          <span className={`h-2 w-2 rounded-full ${s.dot}`} aria-hidden="true" />
          <span>{s.label}</span>
        </div>
      </div>
    </header>
  )
}
