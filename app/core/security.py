"""认证：Bearer Token 解析。

小程序 utils/request.js 对所有请求附带 Authorization: Bearer <token>。
受保护接口用 @login_required 装饰，未登录抛 ApiError(401)，由全局错误处理器统一返回。
"""
from functools import wraps

from flask import current_app, g, request

from ..models import AdminToken, AdminUser, ApiToken, User, db
from .constants import now_ms
from .response import ApiError


def _slide(record, ttl_ms: int) -> bool:
    """滑动过期：age>TTL 判失效返回 False；age>TTL/2 则续期（刷新 created_at）返回 True。

    只在超过半程时才写库续期，控制写放大；未过半程不写。
    """
    age = now_ms() - record.created_at
    if age > ttl_ms:
        return False
    if age > ttl_ms // 2:
        record.created_at = now_ms()
        db.session.commit()
    return True


def _client_ttl_ms() -> int:
    return int(current_app.config.get("TOKEN_TTL_CLIENT_DAYS", 30)) * 86400 * 1000


def _admin_ttl_ms() -> int:
    return int(current_app.config.get("TOKEN_TTL_ADMIN_HOURS", 12)) * 3600 * 1000


def _resolve_token() -> User | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):].strip()
    if not token:
        return None
    record = ApiToken.query.filter_by(token=token).first()
    if record is None:
        return None
    if not _slide(record, _client_ttl_ms()):
        return None  # 超过 TTL 未活跃，视为未登录
    return User.query.get(record.user_id)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _resolve_token()
        if user is None:
            raise ApiError(401, "请先登录")
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def _resolve_admin_token() -> AdminUser | None:
    """解析管理端 Bearer Token（与用户 token 体系完全隔离，走 admin_tokens 表）。"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):].strip()
    if not token:
        return None
    record = AdminToken.query.filter_by(token=token).first()
    if record is None:
        return None
    if not _slide(record, _admin_ttl_ms()):
        return None  # 超过 TTL 未活跃，视为未登录
    admin = AdminUser.query.get(record.admin_id)
    if admin is None or not admin.is_active:
        return None
    return admin


def admin_required(fn):
    """管理端鉴权：仅活跃管理员可用，否则 401。不复用小程序用户的 @login_required。"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        admin = _resolve_admin_token()
        if admin is None:
            raise ApiError(401, "管理员未登录或已失效")
        g.current_admin = admin
        return fn(*args, **kwargs)

    return wrapper


def super_required(fn):
    """超管鉴权：先过 admin_required，再校验 is_super；非超管返回 403。

    用于管理员账号的写操作（增删改），普通管理员无权。
    """
    @wraps(fn)
    @admin_required
    def wrapper(*args, **kwargs):
        if not g.current_admin.is_super:
            raise ApiError(403, "仅超级管理员可操作")
        return fn(*args, **kwargs)

    return wrapper
