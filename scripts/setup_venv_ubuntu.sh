#!/usr/bin/env bash
# Setup Python venv on Ubuntu for non-dockerized services:
#   - Agentic Core Orchestrator (agentic_core_orchestrator.py)
#   - Concept Drift Consumer (kafka_concept_drift_consumer_example.py)
#
# Usage: run from repo root
#   chmod +x scripts/setup_venv_ubuntu.sh
#   ./scripts/setup_venv_ubuntu.sh

set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"
REQUIREMENTS="${REPO_ROOT}/requirements.txt"

echo "Repo root: $REPO_ROOT"
echo "Venv path: $VENV_DIR"

# Python 3.10+ recommended (AutoGluon / torch support)
if ! command -v python3 &>/dev/null; then
    echo "python3 not found. Install with: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    exit 1
fi

PYTHON=$(python3 -c "import sys; print(sys.executable)")
echo "Using: $PYTHON ($($PYTHON --version 2>&1))"

# Create venv if missing
if [[ ! -d "$VENV_DIR" ]]; then
    echo "Creating venv at $VENV_DIR ..."
    "$PYTHON" -m venv "$VENV_DIR"
else
    echo "Venv already exists at $VENV_DIR"
fi

# Activate and upgrade pip
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip setuptools wheel

# Ensure setuptools is installed (needed for pkg_resources used by AutoGluon / concept drift consumer)
pip install 'setuptools>=65.0.0'

# Install requirements (heavy: torch, autogluon, etc.)
if [[ -f "$REQUIREMENTS" ]]; then
    echo "Installing from requirements.txt (this may take several minutes) ..."
    pip install -r "$REQUIREMENTS"
else
    echo "Warning: $REQUIREMENTS not found. Install deps manually."
fi

echo ""
echo "Done. Activate the venv with:"
echo "  source ${VENV_DIR}/bin/activate"
echo ""
echo "Then run e.g.:"
echo "  python agentic_core_orchestrator.py"
echo "  python kafka_concept_drift_consumer_example.py"
echo ""
echo "See scripts/README_NON_DOCKER_SERVICES.md for env vars and Task Manager client."
