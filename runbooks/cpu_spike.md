# RUNBOOK: HighCPUUsage

## Diagnosis Checklist
1. Verify if `cpu_usage_percent` exceeded the 80% threshold.
2. Check if a CPU intensive task (e.g. background batch processing, heavy RAG calculations) is running.
3. Review if a recent Git commit introduced heavy loops.

## Remediation Rules
*   **Safe Actions**:
    *   `enable_rate_limiting`: Enable strict request throttling on intensive endpoints. Safe to execute automatically.
*   **Risky Actions**:
    *   `rollback_deploy`: Rollback to previous deployment if cpu spike aligns with a new release. Requires operator approval.
