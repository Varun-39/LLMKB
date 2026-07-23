import DetectedIssue from './DetectedIssue'
import ActionConfidence from './ActionConfidence'
import NoMatch from './NoMatch'
import Evidence from './Evidence'
import Safety from './Safety'
import DecisionPanel from './DecisionPanel'

export default function Card({ card, mock = false }) {
  const isNoMatch = card.recommended_action === null
  const expandEvidenceByDefault = card.confidence.band === 'medium' || card.confidence.band === 'low'

  return (
    <div className="space-y-4">
      {mock && (
        <div className="rounded-lg border border-caution/40 bg-caution-tint px-4 py-2 text-xs font-medium text-caution">
          Mock card — verified against a hand-built object, not live retrieval (see report, State 5)
        </div>
      )}

      <DetectedIssue detectedIssue={card.detected_issue} />

      {isNoMatch ? (
        <NoMatch hasEvidence={card.evidence.length > 0} />
      ) : (
        <ActionConfidence card={card} />
      )}

      {card.evidence.length > 0 && (
        <Evidence evidence={card.evidence} defaultExpanded={expandEvidenceByDefault} />
      )}

      <Safety risk={card.risk} doNotDo={card.do_not_do} escalateIf={card.escalate_if} />

      <DecisionPanel card={card} />
    </div>
  )
}
