import os
import json
from langchain_groq import ChatGroq

def get_runbook_for_alert(alert_name: str) -> str:
    """Dynamically maps any incoming alert name to its corresponding SRE runbook file, falling back to generic_error.md."""
    mapping = {
        "HighDBConnectionFailures": "runbooks/db_failure.md",
        "HighLatency": "runbooks/latency_spike.md",
        "HighCPUUsage": "runbooks/cpu_spike.md",
        "HighMemoryUsage": "runbooks/memory_leak.md"
    }
    
    # Resolve the file path, fallback to generic_error.md
    file_path = mapping.get(alert_name, "runbooks/generic_error.md")
    print(f"[Dynamic Match] Mapping Alert '{alert_name}' to runbook: {file_path}")
    
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return f.read()
    return "# RUNBOOK NOT FOUND"

def analyze_incident_telemetry(alert_details: dict, metrics_snapshot: dict, system_metrics: dict) -> dict:
    """
    Invokes the SRE AI Agent (ChatGroq llama-3.3-70b-versatile) to perform
    root-cause analysis and generate a structured remediation action plan.
    
    Returns a dictionary matching the schema:
    {
      "root_cause_analysis": "...",
      "proposed_actions": [
         {"action_type": "...", "risk_level": "...", "status": "...", "details": "..."}
      ]
    }
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("[WARNING] GROQ_API_KEY is not set in environment variables.")
        return {
            "root_cause_analysis": "GROQ_API_KEY not configured. Automated AI Agentic analysis skipped.",
            "proposed_actions": []
        }
        
    # 1. Resolve runbook dynamically based on the alert name
    alert_name = alert_details.get("alert_name", "UnknownAlert")
    runbook_content = get_runbook_for_alert(alert_name)

    # 2. Formulate SRE Prompt
    prompt = f"""
You are an expert SRE (Site Reliability Engineer) AI Agent specializing in automated incident response.
Analyze the following production incident and generate a root-cause analysis and remediation plan.

=== 1. ALERT DETAILS ===
Alert Name: {alert_name}
Severity: {alert_details.get('severity', 'warning')}
Started At: {alert_details.get('starts_at', 'unknown')}

=== 2. TELEMETRY METRICS SNAPSHOT ===
{json.dumps(metrics_snapshot, indent=2)}

=== 3. SYSTEM STATS & DEPLOYMENTS SNAPSHOT ===
{json.dumps(system_metrics, indent=2)}

=== 4. RUNBOOK RULES (STANDARD OPERATING PROCEDURES) ===
{runbook_content}

---
CRITICAL REQUIREMENT:
You must perform a detailed root-cause analysis correlating the alert telemetry with the recent deployment changes, and then output a structured remediation plan.
Your response MUST be a single, valid JSON object ONLY. Do not include any conversational text, explanations outside the JSON, or markdown blocks. The JSON must exactly match the schema below:

{{
  "root_cause_analysis": "Clear explanation of what caused the alert based on the telemetry and recent deployments.",
  "proposed_actions": [
    {{
      "action_type": "The name of the action (MUST be selected from the approved actions in the runbook rules, e.g., 'clear_cache', 'rollback_deploy', 'scale_up', 'restart_service', or 'enable_rate_limiting')",
      "risk_level": "The risk of this action (MUST be 'safe' or 'risky')",
      "status": "The execution status (MUST be 'pending_execution' for safe actions, or 'pending_approval' for risky actions)",
      "details": "Explanation of why this action is being taken and what it is expected to accomplish."
    }}
  ]
}}
"""

    try:
        print(f"[Agentic AI] Initializing ChatGroq LLaMA-3 model for incident {alert_name}...")
        llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.0
        )
        
        print("[Agentic AI] Sending SRE Prompt to Groq API...")
        response = llm.invoke(prompt)
        
        raw_content = response.content.strip()
        
        # Clean potential markdown wrappers
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:]
        if raw_content.endswith("```"):
            raw_content = raw_content[:-3]
        raw_content = raw_content.strip()
        
        parsed_plan = json.loads(raw_content)
        print("[Agentic AI] Success! Structured Remediation Plan received and validated.")
        return parsed_plan
        
    except Exception as e:
        print(f"[Agentic AI] [ERROR] Failed to execute LLM analysis: {e}")
        return {
            "root_cause_analysis": f"AI Agent analysis failed with error: {str(e)}",
            "proposed_actions": []
        }
