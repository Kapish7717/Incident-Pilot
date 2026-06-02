# RUNBOOK: HighDBConnectionFailures

## Diagnosis Checklist
1. Inspect the live Prometheus registry for `db_connection_failures_total`.
2. Check if a recent code deployment or database pool migration occurred in the 15-minute pre-alert window.
3. Verify if system resources are under healthy load.

## Remediation Rules
*   **Safe Actions**:
    *   `clear_cache`: Flushes request caching layer to reduce parallel connections to the database. Safe to run automatically.
*   **Risky Actions**:
    *   `rollback_deploy`: If a recent deployment adjusted database connections pool improperly, rollback to the previous stable release commit SHA. Requires operator approval.
