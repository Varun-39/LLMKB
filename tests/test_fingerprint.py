"""
Self-check for src/fingerprint.py. Plain asserts, no framework — same
convention as tests/evaluate.py.

Run:
    python -m tests.test_fingerprint
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.fingerprint import compute_fingerprint, extract_root_frames, classify_error_family

JAVA_TRACE = """\
com.example.payment.PoolExhaustedException: timeout waiting for connection
\tat com.zaxxer.hikari.pool.HikariPool.getConnection(HikariPool.java:197)
\tat com.example.payment.dao.OrderDao.findById(OrderDao.java:42)
\tat com.example.payment.service.PaymentService.charge(PaymentService.java:88)
\tat org.springframework.aop.framework.ReflectiveMethodInvocation.proceed(ReflectiveMethodInvocation.java:198)
"""


def test_same_error_different_volatile_fields_collide():
    a = compute_fingerprint(
        raw_text="2026-04-24T14:52:03Z HikariPool-1 - Connection is not available, request timed out after 30000ms",
        service="payment-service",
        environment="prod",
    )
    b = compute_fingerprint(
        raw_text="2026-05-02T09:11:47Z HikariPool-1 - Connection is not available, request timed out after 30042ms",
        service="payment-service",
        environment="prod",
    )
    assert a.signature_id == b.signature_id, "same error family+service should collapse to one signature"
    assert a.error_family == "connection-pool-exhausted"


def test_same_message_different_service_does_not_collide():
    a = compute_fingerprint(raw_text="connection pool exhausted", service="payment-service")
    b = compute_fingerprint(raw_text="connection pool exhausted", service="auth-service")
    assert a.signature_id != b.signature_id, "same wording on different services must not collide"


def test_instance_suffix_is_stripped():
    a = compute_fingerprint(raw_text="disk full on app-02", service="payment-service")
    b = compute_fingerprint(raw_text="disk full on app-17", service="payment-service")
    assert a.normalized_message == b.normalized_message
    assert a.signature_id == b.signature_id


def test_unknown_family_never_guesses():
    fp = compute_fingerprint(raw_text="completely novel error nobody has seen before", service="frontend")
    assert fp.error_family == "unknown"


def test_root_frame_skips_framework_and_finds_application_code():
    frames = extract_root_frames(JAVA_TRACE)
    assert frames, "expected at least one in-app frame"
    assert not any("com.zaxxer.hikari" in f for f in frames), "framework frame leaked into root_frames"
    assert any("com.example.payment.dao.OrderDao" in f for f in frames)


def test_root_frame_wins_as_anchor_over_message_text():
    fp = compute_fingerprint(
        raw_text="PoolExhaustedException: timeout waiting for connection",
        service="payment-service",
        stack_trace=JAVA_TRACE,
    )
    assert fp.root_frame is not None
    assert "OrderDao" in fp.signature


def test_classify_matches_real_incident_wording():
    assert classify_error_family(
        "FATAL: remaining connection slots are reserved for non-replication superuser connections"
    ) == "connection-pool-exhausted"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)} fingerprint checks passed.")
