#!/usr/bin/env bash
# MicroClaw startup script — starts API server + Telegram bot
# Usage: ./start.sh
# Requires: MICROCLAW_TELEGRAM_BOT_TOKEN and MICROCLAW_TELEGRAM_CHAT_ID in .env

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env if present
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a; source "$SCRIPT_DIR/.env"; set +a
fi

# Kill any existing instances
fuser -k 8769/tcp 2>/dev/null || true
pkill -f "telegram_bot.py" 2>/dev/null || true
sleep 1

echo "[microclaw] Starting API server on :8769..."
nohup python3 -m uvicorn src.api:app \
    --host 0.0.0.0 \
    --port 8769 \
    --app-dir "$SCRIPT_DIR" \
    > /tmp/microclaw_api.log 2>&1 &
API_PID=$!
echo "[microclaw] API server PID: $API_PID"

# Wait for API to be ready
echo "[microclaw] Waiting for API to be ready..."
for i in $(seq 1 120); do
    if curl -sf http://localhost:8769/health > /dev/null 2>&1; then
        echo "[microclaw] API ready ✅"
        break
    fi
    sleep 2
done

# Start Telegram bot only if token is set
if [ -n "$MICROCLAW_TELEGRAM_BOT_TOKEN" ]; then
    echo "[microclaw] Starting Telegram bot (@clawmicrobot)..."
    cd "$SCRIPT_DIR/src" && nohup python3 telegram_bot.py \
        > /tmp/microclaw_bot.log 2>&1 &
    BOT_PID=$!
    echo "[microclaw] Telegram bot PID: $BOT_PID"
else
    echo "[microclaw] ⚠️  MICROCLAW_TELEGRAM_BOT_TOKEN not set — Telegram bot not started"
fi

echo "[microclaw] ✅ MicroClaw running"
echo "  API:     http://localhost:8769"
echo "  API log: /tmp/microclaw_api.log"
echo "  Bot log: /tmp/microclaw_bot.log"
