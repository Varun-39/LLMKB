"""
RecommendationCard assembly (P4/E2, E3) — turns retrieved+scored evidence into
a RecommendationCard. Everything on the card except phrasing (F1/F2, LLM-optional)
comes directly from retrieved content or structured cohort data:

  - recommended_action : raw text of the top-ranked evidence item whose section
                         is action-oriented (resolution/mitigation/fix/triage) —
                         this item is always part of card.evidence (D4/R2).
  - risk               : the recommended runbook's own risk_level frontmatter.
  - do_not_do          : the recommended runbook's own Scope/Notes section text.
  - escalate_if        : the recommended runbook's own Escalation section text.

None of this requires an LLM call (E3) — build_recommendation_card() with
generation disabled produces a complete, correct card from retrieval alone.
"""

import re
from pathlib import Path
from typing import Optional

import yaml

from src.alerts import AlertContext, SplunkAlert
from src.card import Confidence, DetectedIssue, Evidence, RecommendationCard, Risk
from src.confidence import compute_confidence
from src.fingerprint import Fingerprint
from src.query import ACTION_SECTIONS, retrieve_only

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "card.yaml"
_CARD_PROMPT_PATH = Path(__file__).resolve().parent.parent / "config" / "prompts" / "card_prompt.yaml"


def load_card_config() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    # ponytail: minimal fallback if config file is missing
    return {
        "fields": {"show_do_not_do": True, "show_escalate_if": True, "show_risk": True, "max_evidence_items": 8},
        "risk_defaults": {"unknown_label": "unknown"},
        "generation": {"enabled": True, "model_version_tag": "llama3.1"},
    }


def load_card_prompt_config() -> dict:
    if _CARD_PROMPT_PATH.exists():
        with open(_CARD_PROMPT_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    # ponytail: minimal fallback if config file is missing
    return {
        "template": "Rephrase this SRE action for clarity, do not add anything: {action_text}",
        "refusal_marker": "REFUSE:",
    }


CONFIG = load_card_config()
CARD_PROMPT_CONFIG = load_card_prompt_config()
CARD_PROMPT_TEMPLATE = CARD_PROMPT_CONFIG["template"]
REFUSAL_MARKER = CARD_PROMPT_CONFIG["refusal_marker"]
MAX_EVIDENCE_ITEMS = CONFIG["fields"]["max_evidence_items"]
SHOW_DO_NOT_DO = CONFIG["fields"]["show_do_not_do"]
SHOW_ESCALATE_IF = CONFIG["fields"]["show_escalate_if"]
SHOW_RISK = CONFIG["fields"]["show_risk"]
UNKNOWN_RISK_LABEL = CONFIG["risk_defaults"]["unknown_label"]
GENERATION_ENABLED_DEFAULT = CONFIG["generation"]["enabled"]
MODEL_VERSION_TAG = CONFIG["generation"]["model_version_tag"]


def _clean_chunk_body(text: str) -> str:
    """Strip the contextual-retrieval blurb + '## Header' line that
    SectionNodeParser prepends, leaving just the section's real content."""
    parts = text.split("\n\n", 2)
    if len(parts) == 3 and parts[1].strip().startswith("##"):
        return parts[2].strip()
    return text.strip()


def _get_runbook_section(runbook_id: str, section_name: str) -> Optional[str]:
    from src.retrieval import id_lookup
    for n in id_lookup(runbook_id, top_k=50):
        if n.node.metadata.get("section_name") == section_name:
            return _clean_chunk_body(n.node.get_content())
    return None


def _get_runbook_risk_level(runbook_id: str) -> Optional[str]:
    from src.retrieval import id_lookup
    nodes = id_lookup(runbook_id, top_k=1)
    if nodes:
        return nodes[0].node.metadata.get("risk_level")
    return None


def _extract_do_not_do(scope_text: Optional[str], notes_text: Optional[str]) -> Optional[str]:
    if scope_text:
        m = re.search(r"\|\s*Do NOT use when\s*\|\s*(.+?)\s*\|", scope_text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    if notes_text:
        m = re.search(r"-\s*\*\*(Never[^*]+)\*\*\s*([^\n]*)", notes_text, re.IGNORECASE)
        if m:
            return (m.group(1) + " " + m.group(2)).strip()
    return None


def _find_recommended_runbook(nodes) -> Optional[str]:
    """Walk the ranked evidence in order; the first node with a runbook
    association (its own id if it IS a runbook, or resolution_runbook if it's
    an incident) is the one being recommended."""
    for n in nodes:
        meta = n.node.metadata
        if meta.get("doc_type") == "runbook":
            return meta.get("id")
        if meta.get("doc_type") == "incident" and meta.get("resolution_runbook"):
            return meta.get("resolution_runbook")
    return None


def build_recommendation_card(
    alert: SplunkAlert,
    fingerprint: Fingerprint,
    alert_context: AlertContext,
    correlation_id: str,
) -> RecommendationCard:
    """
    Assemble a RecommendationCard for one alert. Unconditionally LLM-free —
    generation (F1/F2's optional phrasing pass) is a separate step the caller
    (src/server.py) applies afterward via apply_generation(), controlled by
    config/card.yaml's generation.enabled (E3).
    """
    from src.alerts import alert_to_query

    query_text = alert_to_query(alert, fingerprint=fingerprint)
    nodes = retrieve_only(
        query_text,
        top_k=MAX_EVIDENCE_ITEMS,
        service=alert.result.service,
        alert_context=alert_context,
    )

    evidence = [
        Evidence(
            doc_id=n.node.metadata.get("id", "?"),
            doc_type=n.node.metadata.get("doc_type", "?"),
            section=n.node.metadata.get("section_name", "?"),
            snippet=_clean_chunk_body(n.node.get_content())[:500],
            why_matched=n.node.metadata.get("why_matched", ""),
            signal_scores=(n.node.metadata.get("_score_explain") or {}).get("signals", {}),
        )
        for n in nodes
    ]

    detected_issue = DetectedIssue(
        error=fingerprint.error_family,
        component=alert.result.component,
        host=alert.result.host,
        environment=alert.result.environment,
        raw_message=alert.result.message,
    )

    recommended_runbook = _find_recommended_runbook(nodes)
    confidence_result = compute_confidence(alert_context.error_family, recommended_runbook)
    confidence = Confidence.from_result(confidence_result)

    if confidence.band == "none" or not evidence:
        return RecommendationCard(
            correlation_id=correlation_id,
            signature_id=fingerprint.signature_id,
            error_family=fingerprint.error_family,
            model_version=None,
            detected_issue=detected_issue,
            recommended_action=None,
            evidence=evidence,
            confidence=confidence,
            risk=Risk(level=UNKNOWN_RISK_LABEL),
            do_not_do=None,
            escalate_if=None,
        )

    # recommended_action: the top-ranked action-oriented evidence item's own
    # text — guaranteed to already be part of `evidence` (D4/R2).
    recommended_action = None
    for n in nodes:
        if n.node.metadata.get("section_name") in ACTION_SECTIONS:
            recommended_action = _clean_chunk_body(n.node.get_content())
            break

    risk_level = None
    do_not_do = None
    escalate_if = None
    if recommended_runbook:
        if SHOW_RISK:
            risk_level = _get_runbook_risk_level(recommended_runbook)
        if SHOW_DO_NOT_DO:
            scope_text = _get_runbook_section(recommended_runbook, "scope")
            notes_text = _get_runbook_section(recommended_runbook, "notes")
            do_not_do = _extract_do_not_do(scope_text, notes_text)
        if SHOW_ESCALATE_IF:
            escalate_if = _get_runbook_section(recommended_runbook, "escalation")

    return RecommendationCard(
        correlation_id=correlation_id,
        signature_id=fingerprint.signature_id,
        error_family=fingerprint.error_family,
        model_version=None,  # assembly never calls an LLM — only apply_generation() sets this,
                              # and only on an actual successful phrasing response (never claim a
                              # model touched the card unless one genuinely did)
        detected_issue=detected_issue,
        recommended_action=recommended_action,
        evidence=evidence,
        confidence=confidence,
        risk=Risk(level=risk_level or UNKNOWN_RISK_LABEL),
        do_not_do=do_not_do,
        escalate_if=escalate_if,
    )


def apply_generation(card: RecommendationCard) -> RecommendationCard:
    """
    Optional LLM phrasing pass (F1/F2) over an already-assembled card's
    recommended_action. Never called by build_recommendation_card() itself —
    assembly is unconditionally LLM-free (E2). Rewrites wording only; refuses
    (leaves the card's raw, already-grounded action untouched) rather than
    inventing content when asked to phrase nothing or when it can't comply
    without adding something not in the source.
    """
    if card.recommended_action is None:
        return card  # nothing to phrase

    from llama_index.core import Settings

    prompt = CARD_PROMPT_TEMPLATE.format(action_text=card.recommended_action)
    response = str(Settings.llm.complete(prompt)).strip()

    if response.startswith(REFUSAL_MARKER) or not response:
        return card

    return card.model_copy(update={
        "recommended_action": response,
        "model_version": MODEL_VERSION_TAG,
    })
