import RichText from './RichText'

const BAND_STYLE = {
  high: { tint: 'bg-success-tint', text: 'text-success', label: 'High confidence' },
  medium: { tint: 'bg-caution-tint', text: 'text-caution', label: 'Medium confidence' },
  low: { tint: 'bg-caution-tint', text: 'text-caution', label: 'Low confidence' },
}

// Rule 1 is enforced by the caller (Card.jsx): this component only ever
// renders when recommended_action is non-null, so a confidence badge can
// never appear next to a null action.
export default function ActionConfidence({ card }) {
  const { recommended_action, confidence, model_version } = card
  const style = BAND_STYLE[confidence.band] || BAND_STYLE.low
  const isCautionBand = confidence.band === 'medium' || confidence.band === 'low'

  return (
    <section className="grid grid-cols-1 md:grid-cols-[1fr_260px] gap-4">
      <div
        className={`rounded-xl border bg-surface p-6 shadow-sm ${isCautionBand ? 'border-caution/40' : 'border-hairline'}`}
      >
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Recommended action</h2>
          {model_version && (
            <span className="text-[11px] text-muted italic">phrased by {model_version}</span>
          )}
        </div>
        {isCautionBand && (
          <p className="text-sm text-caution font-medium mb-2">
            Confidence is {confidence.band} — verify this fits before acting.
          </p>
        )}
        <RichText text={recommended_action} />
      </div>

      <div className="rounded-xl border border-hairline bg-surface p-5 shadow-sm h-fit">
        <span className={`inline-block rounded-full px-2.5 py-1 text-xs font-semibold ${style.tint} ${style.text}`}>
          {style.label}
        </span>

        <p className="mt-3 text-sm text-ink">
          <span className="font-semibold">{confidence.prior_success_n}</span> of{' '}
          <span className="font-semibold">{confidence.prior_total_n}</span> prior incidents resolved this way
        </p>
        <p className="mt-1 text-xs text-muted">Cohort size: {confidence.cohort_size}</p>
        {confidence.excluded_unknown_n > 0 && (
          <p className="mt-2 text-xs text-caution font-medium">
            {confidence.excluded_unknown_n} similar incident{confidence.excluded_unknown_n === 1 ? '' : 's'} had no recorded outcome
          </p>
        )}
      </div>
    </section>
  )
}
