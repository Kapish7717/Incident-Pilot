import sqlite3
import json
from tabulate import tabulate

conn = sqlite3.connect('incidents.db')
cursor = conn.cursor()

# ----------------------------------------------------
# 1. Query & Print Incidents Table
# ----------------------------------------------------
print("=" * 80)
print("                    1. INCIDENTS TABLE CONTENT")
print("=" * 80)
cursor.execute("""
SELECT 
    id,
    alert_name,
    status,
    severity,
    starts_at,
    ends_at
FROM incidents
""")
incidents_rows = cursor.fetchall()
incidents_cols = [desc[0] for desc in cursor.description]
print(tabulate(incidents_rows, headers=incidents_cols, tablefmt="grid"))
print("\n")

# ----------------------------------------------------
# 2. Query & Print Incident Timeline Table
# ----------------------------------------------------
print("=" * 80)
print("                 2. INCIDENT TIMELINE TABLE CONTENT")
print("=" * 80)
cursor.execute("""
SELECT 
    id,
    incident_id,
    timestamp,
    event_type,
    description
FROM incident_timeline
""")
timeline_rows = cursor.fetchall()
timeline_cols = [desc[0] for desc in cursor.description]
print(tabulate(timeline_rows, headers=timeline_cols, tablefmt="grid"))
print("\n")

# ----------------------------------------------------
# 3. LATEST INCIDENT TELEMETRY SNAPSHOT (METRICS_SNAPSHOT)
# ----------------------------------------------------
print("=" * 80)
print("      3. LATEST INCIDENT TELEMETRY SNAPSHOT (METRICS_SNAPSHOT)")
print("=" * 80)

# Fetch the single most recent incident
cursor.execute("""
SELECT 
    id,
    alert_name,
    metrics_snapshot
FROM incidents
ORDER BY starts_at DESC
LIMIT 1
""")
row = cursor.fetchone()

if row:
    inc_id, alert_name, snapshot_raw = row
    print(f"\n>>> LATEST INCIDENT: {alert_name} (ID: {inc_id})")
    
    if not snapshot_raw:
        print("    [No metrics snapshot captured for this incident]")
    else:
        try:
            snapshot = json.loads(snapshot_raw)
            table_data = []
            for metric_name, details in snapshot.items():
                metric_type = details.get("type", "unknown")
                for sample in details.get("samples", []):
                    sample_name = sample.get("name", metric_name)
                    
                    # Filter out the '_created' metadata timestamp to keep the output super clean
                    if sample_name.endswith("_created"):
                        continue
                    
                    labels = sample.get("labels", {})
                    labels_str = ",".join(f"{k}='{v}'" for k, v in labels.items())
                    labels_bracket = f"{{{labels_str}}}" if labels_str else ""
                    
                    table_data.append([
                        sample_name + labels_bracket,
                        metric_type,
                        sample.get("value")
                    ])
                    
            print(tabulate(table_data, headers=["Metric Name", "Type", "Captured Value"], tablefmt="simple"))
        except Exception as e:
            print(f"    [Error parsing metrics snapshot: {e}]")
else:
    print("\n[No incidents found in the database]")
print("-" * 80)
print("\n")

# ----------------------------------------------------
# 4. LATEST INCIDENT SYSTEM METRICS & DEPLOYMENTS
# ----------------------------------------------------
print("=" * 80)
print("       4. LATEST INCIDENT SYSTEM METRICS & RECENT DEPLOYMENTS")
print("=" * 80)

cursor.execute("""
SELECT 
    id,
    alert_name,
    system_metrics
FROM incidents
ORDER BY starts_at DESC
LIMIT 1
""")
row = cursor.fetchone()

if row:
    inc_id, alert_name, sys_raw = row
    print(f"\n>>> LATEST INCIDENT: {alert_name} (ID: {inc_id})")
    
    if not sys_raw:
        print("    [No system metrics snapshot captured for this incident]")
    else:
        try:
            sys_data = json.loads(sys_raw)
            print(f"  CPU Usage:       {sys_data.get('cpu_usage_percent', 0)}%")
            print(f"  Memory Usage:    {sys_data.get('memory_usage_bytes', 0)} bytes")
            print(f"  OS Platform:     {sys_data.get('platform', 'unknown')}")
            print(f"  Service:         {sys_data.get('service', 'unknown')}")
            
            deploys = sys_data.get("recent_deployments", [])
            if deploys:
                print("  Recent Deployments found in 15-minute window:")
                for d in deploys:
                    print(f"    - [{d.get('timestamp')}] SHA: {d.get('sha')} | Author: {d.get('author')}")
                    print(f"      Description: {d.get('description')}")
            else:
                print("  Recent Deployments: None found in 15-minute window.")
        except Exception as e:
            print(f"    [Error parsing system metrics: {e}]")
else:
    print("\n[No incidents found in the database]")
print("-" * 80)

conn.close()