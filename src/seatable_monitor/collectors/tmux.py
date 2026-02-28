import subprocess
import logging
from ..models import TaskInfo

logger = logging.getLogger(__name__)


def list_sessions() -> list[str]:
    """列出所有 tmux session 名称"""
    result = subprocess.run(
        ["tmux", "ls", "-F", "#{session_name}"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    return [l.strip() for l in result.stdout.splitlines() if l.strip()]


def collect_by_prefixes(prefixes: list[str], machine: str) -> list[TaskInfo]:
    """采集名称匹配任意前缀的所有 tmux session"""
    all_sessions = list_sessions()
    matched = [s for s in all_sessions if any(s.startswith(p) for p in prefixes)]

    results = []
    for session_name in matched:
        task = _collect_one(session_name, machine)
        if task:
            results.append(task)
    return results


def _collect_one(session_name: str, machine: str) -> TaskInfo | None:
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", session_name],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.warning("无法采集 tmux session: %s", session_name)
        return None

    lines = [l for l in result.stdout.splitlines() if l.strip()]
    last_line = lines[-1] if lines else "(空)"

    return TaskInfo(
        name=f"tmux:{session_name}",
        status="进行中",
        source="tmux",
        session_id=session_name,
        latest_output=last_line[:500],  # 最多500字符
        parent_name=None,
        machine=machine,
    )
