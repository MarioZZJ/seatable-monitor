import json
import time
import logging
import os
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


def _decode_project_name(encoded: str) -> str:
    """将编码的项目路径解码为可读名称。
    如 -Users-mariozzj-Documents-project-foo → project/foo
    """
    # 去掉 home 目录前缀部分，只保留有意义的路径
    parts = encoded.split("-")
    # 找 Documents/project 等有意义的段
    try:
        # 跳过 Users/{username} 部分
        idx = 0
        while idx < len(parts):
            if parts[idx] in ("Users", "home", ""):
                idx += 1
            elif idx > 0 and parts[idx - 1] in ("Users", "home"):
                idx += 1  # 跳过用户名
                break
            else:
                break
        meaningful = parts[idx:]
        if meaningful:
            return "/".join(meaningful)
    except Exception:
        pass
    return encoded


def _tail_lines(filepath: Path, n: int = 20) -> list[str]:
    """高效读取文件最后 n 行（不读全文件）"""
    try:
        size = filepath.stat().st_size
        if size == 0:
            return []
        # 读取尾部 chunk（每行 JSONL 平均 ~2KB，读 n*4KB 足够）
        chunk_size = min(size, n * 4096)
        with open(filepath, "rb") as f:
            f.seek(max(0, size - chunk_size))
            data = f.read().decode("utf-8", errors="replace")
        lines = data.splitlines()
        return lines[-n:]
    except Exception:
        return []


def _extract_session_state(lines: list[str]) -> dict:
    """从 JSONL 最后几行提取会话状态"""
    last_type = "unknown"
    last_tool = ""
    last_text = ""
    cwd = ""
    git_branch = ""
    session_id = ""
    last_ts = ""

    for raw_line in reversed(lines):
        if not raw_line.strip():
            continue
        try:
            entry = json.loads(raw_line)
        except Exception:
            continue

        entry_type = entry.get("type", "")
        if not session_id:
            session_id = entry.get("sessionId", "")
        if not cwd:
            cwd = entry.get("cwd", "")
        if not git_branch:
            git_branch = entry.get("gitBranch", "")
        if not last_ts:
            last_ts = entry.get("timestamp", "")

        if last_type == "unknown":
            last_type = entry_type

        # 提取最新活动描述
        if not last_tool and not last_text:
            data = entry.get("data", {})
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    try:
                        data = eval(data)
                    except Exception:
                        data = {}

            if isinstance(data, dict):
                msg = data.get("message", {})
                if isinstance(msg, dict):
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for c in reversed(content):
                            if not isinstance(c, dict):
                                continue
                            if c.get("type") == "tool_use" and not last_tool:
                                last_tool = c.get("name", "")
                            elif c.get("type") == "text" and not last_text:
                                last_text = c.get("text", "")[:200]

    return {
        "last_type": last_type,
        "last_tool": last_tool,
        "last_text": last_text,
        "cwd": cwd,
        "git_branch": git_branch,
        "session_id": session_id,
        "last_ts": last_ts,
    }


def collect_sessions(
    projects_dir: str, machine: str, lookback_hours: float = 5
) -> list[TaskInfo]:
    """从 ~/.claude/projects/*/*.jsonl 采集活跃的 Claude Code 会话"""
    results = []
    proj_path = Path(projects_dir).expanduser()
    if not proj_path.exists():
        return results

    cutoff = time.time() - lookback_hours * 3600

    for proj_dir in proj_path.iterdir():
        if not proj_dir.is_dir():
            continue

        project_name = _decode_project_name(proj_dir.name)

        for jsonl_file in proj_dir.glob("*.jsonl"):
            try:
                mtime = jsonl_file.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                continue

            lines = _tail_lines(jsonl_file, 30)
            if not lines:
                continue

            state = _extract_session_state(lines)
            session_id = state["session_id"] or jsonl_file.stem

            # 用 cwd 作为项目名（比目录名解码更准确）
            display_name = project_name
            if state["cwd"]:
                # 取 cwd 最后两级目录作为简称
                cwd_parts = Path(state["cwd"]).parts
                display_name = "/".join(cwd_parts[-2:]) if len(cwd_parts) >= 2 else cwd_parts[-1]

            # 判断状态
            age_seconds = time.time() - mtime
            if age_seconds > 300:
                status = "已完成"  # 5 分钟无更新视为结束
            else:
                status = "进行中"

            # 构造最新输出描述
            output_parts = []
            if state["git_branch"]:
                output_parts.append(f"[{state['git_branch']}]")
            if state["last_tool"]:
                output_parts.append(f"→ {state['last_tool']}")
            if state["last_text"]:
                output_parts.append(state["last_text"][:150])
            elif state["last_type"] == "progress":
                output_parts.append("(执行中...)")

            latest_output = " ".join(output_parts) or "(无输出)"

            results.append(TaskInfo(
                name=f"session:{display_name}",
                status=status,
                source="claude-session",
                session_id=session_id[:36],
                latest_output=latest_output[:500],
                parent_name=None,
                machine=machine,
            ))

    return results
