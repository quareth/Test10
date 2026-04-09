#!/usr/bin/env bash
#
# Create a user for the Sitemap Scraper application.
#
# Usage (local):
#   ./scripts/create-user.sh <username> <password>
#
# Usage (Docker):
#   docker-compose exec app ./scripts/create-user.sh <username> <password>

set -euo pipefail

if [ $# -ne 2 ]; then
    echo "Usage: $0 <username> <password>"
    echo ""
    echo "Create a user for the Sitemap Scraper application."
    echo ""
    echo "Examples:"
    echo "  $0 admin password123              # Local"
    echo "  docker-compose exec app $0 admin password123  # Docker"
    exit 1
fi

USERNAME="$1"
PASSWORD="$2"

# Determine the project root (parent of the scripts/ directory).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Choose Python: use the project venv if available, otherwise fall back to
# system python (which is the expected case inside the Docker container).
if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON="$PROJECT_ROOT/.venv/bin/python"
else
    PYTHON="python"
fi

# Run the CLI create-user command from the backend directory so that relative
# imports and default paths resolve correctly.
cd "$PROJECT_ROOT/backend"

exec "$PYTHON" -m backend.cli create-user "$USERNAME" "$PASSWORD"
