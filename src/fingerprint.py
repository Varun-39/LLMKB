"""
Deterministic error fingerprinting: turn a raw alert/log line (and optional
JEE stack trace) into a stable signature for KB matching.

No LLM involved — fingerprinting must be reproducible and auditable, the
same rule that keeps retrieval scoring outside the model (config/scoring.yaml).
Rules live in config/fingerprint.yaml so they can be tuned without code changes.

Pipeline:
    raw alert text -> normalize_message()   (strip volatile fields)
                   -> extract_root_frame()  (first non-framework JEE frame, if a trace is given)
                   -> classify_error_family() (regex bucket, keyed to an RB-xxx runbook slug)
                   -> compute_fingerprint() -> Fingerprint (signature + signature_id)

A family of "unknown" means no rule matched — callers must surface that as
"no strong match found", never guess a family to force a KB hit.

Usage:
    from src.fingerprint import compute_fingerprint
    fp = compute_fingerprint(
        raw_text="HikariPool-1 - Connection is not available, request timed out after 30000ms",
        service="payment-service",
        environment="prod",
    )
    fp.signature_id  # stable 12-char hash, used as the KB match key
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "fingerprint.yaml"


def load_fingerprint_config() -> dict:
    """Load fingerprint rules from YAML. Falls back to a minimal built-in set if missing."""
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    # ponytail: minimal fallback if config file is missing
    return {
        "version": "fp-v1",
        "volatile_patterns": [{"name": "bare_number", "pattern": r"\b\d+\b", "replacement": "<n>"}],
        "framework_frame_prefixes": ["java.", "javax."],
        "error_families": [],
    }


CONFIG = load_fingerprint_config()
SIGNATURE_VERSION = CONFIG.get("version", "fp-v1")
_VOLATILE_PATTERNS = [
    (re.compile(p["pattern"], re.IGNORECASE), p["replacement"])
    for p in CONFIG.get("volatile_patterns", [])
]
_FRAMEWORK_PREFIXES = tuple(CONFIG.get("framework_frame_prefixes", []))
_ERROR_FAMILIES = [
    (f["family"], re.compile(f["pattern"], re.IGNORECASE))
    for f in CONFIG.get("error_families", [])
]

# Matches a Java stack frame line: "\tat com.foo.Bar.method(File.java:123)"
_STACK_FRAME_RE = re.compile(r"^\s*at\s+([\w.$]+)\.[\w<>$]+\(")


@dataclass
class Fingerprint:
    raw_text: str
    service: str
    environment: str
    error_family: str
    normalized_message: str
    root_frame: Optional[str]
    signature: str
    signature_id: str
    signature_version: str = SIGNATURE_VERSION


def normalize_message(text: str) -> str:
    """Strip volatile fields (timestamps, IDs, counts, instance numbers) so
    two occurrences of the same error collapse to the same string."""
    normalized = text.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    for pattern, replacement in _VOLATILE_PATTERNS:
        normalized = pattern.sub(replacement, normalized)
    return normalized.strip()


def extract_root_frame(stack_trace: str) -> Optional[str]:
    """Return the first stack frame NOT belonging to a known framework/stdlib
    package — the application code most likely responsible for the error.
    Returns None if no application frame is found (or no trace given)."""
    if not stack_trace:
        return None
    for line in stack_trace.splitlines():
        match = _STACK_FRAME_RE.match(line)
        if not match:
            continue
        class_name = match.group(1)
        if not class_name.startswith(_FRAMEWORK_PREFIXES):
            return line.strip()
    return None


def classify_error_family(text: str) -> str:
    """Bucket raw error text into a family keyed to an existing runbook slug.
    Returns 'unknown' if no rule matches — callers must treat 'unknown' as
    'no strong match', never guess a family."""
    text_lower = text.lower()
    for family, pattern in _ERROR_FAMILIES:
        if pattern.search(text_lower):
            return family
    return "unknown"


def compute_fingerprint(
    raw_text: str,
    service: str,
    environment: str = "prod",
    stack_trace: Optional[str] = None,
) -> Fingerprint:
    """Compose a deterministic signature from alert text + optional stack trace.

    Anchor priority: root_frame (strongest signal for a JEE exception) if
    present, else the normalized message. error_family and service narrow
    the match before the anchor is applied, so unrelated errors with similar
    wording on different services never collide.
    """
    normalized = normalize_message(raw_text)
    root_frame = extract_root_frame(stack_trace) if stack_trace else None
    family = classify_error_family(raw_text)

    anchor = root_frame if root_frame else normalized
    signature = f"{family}::{service.lower()}::{anchor}"
    signature_id = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:12]

    return Fingerprint(
        raw_text=raw_text,
        service=service.lower(),
        environment=environment.lower(),
        error_family=family,
        normalized_message=normalized,
        root_frame=root_frame,
        signature=signature,
        signature_id=signature_id,
    )
