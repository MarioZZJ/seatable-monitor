#!/bin/bash
# 跨平台启动入口
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export PYTHONUNBUFFERED=1
export SEATABLE_MONITOR_CONFIG="${SEATABLE_MONITOR_CONFIG:-$HOME/.config/seatable-monitor/config.toml}"
exec .venv/bin/python -m seatable_monitor
