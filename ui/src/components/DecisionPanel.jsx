import { useState } from 'react'
import { submitFeedback, ApiError } from '../api'

const DECISIONS = [
  { id: 'accept', label: 'Accept' },
  { id: 'edit', label: 'Edit' },
  { id: 'reject', label: 'Reject' },
  { id: 'escalate', label: 'Escalate' },
  { id: 'kb_gap', label: 'KB Gap' },
]
const COMMENT_REQUIRED = new Set(['reject', 'escalate', 'kb_gap'])
const PAST_TENSE = {
  accept: 'Accepted',
  edit: 'Edited',
  reject: 'Rejected',
  escalate: 'Escalated',
  kb_gap: 'Flagged as KB gap',
}

function timeAgo() {
  return 'just now'
}

export default function DecisionPanel({ card }) {
  const [actor, setActor] = useState('')
  const [selected, setSelected] = useState(null)
  const [comment, setComment] = useState('')
  const [editedAction, setEditedAction] = useState(card.recommended_action || '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [decided, setDecided] = useState(
    card.ops_decision ? { decision: card.ops_decision.decision, actor: card.ops_decision.actor } : null
  )

  if (decided) {
    return (
      <section className="rounded-xl border border-hairline bg-surface p-6 shadow-sm">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted mb-2">Your decision</h2>
        <p className="text-sm text-ink">
          <span className="font-semibold">{PAST_TENSE[decided.decision] || decided.decision}</span> by{' '}
          <span className="font-medium">{decided.actor}</span> · {timeAgo()}
        </p>
        <button
          type="button"
          onClick={() => {
            setDecided(null)
            setSelected(null)
            setComment('')
            setError(null)
          }}
          className="mt-3 text-xs font-medium text-navy hover:text-coral-deep transition-colors duration-150"
        >
          Record a different decision
        </button>
      </section>
    )
  }

  const needsComment = selected && COMMENT_REQUIRED.has(selected)
  const needsEdit = selected === 'edit'

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const result = await submitFeedback(card.correlation_id, {
        signature_id: card.signature_id,
        error_family: card.error_family,
        // recommended_runbook is Optional on the backend and not present on
        // RecommendationCard — omitted rather than guessed from evidence order.
        decision: selected,
        actor,
        comment: comment || undefined,
        edited_action: needsEdit ? editedAction : undefined,
      })
      setDecided({ decision: selected, actor })
      void result
    } catch (e) {
      setError(e instanceof ApiError ? e.detail || e.message : String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="rounded-xl border border-hairline bg-surface p-6 shadow-sm">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted mb-3">Your decision</h2>

      <label className="block text-xs font-medium text-muted mb-1">Your name / ID</label>
      <input
        type="text"
        value={actor}
        onChange={(e) => setActor(e.target.value)}
        placeholder="e.g. jane.ops"
        className="w-full rounded-lg border border-hairline bg-page px-3 py-2 text-sm text-ink mb-4 focus:outline-none focus:ring-2 focus:ring-coral/40"
      />

      <div className="flex flex-wrap gap-2">
        {DECISIONS.map((d) => (
          <button
            key={d.id}
            type="button"
            onClick={() => setSelected(d.id)}
            className={`rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors duration-150 ${
              selected === d.id
                ? 'bg-navy text-white'
                : 'bg-page text-ink border border-hairline hover:border-navy/40'
            }`}
          >
            {d.label}
          </button>
        ))}
      </div>

      {needsEdit && (
        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-muted mb-1">Original action</label>
            <div className="rounded-lg border border-hairline bg-page px-3 py-2 text-sm text-muted whitespace-pre-wrap max-h-48 overflow-y-auto">
              {card.recommended_action}
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-muted mb-1">Your edit</label>
            <textarea
              value={editedAction}
              onChange={(e) => setEditedAction(e.target.value)}
              rows={6}
              className="w-full rounded-lg border border-hairline bg-page px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-coral/40"
            />
          </div>
        </div>
      )}

      {needsComment && (
        <div className="mt-4">
          <label className="block text-xs font-medium text-muted mb-1">
            Comment <span className="text-danger">(required)</span>
          </label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={3}
            placeholder={selected === 'kb_gap' ? 'What knowledge is missing?' : 'Why?'}
            className="w-full rounded-lg border border-hairline bg-page px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-coral/40"
          />
        </div>
      )}

      {selected && (
        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            onClick={submit}
            disabled={submitting}
            className="rounded-lg bg-coral px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-coral-deep disabled:opacity-50"
          >
            {submitting ? 'Submitting…' : `Submit ${DECISIONS.find((d) => d.id === selected).label}`}
          </button>
          {error && <span className="text-sm font-medium text-danger">{error}</span>}
        </div>
      )}
    </section>
  )
}
