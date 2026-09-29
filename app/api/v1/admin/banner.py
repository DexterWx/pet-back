"""管理端 Banner 接口：列表 / 新建 / 更新 / 删除（含启停与排序）。

Banner 为首页大图美观位；enabled=False 时小程序不展示（不删图，可随时恢复）。
删除时尽力同步删除图片（省存储成本），失败不影响记录删除。
"""
from flask import Blueprint, request

from ....core.response import ok
from ....core.security import admin_required
from ....services import audit, catalog_service, serializers

bp = Blueprint("admin_banner", __name__, url_prefix="/banners")


@bp.get("")
@admin_required
def list_banners():
    return ok([serializers.admin_banner(b) for b in catalog_service.list_banners()])


@bp.post("")
@admin_required
def create_banner():
    """新建 banner `{image, title, sort, enabled}`；image 必填（先走 /upload/image）。"""
    body = request.get_json(silent=True) or {}
    banner = catalog_service.create_banner(body)
    audit.log("banner.create", banner.id, banner.title)
    return ok(serializers.admin_banner(banner))


@bp.put("/<banner_id>")
@admin_required
def update_banner(banner_id: str):
    body = request.get_json(silent=True) or {}
    banner = catalog_service.update_banner(banner_id, body)
    audit.log("banner.update", banner.id, f"enabled={banner.enabled}")
    return ok(serializers.admin_banner(banner))


@bp.delete("/<banner_id>")
@admin_required
def delete_banner(banner_id: str):
    catalog_service.delete_banner(banner_id)
    audit.log("banner.delete", banner_id)
    return ok(None)
