#!/usr/bin/env bash
# IrsBot clean reset (macOS / Linux) - D4.1
#   Remove ALL containers + data volumes (db + milvus), then one-click start.
#   WARNING: this deletes every conversation / knowledge base / config stored
#   in the Docker volumes. Use it only to start from a truly clean state.
set -euo pipefail
cd "$(dirname "$0")/.."

echo
echo "  IrsBot clean reset"
echo "  ============================================"
echo "  WARNING: this removes ALL data (db + milvus"
echo "  volumes) and rebuilds from scratch."
echo

if ! docker version >/dev/null 2>&1; then
    echo "  [ERROR] Docker not available. Start Docker first."
    exit 1
fi

echo "  Stopping and removing containers + volumes..."
docker compose down -v

echo "  Starting clean one-click setup..."
"$(dirname "$0")/start.sh"
