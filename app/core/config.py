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

    # 上传（头像等）：本地磁盘存储；接 OSS 时新增 provider 实现并由此切换
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(BASE_DIR / "instance" / "uploads"))
    # 对外可访问的资源基址（回调/小程序展示需绝对 URL）；未配置则取请求 host
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip()
    MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(2 * 1024 * 1024)))  # 2MB

    # 图床 provider：local=本地磁盘；oss=阿里云 OSS
    IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "local").strip().lower()
    # 阿里云 OSS（IMAGE_PROVIDER=oss 时必填）
    OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "").strip()          # 如 oss-cn-hangzhou.aliyuncs.com
    OSS_BUCKET = os.getenv("OSS_BUCKET", "").strip()
    OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "").strip()
    OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "").strip()
    # 可选：绑定自定义域名后填它（如 https://img.yourdomain.com）；留空则用 OSS 默认 https 域名
    OSS_PUBLIC_BASE = os.getenv("OSS_PUBLIC_BASE", "").strip()

    # 待付款订单超时自动关闭（分钟）；惰性判定，读取时过期即置 CLOSED
    ORDER_PENDING_PAY_TTL_MIN = int(os.getenv("ORDER_PENDING_PAY_TTL_MIN", "30"))

    # 发货后自动确认收货的天数（也是已发货订单可申请退款的窗口）；惰性判定，不引入定时任务。
    # 未发货订单不受此限（随时可退）；超过此天数订单自动转 COMPLETED，用户不能再自助退款。
    ORDER_AUTO_COMPLETE_DAYS = int(os.getenv("ORDER_AUTO_COMPLETE_DAYS", "7"))

    # Token 滑动过期：超过 TTL 未活跃则失效；活跃（超过 TTL/2 时）自动续期。
    TOKEN_TTL_CLIENT_DAYS = int(os.getenv("TOKEN_TTL_CLIENT_DAYS", "30"))
    TOKEN_TTL_ADMIN_HOURS = int(os.getenv("TOKEN_TTL_ADMIN_HOURS", "12"))

    # 管理端登录限流：同一账号在窗口内连续失败达上限则临时锁定
    ADMIN_LOGIN_MAX_FAILS = int(os.getenv("ADMIN_LOGIN_MAX_FAILS", "10"))
    ADMIN_LOGIN_WINDOW_MIN = int(os.getenv("ADMIN_LOGIN_WINDOW_MIN", "15"))

    # 企业微信群机器人通知（新订单已支付 / 用户退款申请）
    # WECOM_WEBHOOK_URL 为空则不推；WECOM_NOTIFY_ENABLED=false 可整体关闭（本地/冒烟测试用，避免骚扰真实群）
    WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL", "").strip()
    WECOM_NOTIFY_ENABLED = _env_bool("WECOM_NOTIFY_ENABLED", True)

    # 支付：mock=本地模拟（下单支付即时成功，仅开发）；wechat=微信商户支付 v3。**生产必须设为 wechat**
    PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "mock").strip().lower()
    # 微信支付 v3 凭证（PAYMENT_PROVIDER=wechat 时必填）；appid 复用 WECHAT_APPID
    WXPAY_MCHID = os.getenv("WXPAY_MCHID", "").strip()
    WXPAY_APIV3_KEY = os.getenv("WXPAY_APIV3_KEY", "").strip()
    WXPAY_CERT_SERIAL_NO = os.getenv("WXPAY_CERT_SERIAL_NO", "").strip()
    WXPAY_PRIVATE_KEY_PATH = os.getenv("WXPAY_PRIVATE_KEY_PATH", "").strip()  # apiclient_key.pem
    WXPAY_NOTIFY_URL = os.getenv("WXPAY_NOTIFY_URL", "").strip()
    WXPAY_CERT_DIR = os.getenv("WXPAY_CERT_DIR", "").strip()  # 平台证书目录（传统模式，留空则自动下载到 instance/wxcert）
    # 微信支付公钥模式（2024+ 新商户可选，填了则优先于 cert_dir）
    WXPAY_PUBLIC_KEY_PATH = os.getenv("WXPAY_PUBLIC_KEY_PATH", "").strip()
    WXPAY_PUBLIC_KEY_ID = os.getenv("WXPAY_PUBLIC_KEY_ID", "").strip()
