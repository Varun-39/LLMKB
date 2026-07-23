// Hand-built mock RecommendationCard objects for State 5 (medium/low
// confidence). On the current corpus these bands almost never fire live —
// outcomes are nearly all "resolved", so scores land at 1.0 or below the
// floor — so this state is verified against these mocks, not live data.
// Shape matches src/card.py's RecommendationCard exactly.

const base = {
  correlation_id: 'mock-correlation-id',
  signature_id: 'mock-signature-id',
  error_family: 'redis-maxmemory-eviction',
  generated_at: new Date().toISOString(),
  model_version: null,
  detected_issue: {
    error: 'redis-maxmemory-eviction',
    component: 'CacheService',
    host: 'redis-03',
    environment: 'prod',
    raw_message: 'OOM command not allowed when used memory > maxmemory. Evicting keys under allkeys-lru policy.',
  },
  evidence: [
    {
      doc_id: 'RB-013',
      doc_type: 'runbook',
      section: 'Mitigation',
      snippet:
        '### Option A: Temporary relief — raise maxmemory\n\n```bash\nredis-cli CONFIG SET maxmemory 6gb\nredis-cli INFO memory | grep used_memory_human\n```\n\nBuys time; does not fix the underlying growth.',
      why_matched: 'error_family match (redis-maxmemory) + component overlap (CacheService)',
      signal_scores: { bm25: 0.61, dense: 0.58, error_family: 0.7 },
    },
    {
      doc_id: 'INC-039-redis-maxmemory-eviction-storm',
      doc_type: 'incident',
      section: 'Resolution',
      snippet: 'Raised maxmemory as a stopgap, then identified an unbounded key growth in the session cache and added TTLs.',
      why_matched: 'same error_family, same environment (prod)',
      signal_scores: { bm25: 0.44, dense: 0.51, error_family: 0.7 },
    },
  ],
  risk: { level: 'medium', note: null },
  do_not_do: 'Do not disable eviction entirely (maxmemory-policy noeviction) — this converts evictions into write errors instead.',
  escalate_if: 'Memory pressure returns within 30 minutes of raising maxmemory, or eviction rate does not drop.',
  ops_decision: null,
}

export const MOCK_MEDIUM = {
  ...base,
  correlation_id: 'mock-medium-' + base.correlation_id,
  recommended_action: base.evidence[0].snippet,
  confidence: {
    band: 'medium',
    score: 0.58,
    prior_success_n: 3,
    prior_total_n: 5,
    cohort_size: 5,
    excluded_unknown_n: 2,
  },
}

export const MOCK_LOW = {
  ...base,
  correlation_id: 'mock-low-' + base.correlation_id,
  recommended_action: base.evidence[0].snippet,
  confidence: {
    band: 'low',
    score: 0.31,
    prior_success_n: 1,
    prior_total_n: 4,
    cohort_size: 4,
    excluded_unknown_n: 3,
  },
}
