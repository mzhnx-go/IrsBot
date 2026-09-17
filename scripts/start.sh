#!/usr/bin/env bash
# IrsBot one-click start (macOS / Linux) - D2.2 / D2.4 / D3.1 / D3.2
#   1.   create .env from .env.example if missing
#   1.5  ensure SECRET_KEY + FIRST_SUPERUSER_PASSWORD are not the
#        insecure default "changethis" (generate random + persist to .env)
#   2.   check Docker
#   3.   docker compose up -d --build
#   4.   poll health-check, then open the browser
set -euo pipefail

cd "$(dirname "$0")/.."

echo
echo "  IrsBot start"
echo "  ============================================"
echo

# ---- 1/5 .env ----
if [ ! -f .env ]; then
    if [ ! -f .env.example ]; then
        echo "  [ERROR] Neither .env nor .env.example exists."
        exit 1
    fi
    cp .env.example .env
    echo "  [1/5] .env created from .env.example."
    echo "        Review SECRET_KEY / DB password / LLM API keys before use."
else
    echo "  [1/5] .env found."
fi

# ---- 1.5/5 secrets (D3.1 / D3.2) ----
gen_value() {
    LC_ALL=C tr -dc 'A-Za-z0-9_-' </dev/urandom | head -c "$1"
}
ensure_var() {
    local name="$1" len="$2"
    local cur
    cur=$(grep -E "^${name}=" .env | head -1 | cut -d= -f2- || true)
    cur=${cur//\"/}
    if [ -z "$cur" ] || [ "$cur" = "changethis" ]; then
        local nv
        nv=$(gen_value "$len")
        if grep -qE "^${name}=" .env; then
            sed -i.bak -E "s|^${name}=.*|${name}=${nv}|" .env
            rm -f .env.bak
        else
            printf '\n%s=%s\n' "$name" "$nv" >> .env
        fi
        echo "$nv"
    else
        echo ""
    fi
}
echo "  [1.5/5] Checking secrets..."
SK_NEW=$(ensure_var SECRET_KEY 32)
PW_NEW=$(ensure_var FIRST_SUPERUSER_PASSWORD 24)
if [ -n "$PW_NEW" ]; then
    echo "  A new random admin password was generated and saved to .env."
    echo "  Use it for your first login, then change it in the UI if you like."
fi
if [ -n "$SK_NEW" ]; then
    echo "  A new random SECRET_KEY was generated and saved to .env."
fi

# ---- 2/5 Docker ----
if ! docker version >/dev/null 2>&1; then
    echo "  [ERROR] Docker not available. Start Docker Desktop / docker daemon."
    exit 1
fi
echo "  [2/5] Docker OK"

# ---- 3/5 start ----
echo "  [3/5] Building and starting containers (first run is slow)..."
docker compose up -d --build

# ---- 4/5 wait until healthy (max 3 min) ----
echo "  [4/5] Waiting for backend..."
READY=0
for _ in $(seq 1 60); do
    if curl -s -f http://localhost:8000/api/v1/utils/health-check/ >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 3
done

if [ "$READY" -ne 1 ]; then
    echo
    echo "  [WARN] Timed out. Check logs: docker compose logs -f backend"
    exit 1
fi

SU=$(grep -E '^FIRST_SUPERUSER=' .env | cut -d= -f2- || true)
SUPW=$(grep -E '^FIRST_SUPERUSER_PASSWORD=' .env | cut -d= -f2- || true)

echo
echo "  Ready"
echo "  --------------------------------------------"
echo "  URL      : http://localhost:8000"
echo "  Account  : ${SU}"
echo "  Password : ${SUPW}"
echo "  Logs     : docker compose logs -f backend"
echo "  Stop     : ./scripts/stop.sh"
echo "  --------------------------------------------"
echo
echo "  The admin password above is the one to use for your first login."
echo "  It was randomly generated on first run and saved to .env; change it"
echo "  in the UI later if you like."
echo

# open browser if a graphical environment is available
if command -v open >/dev/null 2>&1; then
    open http://localhost:8000
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open http://localhost:8000
fi
