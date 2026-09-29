"""管理端操作溯源埋点 helper。

用法：在管理端写操作**成功提交后**调用 `audit.log("product.create", target=id)`。
不记敏感明文；失败的操作不记（只记成功变更），登录失败由限流模块自行计数不入库。
"""
from flask import g, request

from ..core.constants import now_ms
from ..models import AdminAuditLog, db


def log(action: str, target: str = "", detail: str = "", admin=None) -> None:
    """写一条审计日志。admin 缺省取 g.current_admin（登录等场景可显式传入）。"""
    admin = admin or getattr(g, "current_admin", None)
    if admin is None:
        return
    db.session.add(AdminAuditLog(
        admin_id=admin.id,
        username=getattr(admin, "username", "") or "",
        action=str(action)[:64],
        target=str(target)[:128],
        detail=str(detail)[:512],
        ip=(request.remote_addr or "")[:64],
        created_at=now_ms(),
    ))
    db.session.commit()
