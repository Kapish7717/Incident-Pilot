# 🤖 Autonomous AI-Agentic SRE Incident Response & Monitoring Engine

Welcome to the **Autonomous AI-Agentic SRE Incident Response System**! This is an advanced, production-grade observability and auto-remediation pipeline designed to ingest live system alerts, automatically compile telemetry snapshots (Prometheus metrics, active system stats, and Git/config deployment logs), and leverage a state-of-the-art LLM Reasoning Agent (**LLaMA-3 via Groq API**) to dynamically route incidents and propose enqueued remediation plans.

---

## 🏗️ System Architecture & Workflow

```
       +-----------------------+
       |   FastAPI App (/slow) | <--- Simulated failures (DB connection spikes, CPU leaks)
       +-----------------------+
                   |
         (Scrapes live metrics /metrics)
                   v
       +-----------------------+
       |   Prometheus Server   | <--- Evaluates rules.yml thresholds
       +-----------------------+
                   |
         (Fires Alert Webhook)
                   v
       +-----------------------+
       |     Alertmanager      | <--- Packages and groups notifications
       +-----------------------+
                   |
         (Delivers POST JSON Webhook)
                   v
  +--------------------------------------------------------------------------+
  | FastAPI Webhook Handler (/alerts)                                        |
  |  1. Persists incident in SQLite (status="active")                        |
  |  2. Launches background asynchronous context compilation task            |
  |                                                                          |
  | ======= Asynchronous Context Collection & Merging Engine =======         |
  |  - Fetches live Prometheus metrics snapshot (excludes Python overhead)  |
  |  - Fetches current CPU & Memory utilization gauge statistics             |
  |  - Filters data/deploy_history.json logs using 15-minute search window   |
  |  - Merges into single 'system_metrics' JSON snapshot in SQLite           |
  |                                                                          |
  | ======= Agentic SRE AI Core (llm.py / ChatGroq) ===================      |
  |  - Maps alert dynamically to pre-defined SRE Runbook rules              |
  |  - Generates comprehensive reasoning prompt for LLaMA-3                  |
  |  - Invokes LLaMA-3 reasoning via LangChain Groq interface                |
  |  - Parses valid JSON Root Cause Analysis & Remediation Plan              |
  |                                                                          |
  | ======= Remediation Division & Interception (HITL) ===============      |
  |  - Safe Actions (e.g. clear cache) -> Auto-executed & logged             |
  |  - Risky Actions (e.g. rollback release) -> Paused & queued              |
  |  - Exposes control panel /approve endpoint to resume execution           |
  +--------------------------------------------------------------------------+
```

---



## 🛠️ Key Features Built & Completed

1. **Phase 1: Webhook Ingestion & In-flight Lock Registry**
   - Integrates with Alertmanager.
   - Saves firing webhooks with standard epoch timestamps and prevents redundant rows (locks active incidents with matching names until resolved).
2. **Phase 2: Live Metrics-Only Context Collection**
   - Dynamically scrapes current Prometheus registry metrics (`REGISTRY.collect()`), filtering out process/GC overhead to keep database records clean.
   - Extracts live CPU/Memory stats and correlates them with Git deployments in `data/deploy_history.json` using a **strict 15-minute search window** preceding the incident.
3. **Phase 3: Agentic SRE Reasoning Core (`llm.py`)**
   - Loaded with a dynamic SRE Runbook repository (`runbooks/`).
   - Uses `ChatGroq` LLaMA-3 reasoning to diagnose the exact root cause and outputs a structured, parsed JSON action plan splitting proposals into **Safe vs. Risky** categories.
4. **Interactive DB Console Utility (`demo_app/check_db.py`)**
   - Pretty-prints incidents and sequential audit timelines cleanly without terminal output truncation.

---

## 🚀 Setup & Installation Instructions

### 1. Configure the Virtual Environment & Dependencies
Clone or navigate to the directory and run:
```bash
# Activate the virtual environment
.\venv\Scripts\activate

# Install all required libraries
pip install -r requirements.txt
```

### 2. Set Up API Keys
Set your Groq API key in your terminal context:
```bash
# Windows PowerShell
$env:GROQ_API_KEY="gsk_your_actual_groq_api_key_here"
```

---

## 🚦 Running the System E2E

### Step 1: Launch Prometheus & Alertmanager
Make sure your monitoring executables are running using their respective loopback config directories:
```bash
# Term 1: Run Prometheus
.\monitoring\prometheus.exe --config.file=monitoring\prometheus.yml

# Term 2: Run Alertmanager
.\monitoring\alertmanager.exe --config.file=monitoring\alertmanager.yml
```

### Step 2: Start the FastAPI Web Application
Run the dev server:
```bash
# Term 3: Run FastAPI
python -m uvicorn demo_app.app:app --reload
```

---

## 🧪 Verification & Testing Guides

### 1. Running the Agent SRE Reasoning Validation
We have implemented a mock verification program in `test_groq.py` which replicates a production database connection alert end-to-end, load standard runbooks, queries Groq LLaMA-3, and validates the parsed JSON plan:
```bash
python test_groq.py
```
*Expected Output:* Shows the parsed JSON plan stating the root cause as Alice's database pool size decrease, proposing `clear_cache` as a SAFE action, and `rollback_deploy` as a RISKY action.

### 2. Triggering a Real Observability Incident
To test the Prometheus Alert webhook ingestion pathway manually:
1. Open your browser and navigate to:
   `http://127.0.0.1:8000/db_error`
2. **Refresh the page 5 times** to increment `db_connection_failures_total` to `5.0`.
3. Wait **5 to 15 seconds** for Prometheus to scrape, evaluate the rule threshold, and dispatch the alert to Alertmanager.
4. Alertmanager will send the firing alert payload to the FastAPI `/alerts` endpoint.
5. In your main terminal, run the database monitor to watch the ingest timeline log:
   ```bash
   python demo_app/check_db.py
   ```
   *Note: Section 3 and 4 of `check_db.py` will display the full captured telemetry snapshot and CPU/RAM/Deploy correlation logs for this new incident!*
6. Restart/reload Uvicorn to reset client counters to `0` and let Prometheus automatically trigger the resolution webhook to mark active incidents as `"resolved"`.

---

## 🧠 Advanced AI Agent Design: Routing & HITL
For a deep architectural explanation of the dynamic AI branching mechanisms (Routing to diagnostics on low confidence, pausing and enqueuing risky actions for operator manual review), refer to the conceptual guide:
👉 **[routing_and_hitl_guide.txt](file:///c:/Kapish/IncidentAgent/routing_and_hitl_guide.txt)**
