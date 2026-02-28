from dataclasses import dataclass


STATUS_MAP = {
    "pending": "待办",
    "in_progress": "进行中",
    "completed": "已完成",
}


@dataclass(frozen=True)
class TaskInfo:
    name: str               # 任务描述
    status: str             # "待办" / "进行中" / "已完成" / "未知"
    source: str             # "tmux" / "claude-code"
    session_id: str         # 来源会话标识
    latest_output: str      # 最新输出/进度描述
    parent_name: str | None # 父任务名（用于自关联 link）
    machine: str            # hostname
