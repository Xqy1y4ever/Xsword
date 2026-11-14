"""配置：从环境变量 / 项目根 .env 读取。"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 3000
    db_path: str = "./data/app.db"
    timezone: str = "Asia/Shanghai"
    session_secret: str = ""
    admin_password_hash: str = ""
    session_ttl_days: int = 30
    cookie_secure: bool = False
    dist_dir: str = "./dist"

    # 以下 LLM_* 仅用于首次启动时把旧 .env 配置导入数据库（见 llm_config.bootstrap_from_env）；
    # 运行时的大模型配置以数据库 llm_config 表为准，在设置页维护。
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_batch_size: int = 20
    prompt_version: str = "v1"


def get_settings(**overrides) -> Settings:
    """测试时用 overrides 覆盖静态配置。"""
    if overrides:
        return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]
    return Settings()
