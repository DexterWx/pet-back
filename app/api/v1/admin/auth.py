"""管理端认证：账号密码登录 / 登出 / 当前管理员。

与小程序用户体系完全隔离：token 存 admin_tokens 表，鉴权走 @admin_required。
登录限流：同一账号在窗口内连续失败达上限则临时锁定（内存计数，单 worker 足够）。
"""
from flask import Blueprint, current_app, g, request

from ....core.constants import gen_token, now_ms
from ....core.response import ApiError, ok
from ....core.security import admin_required
from ....models import AdminToken, AdminUser, db
from ....services import audit, catalog_service

bp = Blueprint("admin_auth", __name__, url_prefix="/auth")

# 登录失败记录：username -> [失败时间戳(ms)]，窗口外的会被惰性清理
_login_fails: dict[str, list[int]] = {}


def _assert_not_locked(username: str) -> None:
    now = now_ms()
    window = int(current_app.config.get("ADMIN_LOGIN_WINDOW_MIN", 15)) * 60 * 1000
    max_fails = int(current_app.config.get("ADMIN_LOGIN_MAX_FAILS", 10))
    hits = [t for t in _login_fails.get(username, []) if now - t < window]
    _login_fails[username] = hits
    if len(hits) >= max_fails:
        raise ApiError(429, f"登录失败次数过多，请 {window // 60000} 分钟后再试")


def _record_fail(username: str) -> None:
    _login_fails.setdefault(username, []).append(now_ms())


def _clear_fails(username: str) -> None:
    _login_fails.pop(username, None)


def _admin_payload(a: AdminUser) -> dict:
    return {
        "id": a.id,
        "username": a.username,
        "displayName": a.display_name,
        "isSuper": bool(a.is_super),
    }


@bp.post("/login")
def login():
    """账号密码登录：校验通过则轮换 token（删旧发新）并返回 {token, admin}。含失败限流。"""
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or not password:
        raise ApiError(400, "请输入账号和密码")

    _assert_not_locked(username)

    admin = AdminUser.query.filter_by(username=username).first()
    if admin is None or not admin.verify_password(password):
        _record_fail(username)
        raise ApiError(400, "账号或密码错误")
    if not admin.is_active:
        _record_fail(username)
        raise ApiError(400, "该账号已被禁用")
    _clear_fails(username)

    AdminToken.query.filter_by(admin_id=admin.id).delete()
    token = gen_token()
    db.session.add(AdminToken(admin_id=admin.id, token=token, created_at=now_ms()))
    admin.last_login_at = now_ms()
    db.session.commit()
    audit.log("auth.login", admin.id, admin.username, admin=admin)

    return ok({"token": token, "admin": _admin_payload(admin)})


@bp.post("/logout")
@admin_required
def logout():
    """登出：清除当前请求使用的那个 token。"""
    auth = request.headers.get("Authorization", "")
    token = auth[len("Bearer "):].strip()
    AdminToken.query.filter_by(token=token).delete()
    db.session.commit()
    return ok(None)


@bp.get("/me")
@admin_required
def me():
    return ok(_admin_payload(g.current_admin))


@bp.post("/change-password")
@admin_required
def change_password():
    """管理员改自己密码：{oldPassword,newPassword}；成功后删其全部 token 强制重新登录。"""
    body = request.get_json(silent=True) or {}
    catalog_service.change_password(
        g.current_admin,
        str(body.get("oldPassword", "")),
        str(body.get("newPassword", "")),
    )
    audit.log("auth.change_password", g.current_admin.id, g.current_admin.username)
    return ok(None)
