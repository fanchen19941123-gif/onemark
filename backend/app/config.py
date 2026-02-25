from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/onemark"

    # Auth
    secret_key: str = "onemark-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    refresh_token_expire_minutes: int = 60 * 24 * 30
    sms_code_expire_seconds: int = 300
    sms_send_cooldown_seconds: int = 60
    sms_code_max_attempts: int = 5
    sms_daily_send_limit: int = 20
    sms_debug_return_code: bool = True

    # App
    app_name: str = "OneMark"
    app_env: str = "dev"

    # Sync
    default_sync_platforms: list[str] = Field(
        default_factory=lambda: ["xiaohongshu", "douyin", "bilibili"]
    )
    sync_daily_hour: int = 3
    sync_daily_minute: int = 0
    sync_timezone: str = "Asia/Shanghai"

    # AI
    llm_api_key: str = ""
    llm_base_url: str = "https://api.moonshot.cn/v1"
    llm_model: str = "moonshot-v1-8k"
    semantic_search_candidates: int = 160
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Alerts
    feishu_webhook_url: str = ""
    alert_dedupe_hours: int = 6

    # Feishu Login (OAuth)
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_redirect_uri: str = ""
    feishu_oauth_scope: str = "contact:user.base:readonly"
    feishu_session_expire_seconds: int = 600

    # Snapshot
    snapshot_root: str = str(PROJECT_ROOT / "output" / "snapshots")
    single_user_snapshot_namespace: str = "default"

    # Scraper scripts
    xhs_script_path: str = str(
        Path.home()
        / ".codex"
        / "skills"
        / "xiaohongshu-favorites-export"
        / "scripts"
        / "export_xhs_favorites.sh"
    )
    xhs_max_steps: int = 2400
    xhs_sleep_ms: int = 700
    xhs_hard_retries: int = 2
    xhs_favorites_url: str = ""
    douyin_script_path: str = str(PROJECT_ROOT / "scripts" / "export_douyin_favorites.sh")
    douyin_hard_retries: int = 3
    douyin_favorites_url: str = ""
    bilibili_script_path: str = ""

    # Single-user MVP helper
    auto_create_default_user: bool = False
    default_user_email: str = "demo@onemark.local"
    default_user_password: str = "ChangeMe123!"

    @property
    def effective_llm_api_key(self) -> str:
        return self.llm_api_key or self.deepseek_api_key

    @property
    def effective_llm_base_url(self) -> str:
        return self.llm_base_url or self.deepseek_base_url

    @property
    def effective_llm_model(self) -> str:
        return self.llm_model or self.deepseek_model

    model_config = {
        "env_file": str(BACKEND_ROOT / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()
