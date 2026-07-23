// State 2 — band: "none". Not an error: a correct, useful answer that the
// system found nothing it can stand behind. No action block, no confidence
// badge (Rule 1) — both are structurally absent from the card itself.
export default function NoMatch({ hasEvidence }) {
  return (
    <section className="rounded-xl border border-hairline bg-surface p-6 shadow-sm">
      <p className="text-lg font-semibold text-ink">No strong knowledge match found</p>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Nothing in the runbook or incident history cleared the bar for a grounded recommendation
        {hasEvidence ? ' — the related entries below are the closest matches found, shown for context, not as a suggestion.' : ', and no related entries were found either.'}
      </p>
      <p className="mt-3 text-sm leading-relaxed text-ink">
        Use <span className="font-semibold">Escalate</span> or <span className="font-semibold">KB Gap</span> in
        Your Decision below to hand this off or flag the missing knowledge.
      </p>
    </section>
  )
}
