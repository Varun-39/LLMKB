"""
Synthetic alert intake — demo stand-in for a real Splunk webhook alert action.

ponytail: this is a demo. There is no live Splunk/ITRS integration; alerts
are POSTed as JSON shaped like Splunk's webhook alert action payload
(sid/search_name/result), either hand-built or from data/sample_alerts/*.json.
Upgrade path: replace the /alert endpoint's request body with an actual
Splunk webhook receiver once real alert access is approved (see the deck's
"Event intake API" component) — SplunkAlert's shape already matches that
payload, so the swap is endpoint-only, no schema change.

Splunk webhook alert actions POST:
    {
      "sid": "...", "search_name": "...", "app": "...", "owner": "...",
      "results_link": "...",
      "result": { "_time": "...", "host": "...", "source": "...",
                  "sourcetype": "...", ...extracted fields... }
    }
"""

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


class SplunkAlert(BaseModel):
    """Top-level Splunk webhook alert action payload."""

    sid: str
    search_name: str
    app: str = "search"
    owner: str = "svc-monitoring"
    results_link: Optional[str] = None
    result: SplunkResult


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
    return query
