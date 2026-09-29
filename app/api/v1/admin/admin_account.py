"""管理端账号管理接口：列表 / 创建 / 更新 / 删除（多账号）。

- 列表：任何管理员可看（便于协作），但写操作仅超管（@super_required）。
- 保护规则在 catalog_service：不能删/禁自己，不能删/禁/撤最后一个启用超管。
"""
from flask import Blueprint, g, request

from ....core.response import ok
from ....core.security import admin_required, super_required
from ....services import audit, catalog_service, serializers

bp = Blueprint("admin_account", __name__, url_prefix="/admins")


@bp.get("")
@admin_required
def list_admins():
    return ok(catalog_service.list_admins())


@bp.post("")
@super_required
def create_admin():
    body = request.get_json(silent=True) or {}
    admin = catalog_service.create_admin(body)
    audit.log("admin.create", admin.id, admin.username)
    return ok(serializers.admin_account(admin))


@bp.put("/<admin_id>")
@super_required
def update_admin(admin_id: str):
    """改资料/密码/启用禁用/超管；operator 为当前登录管理员（用于自我保护校验）。"""
    body = request.get_json(silent=True) or {}
    admin = catalog_service.update_admin(admin_id, body, g.current_admin)
    audit.log("admin.update", admin.id, admin.username)
    return ok(serializers.admin_account(admin))


@bp.delete("/<admin_id>")
@super_required
def delete_admin(admin_id: str):
    catalog_service.delete_admin(admin_id, g.current_admin)
    audit.log("admin.delete", admin_id)
    return ok(None)
