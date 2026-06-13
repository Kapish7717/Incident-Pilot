from demo_app.database import SessionLocal
from demo_app.models import Incident, IncidentTimeline, RemediationAction
from demo_app.metrics import MEMORY_USAGE, CPU_USAGE
import json
import os
from datetime import datetime
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, START, END

# Define LangGraph State
class IncidentGraphState(TypedDict):
    incident_id: str
    alert_name: str
    severity: str
    starts_at: str
    metrics_snapshot: Dict[str, Any]
    system_metrics: Dict[str, Any]
    analysis_summary: str
    confidence_score: int
    missing_context_details: str
    proposed_actions: List[Dict[str, Any]]
    db_status: str

# ----------------------------------------------------
# 1. GRAPH NODES IMPLEMENTATION
# ----------------------------------------------------

def collect_context_node(state: IncidentGraphState) -> Dict[str, Any]:
    """Node: Retrieves latest collected telemetry context from the DB."""
    db = SessionLocal()
    try:
        incident = db.query(Incident).filter(Incident.id == state["incident_id"]).first()
        if not incident:
            raise ValueError(f"Incident {state['incident_id']} not found.")
        
        metrics_snap = json.loads(incident.metrics_snapshot) if incident.metrics_snapshot else {}
        sys_metrics = json.loads(incident.system_metrics) if incident.system_metrics else {}
        
        print(f"[Graph Node] Context Collection completed for incident: {incident.id}")
        return {
            "alert_name": incident.alert_name,
            "severity": incident.severity,
            "starts_at": incident.starts_at.isoformat() if incident.starts_at else "unknown",
            "metrics_snapshot": metrics_snap,
            "system_metrics": sys_metrics,
            "db_status": incident.status
        }
    finally:
        db.close()

def llm_analysis_node(state: IncidentGraphState) -> Dict[str, Any]:
    """Node: Runs LLM model to perform root-cause analysis and generate action plan."""
    from llm import analyze_incident_telemetry
    
    db = SessionLocal()
    try:
        incident = db.query(Incident).filter(Incident.id == state["incident_id"]).first()
        if incident:
            incident.status = "analyzing"
            db.commit()
            
        alert_details = {
            "alert_name": state["alert_name"],
            "severity": state["severity"],
            "starts_at": state["starts_at"]
        }
        
        print(f"[Graph Node] LLM Agent reasoning running for alert: '{state['alert_name']}'...")
        plan = analyze_incident_telemetry(alert_details, state["metrics_snapshot"], state["system_metrics"])
        
        analysis_summary = plan.get("root_cause_analysis", "")
        confidence = plan.get("confidence_score", 100)
        missing_details = plan.get("missing_context_details", "")
        proposed = plan.get("proposed_actions", [])
        
        if incident:
            incident.analysis_summary = analysis_summary
            db.add(IncidentTimeline(
                incident_id=incident.id,
                event_type="analysis_complete",
                description=f"AI Agentic analysis completed. Root cause: {analysis_summary[:100]}..."
            ))
            db.commit()
            
        return {
            "analysis_summary": analysis_summary,
            "confidence_score": confidence,
            "missing_context_details": missing_details,
            "proposed_actions": proposed,
            "db_status": "analyzing"
        }
    except Exception as e:
        print(f"[Graph Node] [ERROR] in llm_analysis_node: {e}")
        return {
            "analysis_summary": f"Agent reasoning failed: {e}",
            "confidence_score": 0,
            "missing_context_details": str(e),
            "proposed_actions": []
        }
    finally:
        db.close()

def manual_diagnosis_node(state: IncidentGraphState) -> Dict[str, Any]:
    """Node: Routes the incident to manual diagnostic queue due to low confidence/missing context."""
    db = SessionLocal()
    try:
        incident = db.query(Incident).filter(Incident.id == state["incident_id"]).first()
        if incident:
            incident.status = "needs_manual_diagnosis"
            db.add(IncidentTimeline(
                incident_id=incident.id,
                event_type="routed_to_diagnostic",
                description=(
                    f"Confidence: {state['confidence_score']}%. "
                    f"Missing context: {state['missing_context_details'] or 'No deployments found.'} "
                    f"Routed to SRE diagnostic queue."
                )
            ))
            db.commit()
            print(f"[Graph Node] Escalating: Incident {state['incident_id']} routed to SRE diagnostic queue.")
        return {"db_status": "needs_manual_diagnosis"}
    except Exception as e:
        db.rollback()
        print(f"[Graph Node] [ERROR] in manual_diagnosis_node: {e}")
        return {}
    finally:
        db.close()

def remediation_node(state: IncidentGraphState) -> Dict[str, Any]:
    """Node: Auto-executes safe remediation actions and stages risky actions for HITL approval."""
    db = SessionLocal()
    try:
        incident = db.query(Incident).filter(Incident.id == state["incident_id"]).first()
        if not incident:
            return {}
            
        incident.status = "analyzed"
        db.commit()
        
        proposed_actions = state["proposed_actions"]
        has_risky_actions = False
        
        for action in proposed_actions:
            action_type = action.get("action_type", "unknown")
            risk_level = action.get("risk_level", "safe")
            details = action.get("details", "")
            
            db_action = RemediationAction(
                incident_id=incident.id,
                action_type=action_type,
                risk_level=risk_level,
                details=details
            )
            
            if risk_level == "safe":
                # Executing Safe Action
                db_action.status = "executing"
                db.add(db_action)
                db.commit()
                
                db.add(IncidentTimeline(
                    incident_id=incident.id,
                    event_type="action_proposed",
                    description=f"Proposed safe action '{action_type}': {details}"
                ))
                db.commit()
                
                output = run_mock_remediation(action_type)
                db_action.execution_output = output
                db_action.status = "executed"
                
                db.add(IncidentTimeline(
                    incident_id=incident.id,
                    event_type="action_executed",
                    description=f"Auto-executed safe remediation action: '{action_type}'"
                ))
                db.commit()
            else:
                # Staging Risky Action
                has_risky_actions = True
                db_action.status = "pending_approval"
                db.add(db_action)
                db.commit()
                
                db.add(IncidentTimeline(
                    incident_id=incident.id,
                    event_type="action_proposed",
                    description=f"Proposed risky action '{action_type}' (requires SRE approval): {details}"
                ))
                db.commit()
                
        if has_risky_actions:
            incident.status = "awaiting_approval"
            db.add(IncidentTimeline(
                incident_id=incident.id,
                event_type="awaiting_operator_approval",
                description="One or more risky remediation actions require manual Operator approval."
            ))
            db.commit()
            print(f"[Graph Node] Incident {incident.id} transitioned to awaiting operator approval.")
            return {"db_status": "awaiting_approval"}
        else:
            print(f"[Graph Node] Only safe actions proposed/executed for incident {incident.id}.")
            return {"db_status": "resolved"}
    except Exception as e:
        db.rollback()
        print(f"[Graph Node] [ERROR] in remediation_node: {e}")
        return {}
    finally:
        db.close()

def resolve_and_postmortem_node(state: IncidentGraphState) -> Dict[str, Any]:
    """Node: Closes the lifecycle loop, resolves the incident, and generates the postmortem report."""
    db = SessionLocal()
    try:
        incident = db.query(Incident).filter(Incident.id == state["incident_id"]).first()
        if incident:
            incident.status = "resolved"
            incident.ends_at = datetime.utcnow()
            db.add(IncidentTimeline(
                incident_id=incident.id,
                event_type="resolved",
                description="Incident resolved successfully after executing remediation actions."
            ))
            db.commit()
            print(f"[Graph Node] Incident {incident.id} marked as resolved. Creating postmortem report...")
            generate_postmortem(incident.id)
        return {"db_status": "resolved"}
    except Exception as e:
        db.rollback()
        print(f"[Graph Node] [ERROR] in resolve_and_postmortem_node: {e}")
        return {}
    finally:
        db.close()

# ----------------------------------------------------
# 2. CONDITIONAL EDGES / ROUTING LOGIC
# ----------------------------------------------------

def routing_decider(state: IncidentGraphState) -> str:
    """Checks confidence score and recent deployment logs for meta-cognition routing."""
    confidence = state.get("confidence_score", 100)
    sys_metrics = state.get("system_metrics", {})
    recent_deploys = sys_metrics.get("recent_deployments", [])
    
    if confidence < 80 or not recent_deploys:
        return "manual_diagnosis"
    else:
        return "remediation"

def risk_decider(state: IncidentGraphState) -> str:
    """Branches output based on whether any risky actions were enqueued."""
    if state.get("db_status") == "awaiting_approval":
        return "await_approval"
    else:
        return "resolve_and_postmortem"

# ----------------------------------------------------
# 3. COMPILE LANGGRAPH STATEGRAPH
# ----------------------------------------------------

workflow = StateGraph(IncidentGraphState)

# Add Nodes
workflow.add_node("collect_context", collect_context_node)
workflow.add_node("llm_analysis", llm_analysis_node)
workflow.add_node("manual_diagnosis", manual_diagnosis_node)
workflow.add_node("remediation", remediation_node)
workflow.add_node("resolve_and_postmortem", resolve_and_postmortem_node)

# Set Node Edges
workflow.add_edge(START, "collect_context")
workflow.add_edge("collect_context", "llm_analysis")

# Set Conditional Routing Edges
workflow.add_conditional_edges(
    "llm_analysis",
    routing_decider,
    {
        "manual_diagnosis": "manual_diagnosis",
        "remediation": "remediation"
    }
)

workflow.add_edge("manual_diagnosis", END)

workflow.add_conditional_edges(
    "remediation",
    risk_decider,
    {
        "await_approval": END,
        "resolve_and_postmortem": "resolve_and_postmortem"
    }
)

workflow.add_edge("resolve_and_postmortem", END)

compiled_graph = workflow.compile()

# ----------------------------------------------------
# 4. EXPOSED UTILITY & CORE FUNCTIONS
# ----------------------------------------------------

def build_agent_input(incident_id: str) -> dict:
    db = SessionLocal()
    try:
        inc = db.query(Incident).get(incident_id)
        if not inc:
            return None
        
        payload = {
            "incident_id": inc.id,
            "alert_name": inc.alert_name,
            "status": inc.status,
            "severity": inc.severity,
            "starts_at": inc.starts_at.isoformat() if inc.starts_at else None,
            "ends_at": inc.ends_at.isoformat() if inc.ends_at else None,
            "metrics_snapshot": json.loads(inc.metrics_snapshot) if inc.metrics_snapshot else {},
            "system_metrics": json.loads(inc.system_metrics) if inc.system_metrics else {},
            "analysis_summary": inc.analysis_summary,
            "timeline": [
                {"timestamp": t.timestamp.isoformat(), "event_type": t.event_type, "description": t.description}
                for t in inc.timeline
            ],
            "actions": [
                {"id": a.id, "action_type": a.action_type, "risk_level": a.risk_level, "status": a.status, "details": a.details}
                for a in inc.actions
            ]
        }
        return payload
    finally:
        db.close()

def run_agent_on_incident(incident_id: str):
    """Executes the SRE Agent StateGraph for the given incident."""
    initial_state = {
        "incident_id": incident_id,
        "alert_name": "",
        "severity": "",
        "starts_at": "",
        "metrics_snapshot": {},
        "system_metrics": {},
        "analysis_summary": "",
        "confidence_score": 100,
        "missing_context_details": "",
        "proposed_actions": [],
        "db_status": ""
    }
    print(f"[Agent Graph] Invoking LangGraph workflow execution for incident {incident_id}...")
    try:
        compiled_graph.invoke(initial_state)
        print(f"[Agent Graph] Workflow completed successfully.")
    except Exception as e:
        print(f"[Agent Graph] [CRITICAL ERROR] Graph execution failed: {e}")

def run_mock_remediation(action_type: str) -> str:
    import time
    print(f"[Remediation] Running SRE action '{action_type}'...")
    time.sleep(1) # Simulate operation lag
    
    if action_type == "clear_cache":
        try:
            from demo_app.app import memory_hog
            memory_hog.clear()
            MEMORY_USAGE.set(10 * 1024 * 1024) # set memory usage to healthy baseline (10MB)
        except Exception as e:
            print(f"[Remediation] [Warning] Failed to clear memory hog: {e}")
        return "Cache memory storage cleared. Wiped active RAM footprint."
        
    elif action_type == "restart_service":
        try:
            from demo_app.app import memory_hog
            memory_hog.clear()
            MEMORY_USAGE.set(5 * 1024 * 1024)
            CPU_USAGE.set(12.0)
        except Exception as e:
            print(f"[Remediation] [Warning] Failed to reset metrics: {e}")
        return "API service restarted successfully. Threadlocks released. Telemetry baselines reset."
        
    elif action_type == "rollback_deploy":
        return "Git config deployment rolled back. Reverted target pool migration configuration to stable commit SHA."
        
    elif action_type == "scale_up":
        return "Replica container successfully scale-up dispatched. Balanced SRE routing parameters."
        
    elif action_type == "enable_rate_limiting":
        return "Rate-limiting guardrails injected. High-load requests throttled."
        
    return f"Remediation mock for '{action_type}' finished."

def execute_sensitive_remediation(action_id: str):
    """Executes a staged risky action upon Operator approval, then resumes postmortem loop."""
    db = SessionLocal()
    try:
        action = db.query(RemediationAction).filter(RemediationAction.id == action_id).first()
        if not action:
            print(f"[Remediation] Action ID {action_id} not found.")
            return
        
        # 1. Update action status to executing
        action.status = "executing"
        db.commit()
        
        # 2. Trigger mock execution
        output = run_mock_remediation(action.action_type)
        action.execution_output = output
        action.status = "executed"
        
        # 3. Log execution on timeline
        db.add(IncidentTimeline(
            incident_id=action.incident_id,
            event_type="action_executed",
            description=f"Executed SRE approved action: '{action.action_type}'"
        ))
        db.commit()
        
        # 4. Check if there are other pending/executing actions left
        remaining_pending = db.query(RemediationAction).filter(
            RemediationAction.incident_id == action.incident_id,
            RemediationAction.status.in_(["pending_approval", "executing"])
        ).first()
        
        if not remaining_pending:
            # Trigger the resolve and postmortem node to close loop
            print(f"[Remediation] All actions completed for {action.incident_id}. Handing over to resolve node...")
            state = {
                "incident_id": action.incident_id,
                "alert_name": "",
                "severity": "",
                "starts_at": "",
                "metrics_snapshot": {},
                "system_metrics": {},
                "analysis_summary": "",
                "confidence_score": 100,
                "missing_context_details": "",
                "proposed_actions": [],
                "db_status": "analyzed"
            }
            resolve_and_postmortem_node(state)
            
    except Exception as e:
        db.rollback()
        print(f"[Remediation] [ERROR] Failed to execute sensitive remediation: {e}")
    finally:
        db.close()

def generate_postmortem(incident_id: str):
    db = SessionLocal()
    try:
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if not incident:
            print(f"[Postmortem] Incident {incident_id} not found.")
            return
        
        # Calculate duration
        duration_str = "Unknown"
        if incident.starts_at and incident.ends_at:
            duration = incident.ends_at - incident.starts_at
            duration_str = str(duration)
        elif incident.starts_at:
            duration = datetime.utcnow() - incident.starts_at
            duration_str = str(duration) + " (In-progress/Ongoing)"
        
        # Parse metrics snapshot
        metrics_snapshot_raw = incident.metrics_snapshot
        metrics_snapshot_formatted = ""
        if metrics_snapshot_raw:
            try:
                snapshot = json.loads(metrics_snapshot_raw)
                for name, info in snapshot.items():
                    m_type = info.get("type", "unknown")
                    samples_str = ""
                    for s in info.get("samples", []):
                        labels = s.get("labels", {})
                        lbl_str = ",".join(f"{k}='{v}'" for k, v in labels.items())
                        lbl_bracket = f"{{{lbl_str}}}" if lbl_str else ""
                        samples_str += f"    - {s.get('name')}{lbl_bracket} = {s.get('value')}\n"
                    metrics_snapshot_formatted += f"- **{name}** ({m_type}):\n{samples_str}"
            except Exception as e:
                metrics_snapshot_formatted = f"Error parsing metrics snapshot: {e}"
        else:
            metrics_snapshot_formatted = "No metrics snapshot captured."
            
        # Parse system metrics
        sys_raw = incident.system_metrics
        cpu = "N/A"
        memory = "N/A"
        platform = "N/A"
        service = "N/A"
        deployments_str = "None found in 15-minute window."
        
        if sys_raw:
            try:
                sys_data = json.loads(sys_raw)
                cpu = f"{sys_data.get('cpu_usage_percent', 0)}%"
                memory = f"{sys_data.get('memory_usage_bytes', 0)} bytes"
                platform = sys_data.get("platform", "unknown")
                service = sys_data.get("service", "unknown")
                deploys = sys_data.get("recent_deployments", [])
                if deploys:
                    deployments_str = ""
                    for d in deploys:
                        deployments_str += f"- [{d.get('timestamp')}] SHA: `{d.get('sha')}` | Author: {d.get('author')}\n  Description: {d.get('description')}\n"
            except Exception as e:
                deployments_str = f"Error parsing system metrics: {e}"
                
        # Timeline
        timeline_str = ""
        for t in sorted(incident.timeline, key=lambda x: x.timestamp):
            timeline_str += f"- [{t.timestamp.isoformat()}] **{t.event_type}**: {t.description}\n"
            
        # Actions
        actions_str = ""
        if incident.actions:
            for a in incident.actions:
                actions_str += f"- **Action Type**: `{a.action_type}` | **Risk**: {a.risk_level} | **Status**: {a.status}\n"
                actions_str += f"  Details: {a.details}\n"
                if a.execution_output:
                    actions_str += f"  Execution Output: {a.execution_output}\n"
        else:
            actions_str = "No actions proposed."
            
        report = f"""# SRE Incident Postmortem Report
Incident ID: `{incident.id}`
Alert Name: **{incident.alert_name}**

## 1. Incident Executive Summary
- **Severity**: {incident.severity}
- **Status**: {incident.status}
- **Trigger Time (starts_at)**: {incident.starts_at.isoformat() if incident.starts_at else "N/A"} UTC
- **Resolution Time (ends_at)**: {incident.ends_at.isoformat() if incident.ends_at else "N/A"} UTC
- **Total Duration**: {duration_str}

## 2. Root Cause Analysis (AI Reasoning)
{incident.analysis_summary or "No AI analysis performed."}

## 3. Telemetry Snapshot & Context Collection
### System Resources
- **CPU Load**: {cpu}
- **Memory Consumption**: {memory}
- **Platform**: {platform}
- **Service Name**: {service}

### Recent Deployments (15-Minute Alert Window)
{deployments_str}

### Active Prometheus Metrics
{metrics_snapshot_formatted}

## 4. Remediation Actions Summary
{actions_str}

## 5. Chronological Incident Timeline
{timeline_str}

## 6. Action Items & Future Recommendations
- Configure higher DB connection limits on the pooling config.
- Optimize caching layer rules to run proactive flushes automatically.
- Adjust alert threshold timings to reduce alerting noise.
"""
        os.makedirs("postmortems", exist_ok=True)
        filename = f"postmortems/incident_{incident_id}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[Postmortem] Successfully generated postmortem report at {filename}")
        
    except Exception as e:
        print(f"[Postmortem] [ERROR] Failed to generate postmortem: {e}")
    finally:
        db.close()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run SRE Remediation Agent on Incident ID or print DB payload")
    parser.add_argument("--id", help="Incident ID to run the agent on")
    parser.add_argument("--print", help="Incident ID to print payload for")
    args = parser.parse_args()

    if args.id:
        print(f"Running agent on incident {args.id}...")
        run_agent_on_incident(args.id)
    elif args.print:
        payload = build_agent_input(args.print)
        if payload is None:
            print(f"Incident not found!")
            return
        print(json.dumps(payload, indent=2, default=str))
    else:
        # Fallback to the default check
        payload = build_agent_input("a90ab838-a303-40a0-86ee-32c6b7bdd46e")
        if payload is None:
            print(f"Default Incident not found. Specify --id or --print.")
            return
        print(json.dumps(payload, indent=2, default=str))

if __name__ == "__main__":
    main()