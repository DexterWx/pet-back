"""认证：Bearer Token 解析。

小程序 utils/request.js 对所有请求附带 Authorization: Bearer <token>。
受保护接口用 @login_required 装饰，未登录抛 ApiError(401)，由全局错误处理器统一返回。
"""
from functools import wraps

from flask import g, request

from ..models import ApiToken, User
from .response import ApiError


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
