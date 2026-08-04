"""Pydantic Settings — 数据库 (SQLite本地开发 / MySQL火山引擎RDS)"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_root: Path = Path(__file__).parent.parent.resolve()

    # ── 数据库类型: sqlite (本地零配置) / mysql (云端) ──
    db_type: str = "sqlite"

    # MySQL 配置
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_db: str = "agent_eval"

    # SQLite 配置
    sqlite_path: str = "data/agent_eval.db"

    @property
    def database_url(self) -> str:
        if self.db_type == "mysql":
            return (f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
                    f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4")
        return f"sqlite+aiosqlite:///{self.sqlite_path}"

    @property
    def sync_database_url(self) -> str:
        if self.db_type == "mysql":
            return (f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
                    f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4")
        return f"sqlite:///{self.sqlite_path}"

    # ── LLM ──
    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com/v1"

    # ── Auth (必须通过环境变量设置) ──
    admin_username: str = ""
    admin_password: str = ""
    secret_key: str = ""

    # ── 生产环境校验 ──
    def check_production_ready(self) -> None:
        """在生产模式下验证关键配置是否已设置"""
        if self.db_type == "mysql":
            missing = []
            if not self.admin_username:
                missing.append("ADMIN_USERNAME")
            if not self.admin_password:
                missing.append("ADMIN_PASSWORD")
            if not self.secret_key:
                missing.append("SECRET_KEY")
            if not self.openai_api_key:
                missing.append("OPENAI_API_KEY")
            if missing:
                import warnings
                warnings.warn(
                    f"生产环境缺少必要环境变量: {', '.join(missing)}。"
                    f"请通过 .env 文件或环境变量设置。"
                )


settings = Settings()
