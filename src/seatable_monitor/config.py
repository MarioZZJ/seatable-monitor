import os
import tomllib
from pathlib import Path


def load_config() -> dict:
    """加载配置，优先级：环境变量 > config.toml > 默认值"""
    config_path = os.environ.get("SEATABLE_MONITOR_CONFIG")
    if not config_path:
        local = Path("config.toml")
        if local.exists():
            config_path = str(local)
        else:
            config_path = str(Path.home() / ".config" / "seatable-monitor" / "config.toml")

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    # 环境变量覆盖 token
    env_token = os.environ.get("SEATABLE_API_TOKEN")
    if env_token:
        config.setdefault("seatable", {})["api_token"] = env_token

    return config
