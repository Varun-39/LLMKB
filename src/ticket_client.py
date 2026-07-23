"""
TicketClient — interface for the Jira write-back the deck names (slide 7:
comments, KB-gap signals, draft KB updates). Per the standing project
decision: no live Jira integration this phase. NoopTicketClient logs every
call (structured log, not print) and returns a Jira-shaped response, so
nothing downstream needs to know it's talking to a stub — swapping in a real
client later is a one-class change, not a rewire.

config/jira.yaml's `mode` selects the implementation. 'noop' is the only
value implemented this session.
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import yaml

logger = logging.getLogger("llmkb2.ticket_client")

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "jira.yaml"

# create_kb_gap() routes into this file rather than a new review-file format.
# NOTE: the P1 enrichment pass's propose step (error_family/resolution_runbook/
# resolution_outcome proposals) was an ad-hoc script writing to a scratchpad
# JSON file — there was no persisted, importable "review file mechanism" in
# the repo to literally reuse. This is the first time that propose/approve/
# apply shape becomes real, checked-in infrastructure. The shape mirrors that
# script's output (a flat JSON array of proposal objects with a status field
# a human flips from "pending"), so a reviewer already familiar with the P1
# pass recognizes it immediately, but it's honest to note this is new code,
# not a reused module.
_REVIEW_QUEUE_PATH = Path(__file__).resolve().parent.parent / "review" / "kb_gap_proposals.json"


def load_jira_config() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {"mode": "noop"}


class TicketClient(Protocol):
    def add_comment(self, ticket_id: str, text: str) -> dict: ...
    def create_kb_gap(self, details: dict) -> dict: ...
    def create_kb_update_draft(self, content: str) -> dict: ...


def _append_to_review_queue(entry: dict) -> None:
    """R5: kb_gap signals accumulate here for human propose/approve/apply
    review — nothing here ever writes to wiki/ directly or auto-applies."""
    import json

    _REVIEW_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    queue = []
    if _REVIEW_QUEUE_PATH.exists():
        with open(_REVIEW_QUEUE_PATH, "r", encoding="utf-8") as f:
            queue = json.load(f)
    queue.append(entry)
    with open(_REVIEW_QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)


class NoopTicketClient(TicketClient):
    """Log-only stub. No network call, no file write except the kb_gap review
    queue (which is a review artifact for humans, not a ticket)."""

    def add_comment(self, ticket_id: str, text: str) -> dict:
        response = {
            "issue_key": f"MOCK-{uuid.uuid4().hex[:6]}",
            "created": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(
            "NoopTicketClient.add_comment ticket_id=%s text=%r -> %s",
            ticket_id, text, response,
        )
        return response

    def create_kb_gap(self, details: dict) -> dict:
        response = {
            "issue_key": f"MOCK-{uuid.uuid4().hex[:6]}",
            "created": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("NoopTicketClient.create_kb_gap details=%r -> %s", details, response)
        _append_to_review_queue({
            "proposed_at": response["created"],
            "mock_issue_key": response["issue_key"],
            "details": details,
            "status": "pending",
        })
        return response

    def create_kb_update_draft(self, content: str) -> dict:
        response = {
            "issue_key": f"MOCK-{uuid.uuid4().hex[:6]}",
            "created": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("NoopTicketClient.create_kb_update_draft content=%r -> %s", content, response)
        return response


_CLIENTS = {"noop": NoopTicketClient}


def get_ticket_client() -> TicketClient:
    mode = load_jira_config().get("mode", "noop")
    client_cls = _CLIENTS.get(mode)
    if client_cls is None:
        raise ValueError(f"jira.yaml mode='{mode}' has no implementation (only 'noop' exists this session)")
    return client_cls()
