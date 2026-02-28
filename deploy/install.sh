#!/bin/bash
set -e

# 项目目录 = install.sh 所在目录的上级
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_DIR="$HOME/.config/seatable-monitor"

# 复制配置
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.toml" ]; then
    cp "$PROJECT_DIR/config.toml.example" "$CONFIG_DIR/config.toml"
    echo "请编辑 $CONFIG_DIR/config.toml 填写 api_token 和 session_prefixes"
fi

# 创建 venv 并安装依赖
cd "$PROJECT_DIR"
if [ ! -d ".venv" ]; then
    uv venv .venv
fi
uv pip install -e .

OS="$(uname)"
if [ "$OS" = "Darwin" ]; then
    PLIST="$HOME/Library/LaunchAgents/com.seatable-monitor.plist"
    launchctl bootout gui/$(id -u) "$PLIST" 2>/dev/null || true
    sed -e "s|YOURUSERNAME|$(whoami)|g" \
        -e "s|PROJECTDIR|$PROJECT_DIR|g" \
        "$PROJECT_DIR/deploy/com.seatable-monitor.plist" > "$PLIST"
    launchctl bootstrap gui/$(id -u) "$PLIST"
    echo "macOS launchd 服务已安装并启动"
    echo "提示：如果 Python 进程被 TCC 阻塞，请在 系统设置 > 隐私与安全性 > 完全磁盘访问权限 中授权 /bin/bash"
elif [ "$OS" = "Linux" ]; then
    UNIT_DIR="$HOME/.config/systemd/user"
    mkdir -p "$UNIT_DIR"
    sed "s|PROJECTDIR|$PROJECT_DIR|g" \
        "$PROJECT_DIR/deploy/seatable-monitor.service" > "$UNIT_DIR/seatable-monitor.service"
    systemctl --user daemon-reload
    systemctl --user enable seatable-monitor
    systemctl --user start seatable-monitor
    echo "Linux systemd 服务已安装并启动"
fi
