import RichText from './RichText'

const RISK_STYLE = {
  low: { tint: 'bg-success-tint', text: 'text-success', border: 'border-success/30' },
  medium: { tint: 'bg-caution-tint', text: 'text-caution', border: 'border-caution/30' },
  high: { tint: 'bg-danger-tint', text: 'text-danger', border: 'border-danger/30' },
  unknown: { tint: 'bg-neutral-tint', text: 'text-neutral', border: 'border-neutral/30' },
}

// Rule 6: a null do_not_do or escalate_if means that subsection is entirely
// absent — no "N/A", no empty box.
export default function Safety({ risk, doNotDo, escalateIf }) {
  const style = RISK_STYLE[risk.level] || RISK_STYLE.unknown

  return (
    <section className={`rounded-xl border-2 ${style.border} ${style.tint} p-6`}>
      <div className="flex items-center gap-2">
        <span className={`inline-block rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${style.text} bg-white/60`}>
          {risk.level} risk
        </span>
        {risk.note && <span className="text-sm text-ink/80">{risk.note}</span>}
      </div>

      {doNotDo && (
        <div className="mt-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-danger mb-1">Do not</h3>
          <RichText text={doNotDo} className="text-sm text-ink [&_p]:text-sm [&_p]:my-0" />
        </div>
      )}

      {escalateIf && (
        <div className="mt-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/70 mb-1">Escalate if</h3>
          <RichText text={escalateIf} className="text-sm text-ink [&_p]:text-sm [&_p]:my-0" />
        </div>
      )}
    </section>
  )
}
