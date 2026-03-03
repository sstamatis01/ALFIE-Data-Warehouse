#!/usr/bin/env sh
# Create a GraphDB config in the Data Warehouse API for the local GraphDB (e.g. restored from backup).
# Usage:
#   ./create_graphdb_config.sh [repository_id] [created_by]
# Example:
#   ./create_graphdb_config.sh etd-hub-kg default
# If repository_id is omitted, the script will try to list repositories from GraphDB (requires curl).

set -e
GRAPHDB_URL="${GRAPHDB_URL:-http://localhost:7200}"
API_URL="${API_URL:-http://localhost:8000}"
GDB_USER="${GDB_USER:-admin}"
GDB_PASS="${GDB_PASS:-admin}"

REPO_ID="${1:-}"
CREATED_BY="${2:-default}"

if [ -z "$REPO_ID" ]; then
  echo "Listing repositories from GraphDB at $GRAPHDB_URL ..."
  REPOS=$(curl -s -u "${GDB_USER}:${GDB_PASS}" "${GRAPHDB_URL}/rest/repositories" 2>/dev/null || true)
  if [ -z "$REPOS" ]; then
    echo "Could not list repositories. Please pass the repository ID as the first argument."
    echo "You can find it at ${GRAPHDB_URL} in the Workbench (Setup -> Repositories)."
    echo "Usage: $0 <repository_id> [created_by]"
    exit 1
  fi
  # Try to extract repository id from JSON (simple grep for "id" in typical REST response)
  REPO_ID=$(echo "$REPOS" | grep -o '"id"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/')
  if [ -z "$REPO_ID" ]; then
    echo "Repositories response received but could not parse ID. Please pass repository ID as first argument."
    echo "Usage: $0 <repository_id> [created_by]"
    exit 1
  fi
  echo "Using repository ID: $REPO_ID"
fi

# When the API runs in Docker, it must use the service name to reach GraphDB
SELECT_ENDPOINT="http://graphdb:7200/repositories/${REPO_ID}"
UPDATE_ENDPOINT="http://graphdb:7200/repositories/${REPO_ID}/statements"

echo "Creating GraphDB config in Data Warehouse API at $API_URL ..."
echo "  repository_name: $REPO_ID"
echo "  created_by: $CREATED_BY"

RESPONSE=$(curl -s -X POST "${API_URL}/graphdb/configs?created_by=${CREATED_BY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Local GraphDB (restored backup)\",
    \"description\": \"GraphDB in Docker with initialized backup\",
    \"select_endpoint\": \"${SELECT_ENDPOINT}\",
    \"update_endpoint\": \"${UPDATE_ENDPOINT}\",
    \"username\": \"${GDB_USER}\",
    \"password\": \"${GDB_PASS}\",
    \"repository_name\": \"${REPO_ID}\"
  }")

if echo "$RESPONSE" | grep -q '"id"'; then
  CONFIG_ID=$(echo "$RESPONSE" | grep -o '"id"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/')
  echo "Config created successfully."
  echo "  config_id: $CONFIG_ID"
  echo "You can run SPARQL with: curl -X POST ${API_URL}/graphdb/query -H 'Content-Type: application/json' -d '{\"config_id\": \"$CONFIG_ID\", \"query\": \"SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10\", \"query_type\": \"SELECT\"}'"
else
  echo "Failed to create config. Response:"
  echo "$RESPONSE"
  exit 1
fi
