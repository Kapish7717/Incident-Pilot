from fastapi import FastAPI, Request, BackgroundTasks
from prometheus_client import generate_latest, REGISTRY
from prometheus_client import CONTENT_TYPE_LATEST
from fastapi.responses import Response
import time
import random
from datetime import datetime, timedelta
import json
import os

from demo_app.metrics import *
from demo_app.database import engine, Base, SessionLocal
from demo_app.models import Incident, IncidentTimeline

# Initialize database tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

memory_hog = []

DATA_DIR = "data"
DEPLOY_HISTORY_PATH = os.path.join(DATA_DIR, "deploy_history.json")

def ensure_mock_deployments():
    """Ensures a mock deployment JSON file exists in the data folder for correlation testing."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DEPLOY_HISTORY_PATH):
        # We set the deployment timestamp dynamically to 10 minutes ago
        # so it always fits perfectly inside our 15-minute search window!
        mock_deploys = [
            {
                "timestamp": (datetime.utcnow() - timedelta(minutes=10)).isoformat() + "Z",
                "sha": "9a2f1c8",
                "service": "rag-api",
                "author": "Alice",
                "description": "Database pool size migration config update"
            }
        ]
        with open(DEPLOY_HISTORY_PATH, "w") as f:
            json.dump(mock_deploys, f, indent=4)

def parse_iso_time(time_str: str) -> datetime:
    if not time_str:
        return datetime.utcnow()
    clean_str = time_str.replace("Z", "")
    if "." in clean_str:
        parts = clean_str.split(".")
        fractional = parts[1][:6]  # limit to microsecond precision
        clean_str = f"{parts[0]}.{fractional}"
    try:
        return datetime.fromisoformat(clean_str)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(clean_str, fmt)
            except ValueError:
                pass
        return datetime.utcnow()

def collect_and_analyze(incident_id: str):
    """Background task to collect telemetry metrics snapshot, system stats, and check deployments."""
    # Simulate a brief asynchronous lag for telemetry systems to compile
    time.sleep(2)
    
    db = SessionLocal()
    try:
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if incident:
            # 1. Collect live Prometheus registry metrics
            collected_metrics = {}
            for metric in REGISTRY.collect():
                if metric.name.startswith(("python_", "process_")):
                    continue
                
                samples = [
                    {"name": s.name, "labels": s.labels, "value": s.value}
                    for s in metric.samples
                ]
                collected_metrics[metric.name] = {
                    "type": metric.type,
                    "samples": samples
                }
            incident.metrics_snapshot = json.dumps(collected_metrics)
            
            # 2. Collect System Stats directly from metrics gauges
            cpu_val = 0
            mem_val = 0
            try:
                cpu_val = CPU_USAGE._value.get()
                mem_val = MEMORY_USAGE._value.get()
            except Exception:
                pass
                
            # 3. Deploy Correlation (Check data/deploy_history.json)
            ensure_mock_deployments()
            matching_deploys = []
            
            if os.path.exists(DEPLOY_HISTORY_PATH):
                try:
                    with open(DEPLOY_HISTORY_PATH, "r") as f:
                        deploys = json.load(f)
                    
                    # Search window: 15 minutes before the alert started
                    start_window = incident.starts_at - timedelta(minutes=15)
                    end_window = incident.starts_at
                    
                    for d in deploys:
                        ts_str = d.get("timestamp", "").replace("Z", "")
                        if "." in ts_str:
                            ts_str = ts_str.split(".")[0]
                        deploy_time = datetime.fromisoformat(ts_str)
                        
                        if start_window <= deploy_time <= end_window:
                            matching_deploys.append(d)
                except Exception as e:
                    print(f"Error reading deploy history: {e}")
            
            # 4. Save system metrics and deployments snapshot to SQLite
            system_snapshot = {
                "cpu_usage_percent": cpu_val,
                "memory_usage_bytes": mem_val,
                "platform": "windows",
                "service": "rag-api",
                "recent_deployments": matching_deploys
            }
            incident.system_metrics = json.dumps(system_snapshot)
            incident.status = "analyzed"
            
            # 5. Log timeline audit trail
            db.add(IncidentTimeline(
                incident_id=incident.id,
                event_type="context_collected",
                description=f"Prometheus metrics, CPU/Memory stats, and {len(matching_deploys)} recent deployments collected successfully."
            ))
            db.add(IncidentTimeline(
                incident_id=incident.id,
                event_type="analysis_complete",
                description=f"Incident '{incident.alert_name}' successfully analyzed. Telemetry + deploy snapshots captured in SQLite."
            ))
            db.commit()
            print(f"[Background Task] Successfully analyzed incident {incident_id}.")
            
    except Exception as e:
        db.rollback()
        print(f"Error in background task for incident {incident_id}: {e}")
    finally:
        db.close()

@app.get("/")
def home():
    REQUEST_COUNT.inc()
    return {"status": "healthy"}

# ----------------------------
# High latency simulation
# ----------------------------

@app.get("/slow")
def slow():
    REQUEST_COUNT.inc()
    latency = random.randint(5, 10)
    time.sleep(latency)
    REQUEST_LATENCY.observe(latency)
    return {"latency": latency}

# ----------------------------
# Error simulation
# ----------------------------

@app.get("/error")
def error():
    REQUEST_COUNT.inc()
    ERROR_COUNT.inc()
    return {"error": "simulated failure"}

# ----------------------------
# Memory leak simulation
# ----------------------------

@app.get("/memory")
def memory():
    global memory_hog
    REQUEST_COUNT.inc()
    memory_hog.append("A" * 10_000_000)
    MEMORY_USAGE.set(len(memory_hog) * 10)
    return {"memory_chunks": len(memory_hog)}

# ----------------------------
# CPU spike simulation
# ----------------------------

@app.get("/cpu")
def cpu():
    REQUEST_COUNT.inc()
    start = time.time()
    while time.time() - start < 10:
        pass
    CPU_USAGE.set(95)
    return {"cpu": "spike"}

# ----------------------------
# Detailed Error Simulations
# ----------------------------

@app.get("/db_error")
def db_error():
    REQUEST_COUNT.inc()
    DB_CONNECTION_FAILURES.inc()
    APP_ERRORS_TOTAL.labels(type="db_error", endpoint="/db_error").inc()
    return {"status": "error", "error": "DatabaseConnectionError"}

@app.get("/timeout")
def timeout():
    REQUEST_COUNT.inc()
    LLM_TIMEOUT.inc()
    APP_ERRORS_TOTAL.labels(type="timeout", endpoint="/timeout").inc()
    return {"status": "error", "error": "OpenAITimeout"}

@app.get("/rag_failure")
def rag_failure():
    REQUEST_COUNT.inc()
    RAG_RETRIEVAL_FAILURES.inc()
    APP_ERRORS_TOTAL.labels(type="rag_failure", endpoint="/rag_failure").inc()
    return {"status": "error", "error": "RAGRetrievalFailure"}

@app.get("/invalid_input")
def invalid_input():
    REQUEST_COUNT.inc()
    INVALID_INPUT_ERRORS.inc()
    APP_ERRORS_TOTAL.labels(type="invalid_input", endpoint="/invalid_input").inc()
    return {"status": "error", "error": "ValidationError"}

@app.get("/external_api")
def external_api():
    REQUEST_COUNT.inc()
    EXTERNAL_API_FAILURES.inc()
    APP_ERRORS_TOTAL.labels(type="external_api", endpoint="/external_api").inc()
    return {"status": "error", "error": "ExternalAPIFailure"}

# ----------------------------
# Metrics endpoint
# ----------------------------

@app.get("/metrics")
def metrics():
    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )

@app.post("/alerts")
async def alerts(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()             
    
    alerts_list = data.get("alerts", [])
    db = SessionLocal()
    
    try:
        for alert in alerts_list:
            alert_name = alert.get("labels", {}).get("alertname", "UnknownAlert")
            severity = alert.get("labels", {}).get("severity", "warning")
            status = alert.get("status", "firing")
            starts_at = parse_iso_time(alert.get("startsAt"))
            ends_at = parse_iso_time(alert.get("endsAt")) if alert.get("endsAt") else None
            
            if status == "firing":
                # Check for existing active incident with same name
                existing = db.query(Incident).filter(
                    Incident.alert_name == alert_name,
                    Incident.status != "resolved"
                ).first()
                
                if not existing:
                    # Create new active incident
                    incident = Incident(
                        alert_name=alert_name,
                        status="active",
                        severity=severity,
                        starts_at=starts_at
                    )
                    db.add(incident)
                    db.flush()  # populate incident.id
                    
                    # Add timeline ingestion entry
                    timeline_entry = IncidentTimeline(
                        incident_id=incident.id,
                        event_type="ingest",
                        description=f"Alert '{alert_name}' (severity: {severity}) ingested successfully from Alertmanager."
                    )
                    db.add(timeline_entry)
                    db.commit()  # commit to make sure background task can find the ID
                    
                    # Schedule context collection and analysis in a background task
                    background_tasks.add_task(collect_and_analyze, incident.id)
                    print(f"[Ingest] Ingested alert '{alert_name}'. Scheduled background analysis.")
                else:
                    print(f"[Ingest] Alert '{alert_name}' is already active.")
                    
            elif status == "resolved":
                # Find the active incident to resolve
                active_incident = db.query(Incident).filter(
                    Incident.alert_name == alert_name,
                    Incident.status != "resolved"
                ).first()
                
                if active_incident:
                    active_incident.status = "resolved"
                    active_incident.ends_at = ends_at or datetime.utcnow()
                    
                    timeline_entry = IncidentTimeline(
                        incident_id=active_incident.id,
                        event_type="resolved",
                        description=f"Alert '{alert_name}' marked as resolved by Alertmanager."
                    )
                    db.add(timeline_entry)
                    print(f"[Ingest] Alert '{alert_name}' resolved successfully.")
                else:
                    print(f"[Ingest] Received resolution webhook for '{alert_name}', but no active incident found.")
                    
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error processing alerts webhook: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
        
    return {"status": "processed", "alerts_count": len(alerts_list)}