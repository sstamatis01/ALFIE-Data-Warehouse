# Running non-dockerized services on Ubuntu

These services run **outside** Docker and need a local Python env: Agentic Core Orchestrator and Concept Drift Consumer.

## 1. One-time setup

### Install Python 3.10+ and venv (if needed)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
# Optional: python3.11 if your distro has it
# sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

### Create venv and install dependencies

From the repo root (e.g. `~/ALFIE-Data-Warehouse`):

```bash
chmod +x scripts/setup_venv_ubuntu.sh
./scripts/setup_venv_ubuntu.sh
```

Or manually:

```bash
cd ~/ALFIE-Data-Warehouse
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Installation can take several minutes (torch, AutoGluon, etc.).

### Task Manager client (Agentic Core only)

The **Agentic Core Orchestrator** imports `TaskManagerClient` from `task_manager.client.client`. If that package lives in another repo (e.g. Task Manager):

- Either install that package in the venv (`pip install -e /path/to/task-manager-repo`), or  
- Add it to `PYTHONPATH` when running the orchestrator:

```bash
export PYTHONPATH="/path/to/task-manager-repo:$PYTHONPATH"
python agentic_core_orchestrator.py
```

## 2. Environment variables (deployment server)

Create a `.env` in the repo root or export before running. Example for **alfie.iti.gr**:

```bash
# Kafka
export KAFKA_BOOTSTRAP_SERVERS=alfie.iti.gr:9092

# Data Warehouse API
export API_BASE=https://alfie.iti.gr/autodw

# Task Manager (orchestrator only; adjust if Task Manager runs elsewhere)
export TASK_MANAGER_URL=http://localhost:8102
# If Task Manager is on another host:
# export TASK_MANAGER_URL=https://alfie.iti.gr/taskmanager
```

Optional (concept drift consumer):

```bash
export KAFKA_CONCEPT_DRIFT_TRIGGER_TOPIC=concept-drift-trigger-events
export KAFKA_CONCEPT_DRIFT_COMPLETE_TOPIC=concept-drift-complete-events
export KAFKA_CONCEPT_DRIFT_CONSUMER_GROUP=concept-drift-consumer
# If API is on same host:
export DW_HOST=localhost
export DW_PORT=8000
# Or leave unset and set API_BASE only
```

You can also copy `env.example.txt` to `.env` and set the variables there; the scripts use `python-dotenv` where applicable.

## 3. Run the services

Activate the venv and run in separate terminals (or under tmux/screen).

### Agentic Core Orchestrator

Listens to Kafka and drives the pipeline via Task Manager (bias → automl → concept drift → xai).

```bash
cd ~/ALFIE-Data-Warehouse
source .venv/bin/activate
# If using Task Manager from another repo:
# export PYTHONPATH=/path/to/task-manager-repo:$PYTHONPATH
export TASK_MANAGER_URL=http://localhost:8102
export KAFKA_BOOTSTRAP_SERVERS=alfie.iti.gr:9092
export API_BASE=https://alfie.iti.gr/autodw
python agentic_core_orchestrator.py
```

### Concept Drift Consumer

Listens to concept-drift-trigger-events, runs drift detection and retraining, publishes concept-drift-complete-events.

```bash
cd ~/ALFIE-Data-Warehouse
source .venv/bin/activate
export KAFKA_BOOTSTRAP_SERVERS=alfie.iti.gr:9092
export API_BASE=https://alfie.iti.gr/autodw
python kafka_concept_drift_consumer_example.py
```

## 4. Run in background (optional)

**Using nohup:**

```bash
source .venv/bin/activate
nohup python agentic_core_orchestrator.py > logs/orchestrator.log 2>&1 &
nohup python kafka_concept_drift_consumer_example.py > logs/concept_drift.log 2>&1 &
```

Create `logs` first: `mkdir -p logs`.

**Using tmux (recommended for debugging):**

```bash
tmux new -s orchestrator
source .venv/bin/activate
export TASK_MANAGER_URL=http://localhost:8102 KAFKA_BOOTSTRAP_SERVERS=alfie.iti.gr:9092 API_BASE=https://alfie.iti.gr/autodw
python agentic_core_orchestrator.py
# Detach: Ctrl+B, then D
# Reattach: tmux attach -t orchestrator
```

Repeat in another tmux session for the concept drift consumer.

**Using systemd:** You can add two unit files (e.g. `agentic-core-orchestrator.service` and `concept-drift-consumer.service`) that set `WorkingDirectory`, `Environment`, and `ExecStart` to the venv Python and script. Ask if you want example unit files.

## 5. Quick checklist

- [ ] Python 3.10+ and venv installed  
- [ ] `.venv` created and `requirements.txt` installed  
- [ ] Task Manager client available (PYTHONPATH or pip) for the orchestrator  
- [ ] `.env` or exports set (KAFKA_BOOTSTRAP_SERVERS, API_BASE, TASK_MANAGER_URL)  
- [ ] Kafka reachable (e.g. `telnet alfie.iti.gr 9092` or `nc -zv alfie.iti.gr 9092`)  
- [ ] Task Manager and Data Warehouse API reachable at the URLs you set  
