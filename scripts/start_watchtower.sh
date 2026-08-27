#!/usr/bin/env bash
# ==============================================================================
# 🗼 Start Watchtower Daemon for Automated Docker Container Updates
#
# Watchtower is a lightweight 15MB Golang container that monitors running
# containers and automatically restarts them when updated images are available.
# ==============================================================================

set -e

WATCHTOWER_CONTAINER="watchtower"
POLL_INTERVAL="${WATCHTOWER_POLL_INTERVAL:-3600}" # Default: 1 hour (3600s)

echo "🗼 Starting Watchtower automated container update daemon..."

# Remove existing watchtower container if running
docker stop "${WATCHTOWER_CONTAINER}" 2>/dev/null || true
docker rm "${WATCHTOWER_CONTAINER}" 2>/dev/null || true

# Start Watchtower with label filtering & automatic cleanup of old images
docker run -d \
    --name "${WATCHTOWER_CONTAINER}" \
    --restart always \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -e WATCHTOWER_CLEANUP=true \
    -e WATCHTOWER_POLL_INTERVAL="${POLL_INTERVAL}" \
    -e WATCHTOWER_LABEL_ENABLE=true \
    -e WATCHTOWER_INCLUDE_RESTARTING=true \
    containrrr/watchtower

echo "✅ Watchtower is now running and monitoring containers with label 'com.centurylinklabs.watchtower.enable=true' (Poll Interval: ${POLL_INTERVAL}s)!"
