import secrets
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "ccreward-cn"
    APP_VERSION: str = "0.2.0"
    DEBUG: bool = False

    # Database: SQLite for local dev, PostgreSQL for production
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/ccreward.db"

    CRAWLER_ENABLED: bool = True
    CRAWLER_INTERVAL_HOURS: int = 6
    CRAWLER_USER_AGENT: str = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )

    CORS_ORIGINS: list[str] = ["*"]

    # 生产环境强制认证，开发环境可选（设为 false 恢复旧行为：无 token 自动创建匿名用户）
    API_AUTH_ENFORCE: bool = True

    JWT_SECRET: str = "ccreward-cn-dev-secret-change-in-production"

    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""
    WECHAT_ENABLED: bool = False

    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_ENABLED: bool = False

    # PushPlus wechat push (https://www.pushplus.plus/)
    PUSHPLUS_TOKEN: str = ""
    PUSHPLUS_ENABLED: bool = False

    # ServerChan wechat push (https://sct.ftqq.com/)
    SERVERCHAN_KEY: str = ""
    SERVERCHAN_ENABLED: bool = False

    # SMTP email notification
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_TO: str = ""
    SMTP_ENABLED: bool = False

    NOTIFY_HOUR: int = 9
    NOTIFY_MINUTE: int = 0

    BANK_OFFER_INSPECTION_DAY: int = 1  # 周一巡检 (0=周日, 1=周一...6=周六)
    BANK_OFFER_INSPECTION_HOUR: int = 9
    BANK_OFFER_INSPECTION_MINUTE: int = 0

    BENEFIT_INSPECTION_DAY: int = 6  # 周六巡检 (0=周日, 1=周一...6=周六)
    BENEFIT_INSPECTION_HOUR: int = 9
    BENEFIT_INSPECTION_MINUTE: int = 0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

if not settings.DEBUG and settings.JWT_SECRET == "ccreward-cn-dev-secret-change-in-production":
    settings.JWT_SECRET = secrets.token_urlsafe(32)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
