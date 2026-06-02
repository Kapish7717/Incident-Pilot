# RUNBOOK: HighLatency

## Diagnosis Checklist
1. Analyze 95th percentile metrics `request_latency_seconds` bucket distributions.
2. Check if a high request load occurred concurrently.
3. Check for recent deployments in the 15-minute window.

## Remediation Rules
*   **Safe Actions**:
    *   `scale_up`: Provision an extra mock API server instance to handle and distribute high traffic. Safe to run automatically.
*   **Risky Actions**:
    *   `restart_service`: Restarts the API microservice container to clear threadlocks. Requires manual Operator approval.
