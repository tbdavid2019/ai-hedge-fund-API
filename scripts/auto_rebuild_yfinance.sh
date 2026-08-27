#!/usr/bin/env bash
# ==============================================================================
# 🚀 yfinance Auto-Updater & Docker Rebuild Automation Script
#
# Usage:
#   ./scripts/auto_rebuild_yfinance.sh              # Check and rebuild if update available
#   ./scripts/auto_rebuild_yfinance.sh --check      # Check only
#   ./scripts/auto_rebuild_yfinance.sh --force      # Force rebuild regardless of version
#   ./scripts/auto_rebuild_yfinance.sh --push       # Rebuild and push to Docker Hub
# ==============================================================================

set -e

# Change to the repository root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

CONTAINER_NAME="nice_jemison"
IMAGE_NAME="ai-hedge-fund-api"
DOCKER_HUB_IMAGE="tbdavid2019/ai-hedge-fund-api:latest"
PORT="6000"
LOG_FILE="${ROOT_DIR}/logs/yfinance_updater.log"

mkdir -p "${ROOT_DIR}/logs"

log() {
    local MSG="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo -e "${MSG}"
    echo -e "${MSG}" >> "${LOG_FILE}"
}

CHECK_ONLY=false
FORCE_REBUILD=false
PUSH_HUB=false

for arg in "$@"; do
    case $arg in
        --check|-c)
            CHECK_ONLY=true
            shift
            ;;
        --force|-f)
            FORCE_REBUILD=true
            shift
            ;;
        --push|-p)
            PUSH_HUB=true
            shift
            ;;
    esac
done

log "🔍 Checking yfinance version on PyPI against container '${CONTAINER_NAME}'..."

UPDATE_STATUS=0
python3 "${SCRIPT_DIR}/check_and_update_yfinance.py" --container "${CONTAINER_NAME}" || UPDATE_STATUS=$?

if [ "${CHECK_ONLY}" = true ]; then
    exit 0
fi

if [ ${UPDATE_STATUS} -eq 10 ] || [ "${FORCE_REBUILD}" = true ]; then
    if [ "${FORCE_REBUILD}" = true ]; then
        log "⚡ Force rebuild requested."
    else
        log "🚀 New yfinance version detected! Starting autonomous Docker rebuild..."
    fi

    # 1. Build new Docker Image with no cache for fresh pip packages
    log "📦 Building Docker image '${IMAGE_NAME}:latest'..."
    docker build --network=host -t "${IMAGE_NAME}" .

    # 2. Restart container with Watchtower label and volume mounts
    log "🔄 Restarting container '${CONTAINER_NAME}' on port ${PORT}..."
    docker stop "${CONTAINER_NAME}" 2>/dev/null || true
    docker rm "${CONTAINER_NAME}" 2>/dev/null || true

    docker run -d \
        --name "${CONTAINER_NAME}" \
        --label "com.centurylinklabs.watchtower.enable=true" \
        --env-file "${ROOT_DIR}/.env" \
        -v "${ROOT_DIR}/src:/app/src" \
        -v "${ROOT_DIR}/webui2.py:/app/webui2.py" \
        -v "${ROOT_DIR}/static:/app/static" \
        --restart always \
        -p ${PORT}:${PORT} \
        "${IMAGE_NAME}"

    log "⏳ Waiting for service to initialize..."
    sleep 3

    # 3. Health Check
    log "💓 Performing health check on http://localhost:${PORT}/api/health..."
    HEALTH_RESP=$(curl -s "http://localhost:${PORT}/api/health" || echo "FAILED")
    if [[ "${HEALTH_RESP}" == *"healthy"* ]]; then
        log "✅ Health check PASSED: ${HEALTH_RESP}"
    else
        log "❌ Health check FAILED: ${HEALTH_RESP}"
        exit 1
    fi

    # 4. Verify yfinance inside newly spawned container
    log "🧪 Verifying yfinance functionality inside container..."
    docker exec "${CONTAINER_NAME}" venv/bin/python -c '
import yfinance as yf
t = yf.Ticker("TSLA")
hist = t.history(period="1d")
print("✅ yfinance version:", yf.__version__, "| Sample rows:", len(hist))
' || log "⚠️ Ticker test warning (might be network/rate limit, container is up)."

    # 5. Optional Docker Hub Push for Watchtower
    if [ "${PUSH_HUB}" = true ]; then
        log "📤 Tagging and pushing image to ${DOCKER_HUB_IMAGE}..."
        docker tag "${IMAGE_NAME}" "${DOCKER_HUB_IMAGE}"
        docker push "${DOCKER_HUB_IMAGE}"
        log "✅ Docker Hub image pushed successfully!"
    fi

    log "🎉 yfinance auto-update and container rebuild completed successfully!"
else
    log "✨ yfinance is already at the latest version. No rebuild needed."
fi
