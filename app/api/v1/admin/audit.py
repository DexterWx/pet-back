"""管理端操作溯源查询（仅超管）：分页列出 admin_audit_logs。"""
from flask import Blueprint, request

from ....core.response import ok
from ....core.security import super_required
from ....models import AdminAuditLog

bp = Blueprint("admin_audit", __name__, url_prefix="/audit-logs")


def _log_payload(l: AdminAuditLog) -> dict:
    return {
        "id": l.id,
        "adminId": l.admin_id,
        "username": l.username,
        "action": l.action,
        "target": l.target,
        "detail": l.detail,
        "ip": l.ip,
        "createdAt": l.created_at,
    }


@bp.get("")
@super_required
def list_logs():
    """?page=&pageSize=&action= 分页倒序。仅超管可查。"""
    page = max(int(request.args.get("page", 1) or 1), 1)
    page_size = max(int(request.args.get("pageSize", 20) or 20), 1)
    action = request.args.get("action", "") or ""
    query = AdminAuditLog.query
    if action:
        query = query.filter_by(action=action)
    query = query.order_by(AdminAuditLog.created_at.desc())
    total = query.count()
    rows = query.limit(page_size).offset((page - 1) * page_size).all()
    return ok({"list": [_log_payload(r) for r in rows], "total": total, "page": page, "pageSize": page_size})
