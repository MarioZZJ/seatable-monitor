import signal
import socket
import logging
import time

from .config import load_config
from .seatable_client import SeaTableClient
from .collectors.tmux import collect_by_prefixes
from .collectors.claude import collect_todos, collect_tasks

logger = logging.getLogger("seatable-monitor")
_running = True


def _handle_signal(signum, frame):
    global _running
    _running = False
    logger.info("收到退出信号，正在停止...")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    config = load_config()
    machine = config.get("monitor", {}).get("hostname") or socket.gethostname()
    poll_interval = config.get("monitor", {}).get("poll_interval", 30)

    client = SeaTableClient(
        server_url=config["seatable"]["server_url"],
        api_token=config["seatable"]["api_token"],
        table_name=config["seatable"].get("table_name", "任务监控"),
    )
    client.init()
    logger.info("启动成功，机器=%s，间隔=%ds", machine, poll_interval)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    while _running:
        try:
            _run_once(config, client, machine)
            client.refresh_auth_if_needed()
        except Exception:
            logger.exception("本轮采集出错，将在下次重试")
        time.sleep(poll_interval)

    logger.info("监控已停止")


def _run_once(config: dict, client: SeaTableClient, machine: str):
    # tmux 采集
    prefixes = config.get("tmux", {}).get("session_prefixes", [])
    if prefixes:
        tasks = collect_by_prefixes(prefixes, machine)
        active_sessions: dict[str, set] = {}
        for t in tasks:
            active_sessions.setdefault(t.session_id, set()).add(t.name)
            client.upsert_task(t)
        # 清理已消失的 session 行
        for session_id, active_names in active_sessions.items():
            client.remove_stale_tasks("tmux", session_id, machine, active_names)

    # Claude Code 采集
    claude_conf = config.get("claude", {})
    if claude_conf.get("enabled", True):
        lookback = claude_conf.get("lookback_hours", 5)
        todos = collect_todos(claude_conf.get("todos_dir", "~/.claude/todos"), machine, lookback)
        task_list = collect_tasks(claude_conf.get("tasks_dir", "~/.claude/tasks"), machine, lookback)
        for t in todos + task_list:
            client.upsert_task(t)


if __name__ == "__main__":
    main()
