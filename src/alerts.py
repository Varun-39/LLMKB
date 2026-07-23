"""
Synthetic alert intake — demo stand-in for a real Splunk webhook alert action,
with an optional ITRS health context alongside it.

ponytail: this is a demo. There is no live Splunk/ITRS integration; alerts
are POSTed as JSON shaped like Splunk's webhook alert action payload
(sid/search_name/result) plus an optional `itrs` block (ITRSContext, below),
either hand-built or from data/sample_alerts/*.json.
Upgrade path: replace the /alert endpoint's request body with an actual
Splunk webhook receiver, and add a real ITRS event/API pull merged into the
same payload, once real alert access is approved (see the deck's "Event
intake API" component) — SplunkAlert's shape already matches that combined
payload, so the swap is endpoint-only, no schema change.

Splunk webhook alert actions POST:
    {
      "sid": "...", "search_name": "...", "app": "...", "owner": "...",
      "results_link": "...",
      "result": { "_time": "...", "host": "...", "source": "...",
                  "sourcetype": "...", ...extracted fields... }
    }
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from src.fingerprint import Fingerprint


class SplunkResult(BaseModel):
    """The `result` object — one matched event, with fields a saved search
    would extract (host, component lookup, error field extraction)."""

    time: str = Field(alias="_time")
    host: str
    source: str
    sourcetype: str = "jee:app:log"
    component: str
    service: str
    environment: str = "prod"
    severity: str = "ERROR"
    message: str
    stack_trace: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class ITRSContext(BaseModel):
    """
    ITRS Geneos-style health snapshot for the host/dependency around the alert's
    time window (process state, host health, dependency latency) — the deck's
    "Context-aware: combine ... host, component, environment and ITRS health
    state" design principle, and the "ITRS integration" event source in the
    solution overview.

    ponytail: schema-only for this demo phase, same simplification as
    SplunkAlert itself — there is no live ITRS Geneos API/webhook client here.
    See project memory: alert input stays synthetic JSON (hand-built or from
    data/sample_alerts/*.json) until real Splunk/ITRS access is approved.
    Upgrade path: an ITRS event intake feeds this same shape once available;
    no schema change needed, only a new ingestion source.
    """

    process_status: str = "UP"           # UP | DEGRADED | DOWN
    host_health: str = "OK"              # OK | WARNING | CRITICAL
    dependency: Optional[str] = None     # e.g. "database", "message-queue"
    dependency_status: str = "OK"        # OK | DEGRADED | CRITICAL
    latency_ms: Optional[float] = None
    notes: Optional[str] = None          # e.g. "DB listener instability observed"

    def summary(self) -> Optional[str]:
        """Short clause for the retrieval query text / card context, e.g.
        'ITRS shows database degraded (latency 850ms): DB listener instability
        observed.' Returns None when nothing noteworthy is reported (both
        process and dependency healthy), so a fully-healthy ITRS block never
        pads the query with boilerplate."""
        bits = []
        if self.process_status != "UP" or self.host_health != "OK":
            bits.append(f"process {self.process_status.lower()}, host {self.host_health.lower()}")
        if self.dependency and self.dependency_status != "OK":
            lat = f" (latency {self.latency_ms:.0f}ms)" if self.latency_ms is not None else ""
            bits.append(f"{self.dependency} {self.dependency_status.lower()}{lat}")
        if not bits:
            return None
        clause = "ITRS shows " + "; ".join(bits) + "."
        if self.notes:
            clause += f" {self.notes}"
        return clause


class SplunkAlert(BaseModel):
    """Top-level Splunk webhook alert action payload, plus an optional ITRS
    health context merged in at the same "event intake" point the deck
    describes (Splunk shows the symptom, ITRS shows surrounding health)."""

    sid: str
    search_name: str
    app: str = "search"
    owner: str = "svc-monitoring"
    results_link: Optional[str] = None
    result: SplunkResult
    itrs: Optional[ITRSContext] = None


def alert_to_query(alert: SplunkAlert, fingerprint: "Optional[Fingerprint]" = None) -> str:
    """
    Turn an alert into the search query the retrieval pipeline sees.

    Without a fingerprint, this is just a paraphrased sentence — fine for
    dense/semantic recall but it discards the stack trace entirely, so BM25's
    exact-match signal only ever sees the top-level log message.

    With a fingerprint, append its error_family (a curated slug, e.g.
    "connection-pool-exhausted") and root_frame (the exact application
    class/method from the stack trace, e.g. "ExportJobExecutor.runExport") as
    literal search terms. root_frame in particular is often the sharpest
    signal available: a generic top-level message ("Connection is not
    available") can match many incidents, but the exact class name usually
    only appears in the one incident/runbook that already diagnosed it.
    """
    r = alert.result
    query = (
        f"{r.component} on {r.host} ({r.environment}) is reporting: {r.message}. "
        f"What corrective action should be taken?"
    )
    if fingerprint is not None:
        extra = [fingerprint.error_family.replace("-", " ")]
        if fingerprint.root_frame:
            extra.append(fingerprint.root_frame)
        query += " (" + " | ".join(extra) + ")"
    if alert.itrs is not None:
        itrs_clause = alert.itrs.summary()
        if itrs_clause:
            query += f" {itrs_clause}"
    return query


@dataclass
class AlertContext:
    """
    Structured alert facts, carried alongside the rendered query string instead
    of being re-derived from it downstream.

    This generalizes the P0.1 fix (a scoring signal was reading `service` back
    out of alert_to_query()'s rendered sentence via substring matching, and
    collided with boilerplate wording — "...is reporting: ..." literally
    contains the word "reporting", matching reporting-service regardless of
    the actual alert's service). The rendered query string still exists and is
    still used for embedding + BM25 — but any signal that needs a structured
    alert fact (service, component, error_family, ...) reads it from here,
    never by re-parsing that sentence.
    """

    service: str
    component: str
    host: str
    environment: str
    severity: str
    signature_id: str
    error_family: str
    root_frame: Optional[str] = None
    itrs_summary: Optional[str] = None  # ITRSContext.summary(), None if no itrs block or nothing noteworthy


def build_alert_context(alert: SplunkAlert, fingerprint: "Fingerprint") -> AlertContext:
    """Compose the structured context from an alert + its computed fingerprint."""
    r = alert.result
    return AlertContext(
        service=r.service.lower(),
        component=r.component,
        host=r.host,
        environment=r.environment,
        severity=r.severity,
        signature_id=fingerprint.signature_id,
        error_family=fingerprint.error_family,
        root_frame=fingerprint.root_frame,
        itrs_summary=alert.itrs.summary() if alert.itrs is not None else None,
    )
