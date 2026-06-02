# RUNBOOK: GenericError

## Diagnosis Checklist
1. Review raw metrics registry for high error counts or abnormal spikes.
2. Cross-reference starts_at timestamp with system resource stats.
3. Check for any deployments or git commits in the 15-minute pre-alert window.

## Remediation Rules
*   **Safe Actions**:
    *   `clear_cache`: Safely refresh application caching layer. Safe to run automatically.
*   **Risky Actions**:
    *   `restart_service`: Restarts the FastAPI service to clear generic thread/port locks. Requires operator approval.
