# RUNBOOK: HighMemoryUsage

## Diagnosis Checklist
1. Track `memory_usage_bytes` gauge values.
2. Verify if memory growth is monotonic (memory leak pattern).
3. Correlate with recent deployments (e.g. pool size changes, data caching layers).

## Remediation Rules
*   **Safe Actions**:
    *   `clear_cache`: Flushes application caches to free memory chunks. Safe to execute automatically.
*   **Risky Actions**:
    *   `restart_service`: Force-restarts the FastAPI container to release all heap memory. Requires manual Operator approval.
