# seatable-monitor

常驻后台的任务监控 daemon，自动采集 tmux 会话输出和 Claude Code 任务进度，推送到 SeaTable 看板实时展示。

支持 macOS 和 Linux，多台机器同时推送同一张表（通过 `机器` 列区分）。

## 效果

SeaTable 看板按 `状态` 列分组：`待办` → `进行中` → `已完成` → `未知`

每行包含：任务名、状态、来源（tmux/claude-code）、会话ID、最新输出、更新时间、所属机器。

## 前置要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- tmux（可选，不用 tmux 采集可不装）
- SeaTable 账号及 API Token

## 安装

```bash
git clone https://github.com/YOUR_USERNAME/seatable-monitor.git ~/seatable-monitor
cd ~/seatable-monitor
```

## 配置

**1. 获取 SeaTable API Token**

登录你的 SeaTable 实例 → 右上角头像 → **API Token** → 新建一个 Base 级别的 Token，复制备用。

**2. 创建配置文件**

```bash
mkdir -p ~/.config/seatable-monitor
cp config.toml.example ~/.config/seatable-monitor/config.toml
```

**3. 编辑配置**

```toml
[seatable]
server_url = "https://table.nju.edu.cn"   # 你的 SeaTable 实例地址
api_token  = "YOUR_API_TOKEN"              # 粘贴刚才复制的 Token
table_name = "任务监控"                    # 表名，不存在会自动创建

[monitor]
poll_interval = 30   # 采集间隔（秒）
hostname = ""        # 留空自动取 socket.gethostname()

[tmux]
# 只监控名称以指定前缀开头的 session
session_prefixes = ["work", "train"]

[claude]
todos_dir     = "~/.claude/todos"
tasks_dir     = "~/.claude/tasks"
enabled       = true
lookback_hours = 5   # 只追踪最近 5 小时内有更新的任务
```

**4. 安装并启动服务**

安装脚本会自动创建 venv、安装依赖，并注册为系统服务（macOS launchd / Linux systemd）：

```bash
bash deploy/install.sh
```

首次运行会自动在 SeaTable 中建表、建列、建选项。

> **macOS 提示**：首次启动时系统可能弹出 TCC 权限请求，点击允许即可。如果进程卡住无输出，请在 **系统设置 → 隐私与安全性 → 完全磁盘访问权限** 中授权 `/bin/bash`。

### 前台测试

```bash
bash deploy/run.sh
```

### 管理服务

**macOS（launchd）**

```bash
# 查看日志
tail -f /tmp/seatable-monitor.log

# 停止服务
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.seatable-monitor.plist

# 重启服务
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.seatable-monitor.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.seatable-monitor.plist
```

**Linux（systemd user service）**

```bash
# 查看状态
systemctl --user status seatable-monitor

# 查看日志
journalctl --user -u seatable-monitor -f

# 停止 / 重启
systemctl --user stop    seatable-monitor
systemctl --user restart seatable-monitor
```

## 多机器使用

每台机器独立部署，共享同一张 SeaTable 表。行通过 `机器` 列（hostname）区分，upsert key = `(任务名, 会话ID, 机器)`，不会互相覆盖。

## 项目结构

```
seatable-monitor/
├── pyproject.toml
├── config.toml.example
├── src/seatable_monitor/
│   ├── main.py              # daemon 入口 + 轮询调度
│   ├── config.py            # TOML 配置加载
│   ├── models.py            # TaskInfo 数据类
│   ├── seatable_client.py   # SeaTable API 封装
│   └── collectors/
│       ├── tmux.py          # tmux 会话采集
│       └── claude.py        # Claude Code 任务采集
└── deploy/
    ├── install.sh                    # 自动安装脚本
    ├── run.sh                        # 跨平台启动入口
    ├── com.seatable-monitor.plist    # macOS launchd
    └── seatable-monitor.service      # Linux systemd
```

## 安全说明

- API Token 存放在 `~/.config/seatable-monitor/config.toml`，不进入版本库
- `config.toml` 已在 `.gitignore` 中
- 也可通过环境变量 `SEATABLE_API_TOKEN` 传入 Token
