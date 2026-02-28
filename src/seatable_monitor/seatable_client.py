import time
import logging
from datetime import datetime
from seatable_api import Base
from seatable_api.constants import ColumnTypes
from .models import TaskInfo

logger = logging.getLogger(__name__)

# 列配置（首列"任务名"由建表时自动创建）
COLUMNS = [
    ("状态", ColumnTypes.SINGLE_SELECT),
    ("来源", ColumnTypes.SINGLE_SELECT),
    ("会话ID", ColumnTypes.TEXT),
    ("最新输出", ColumnTypes.LONG_TEXT),
    ("更新时间", ColumnTypes.DATE),
    ("机器", ColumnTypes.TEXT),
    ("父任务", ColumnTypes.LINK),  # 自关联，特殊处理
]

STATUS_OPTIONS = [
    {"name": "待办",   "color": "#FF8000", "textColor": "#FFFFFF"},
    {"name": "进行中", "color": "#59CB74", "textColor": "#FFFFFF"},
    {"name": "已完成", "color": "#9860E5", "textColor": "#FFFFFF"},
    {"name": "未知",   "color": "#CCCCCC", "textColor": "#333333"},
]

SOURCE_OPTIONS = [
    {"name": "tmux",        "color": "#4A90D9", "textColor": "#FFFFFF"},
    {"name": "claude-code", "color": "#5BC8C0", "textColor": "#FFFFFF"},
]


def _esc(s: str) -> str:
    """转义 SQL 单引号"""
    return s.replace("'", "''")


class SeaTableClient:
    def __init__(self, server_url: str, api_token: str, table_name: str):
        self.server_url = server_url
        self.api_token = api_token
        self.table_name = table_name
        self.base = None
        self._auth_time = 0
        self._link_column_id = None  # 父任务 link column id

    def init(self):
        """认证 + 确保表/列/选项存在"""
        self.base = Base(self.api_token, self.server_url)
        self.base.auth()
        self._auth_time = time.time()
        self._ensure_table()
        self._ensure_columns()
        self._ensure_options()
        logger.info("SeaTable 初始化完成：表=%s", self.table_name)

    def _ensure_table(self):
        metadata = self.base.get_metadata()
        if not any(t["name"] == self.table_name for t in metadata["tables"]):
            self.base.add_table(self.table_name)
            logger.info("已创建表：%s", self.table_name)

    def _ensure_columns(self):
        metadata = self.base.get_metadata()
        existing_cols = {
            c["name"]
            for t in metadata["tables"]
            if t["name"] == self.table_name
            for c in t.get("columns", [])
        }

        for col_name, col_type in COLUMNS:
            if col_name in existing_cols:
                continue
            if col_type == ColumnTypes.LINK:
                # 自关联：父任务指向同表
                self.base.insert_column(
                    self.table_name, col_name, col_type,
                    column_data={"table": self.table_name, "other_table": self.table_name}
                )
            else:
                self.base.insert_column(self.table_name, col_name, col_type)
            logger.info("已添加列：%s (%s)", col_name, col_type)

        # 缓存 link column id
        self._refresh_link_column_id()

    def _refresh_link_column_id(self):
        metadata = self.base.get_metadata()
        for t in metadata["tables"]:
            if t["name"] == self.table_name:
                for c in t.get("columns", []):
                    if c["name"] == "父任务":
                        self._link_column_id = c.get("data", {}).get("link_id")
                        return

    def _ensure_options(self):
        # 设置状态选项
        try:
            self.base.add_column_options(self.table_name, "状态", STATUS_OPTIONS)
            self.base.add_column_options(self.table_name, "来源", SOURCE_OPTIONS)
        except Exception:
            pass  # 选项已存在时可能报错，忽略

    def upsert_task(self, task: TaskInfo):
        """按 (任务名, 会话ID, 机器) 去重 upsert"""
        sql = (
            f"SELECT _id FROM `{self.table_name}` "
            f"WHERE `任务名`='{_esc(task.name)}' "
            f"AND `会话ID`='{_esc(task.session_id)}' "
            f"AND `机器`='{_esc(task.machine)}' LIMIT 1"
        )
        rows = self.base.query(sql)
        row_data = {
            "任务名": task.name,
            "状态": task.status,
            "来源": task.source,
            "会话ID": task.session_id,
            "最新输出": task.latest_output,
            "更新时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "机器": task.machine,
        }
        if rows:
            row_id = rows[0]["_id"]
            self.base.update_row(self.table_name, row_id, row_data)
        else:
            self.base.append_row(self.table_name, row_data)
            # 重新查询拿到新行 id
            rows = self.base.query(sql)
            if not rows:
                return
            row_id = rows[0]["_id"]

        # 处理父任务 link
        if task.parent_name and self._link_column_id:
            self._link_parent(row_id, task)

    def _link_parent(self, child_row_id: str, task: TaskInfo):
        """建立子任务与父任务的 link 关联"""
        parent_sql = (
            f"SELECT _id FROM `{self.table_name}` "
            f"WHERE `任务名`='{_esc(task.parent_name)}' "
            f"AND `会话ID`='{_esc(task.session_id)}' "
            f"AND `机器`='{_esc(task.machine)}' LIMIT 1"
        )
        parent_rows = self.base.query(parent_sql)
        if not parent_rows:
            return
        parent_row_id = parent_rows[0]["_id"]
        try:
            self.base.add_link(
                self._link_column_id,
                self.table_name, self.table_name,
                child_row_id, parent_row_id
            )
        except Exception:
            pass  # link 已存在时忽略

    def remove_stale_tasks(self, source: str, session_id: str, machine: str, active_names: set):
        """删除该机器/会话下已不存在的旧任务行"""
        sql = (
            f"SELECT _id, `任务名` FROM `{self.table_name}` "
            f"WHERE `来源`='{source}' AND `会话ID`='{_esc(session_id)}' "
            f"AND `机器`='{_esc(machine)}'"
        )
        for row in self.base.query(sql):
            if row["任务名"] not in active_names:
                self.base.delete_row(self.table_name, row["_id"])

    def refresh_auth_if_needed(self):
        """base_token 有效期 3 天，超 2 天自动刷新"""
        if time.time() - self._auth_time > 2 * 86400:
            self.base.auth()
            self._auth_time = time.time()
            self._refresh_link_column_id()
            logger.info("SeaTable token 已刷新")
