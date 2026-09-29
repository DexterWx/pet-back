"""管理端分类接口（全部需管理员登录）：列表 / 创建 / 更新 / 删除。

删除前校验无商品引用（catalog_service 内）；接口层只做参数解析与鉴权。
"""
from flask import Blueprint, request

from ....core.response import ok
from ....core.security import admin_required
from ....services import audit, catalog_service

bp = Blueprint("admin_category", __name__, url_prefix="/categories")


@bp.get("")
@admin_required
def list_categories():
    """分类列表（含每类商品数），按 sort 升序。"""
    return ok(catalog_service.list_categories())


@bp.post("")
@admin_required
def create_category():
    body = request.get_json(silent=True) or {}
    category = catalog_service.create_category(body)
    audit.log("category.create", category.id, category.name)
    return ok({"id": category.id, "name": category.name, "sort": category.sort, "productCount": 0})


@bp.put("/<category_id>")
@admin_required
def update_category(category_id: str):
    body = request.get_json(silent=True) or {}
    category = catalog_service.update_category(category_id, body)
    audit.log("category.update", category.id, category.name)
    return ok({"id": category.id, "name": category.name, "sort": category.sort})


@bp.delete("/<category_id>")
@admin_required
def delete_category(category_id: str):
    """删除分类：存在商品引用时返回 400。"""
    catalog_service.delete_category(category_id)
    audit.log("category.delete", category_id)
    return ok(None)
