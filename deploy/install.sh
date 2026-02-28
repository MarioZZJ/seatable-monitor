#!/bin/bash
set -e
PROJECT_DIR="$HOME/Documents/project/seatable-monitor"
CONFIG_DIR="$HOME/.config/seatable-monitor"

# 复制配置
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.toml" ]; then
    cp "$PROJECT_DIR/config.toml.example" "$CONFIG_DIR/config.toml"
    echo "请编辑 $CONFIG_DIR/config.toml 填写 api_token 和 session_prefixes"
fi

OS="$(uname)"
if [ "$OS" = "Darwin" ]; then
    # macOS: 替换 plist 中的用户名
    PLIST="$HOME/Library/LaunchAgents/com.seatable-monitor.plist"
    sed "s/YOURUSERNAME/$(whoami)/g" \
        "$PROJECT_DIR/deploy/com.seatable-monitor.plist" > "$PLIST"
    launchctl load "$PLIST"
    echo "macOS launchd 服务已安装并启动"
elif [ "$OS" = "Linux" ]; then
    # Linux: systemd user service
    mkdir -p "$HOME/.config/systemd/user"
    cp "$PROJECT_DIR/deploy/seatable-monitor.service" \
        "$HOME/.config/systemd/user/"
    # 写 env 文件（api_token 从 config.toml 读，这里只占位）
    touch "$HOME/.config/seatable-monitor/env"
    systemctl --user daemon-reload
    systemctl --user enable seatable-monitor
    systemctl --user start seatable-monitor
    echo "Linux systemd 服务已安装并启动"
fi
