import json
import time
import logging
from pathlib import Path
from ..models import TaskInfo, STATUS_MAP

logger = logging.getLogger(__name__)


def collect_todos(todos_dir: str, machine: str, lookback_hours: float = 5) -> list[TaskInfo]:
    """从 ~/.claude/todos/*.json 采集 TodoWrite 数据（最近 N 小时）"""
    results = []
    todos_path = Path(todos_dir).expanduser()
    if not todos_path.exists():
        return results

    cutoff = time.time() - lookback_hours * 3600
    for f in todos_path.glob("*.json"):
        if f.stat().st_mtime < cutoff:
            continue
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        if not data:
            continue

        # 文件名格式：{sessionId}-agent-{agentId}.json
        session_id = f.stem.split("-agent-")[0]
        for item in data:
            results.append(TaskInfo(
                name=item.get("content", "未知任务")[:200],
                status=STATUS_MAP.get(item.get("status", ""), "未知"),
                source="claude-code",
                session_id=session_id,
                latest_output=item.get("activeForm", ""),
                parent_name=None,
                machine=machine,
            ))
    return results


def collect_tasks(tasks_dir: str, machine: str, lookback_hours: float = 5) -> list[TaskInfo]:
    """从 ~/.claude/tasks/*/*.json 采集 TaskCreate/TaskUpdate 数据（最近 N 小时）"""
    results = []
    tasks_path = Path(tasks_dir).expanduser()
    if not tasks_path.exists():
        return results

    cutoff = time.time() - lookback_hours * 3600
    for team_dir in tasks_path.iterdir():
        if not team_dir.is_dir():
            continue
        if team_dir.stat().st_mtime < cutoff:
            continue

        # 加载团队所有任务，建立 id→task 映射
        all_tasks: dict[str, dict] = {}
        for tf in team_dir.glob("*.json"):
            if tf.stem.startswith(".") or not tf.stem.isdigit():
                continue
            try:
                task_data = json.loads(tf.read_text())
                all_tasks[task_data["id"]] = task_data
            except Exception:
                continue

        for task in all_tasks.values():
            # 父任务：取 blockedBy 第一个
            parent_name = None
            blocked_by = task.get("blockedBy", [])
            if blocked_by and blocked_by[0] in all_tasks:
                parent_name = all_tasks[blocked_by[0]]["subject"]

            output = task.get("activeForm") or task.get("description", "")
            results.append(TaskInfo(
                name=task["subject"][:200],
                status=STATUS_MAP.get(task.get("status", ""), "未知"),
                source="claude-code",
                session_id=team_dir.name,
                latest_output=output[:500],
                parent_name=parent_name,
                machine=machine,
            ))
    return results
