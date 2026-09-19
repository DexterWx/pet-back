"""全局配置：默认值面向本地开发，敏感项从环境变量 / .env 读取。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（pet-back/）
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 加载 .env（不存在时静默跳过，.env.example 为模板）
load_dotenv(BASE_DIR / ".env")


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

    # SQLite 数据库文件放在 instance/ 下（已 gitignore）
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///" + str(BASE_DIR / "instance" / "petstore.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 微信登录：true=本地 Mock（固定 openid 模拟单一身份，无需 appid/secret）
    WECHAT_MOCK_LOGIN = _env_bool("WECHAT_MOCK_LOGIN", True)
    WECHAT_APPID = os.getenv("WECHAT_APPID", "")
    WECHAT_SECRET = os.getenv("WECHAT_SECRET", "")
