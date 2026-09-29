"""管理端商品接口（全部需管理员登录）：列表 / 详情 / 创建 / 更新 / 上下架 / 删除。

业务规则在 services.catalog_service；接口层只做参数解析与鉴权。
- 下架 = PATCH /<id>/on-sale {onSale:false}（保留在库，可重新上架）。
- 删除 = DELETE /<id>（物理删库 + 删 OSS 图片，省钱；不可恢复）。
"""
from flask import Blueprint, request

from ....core.response import ok
from ....core.security import admin_required
from ....services import audit, catalog_service, serializers

bp = Blueprint("admin_product", __name__, url_prefix="/products")


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


@bp.get("")
@admin_required
def list_products():
    """分页 + keyword(标题) + categoryId + onSale(true/false/空=全部，含下架)。"""
    data = catalog_service.list_products(
        page=_int_arg("page", 1),
        page_size=_int_arg("pageSize", 20),
        keyword=request.args.get("keyword", ""),
        category_id=request.args.get("categoryId", ""),
        on_sale=request.args.get("onSale", ""),
    )
    return ok(data)


@bp.post("")
@admin_required
def create_product():
    body = request.get_json(silent=True) or {}
    product = catalog_service.create_product(body)
    audit.log("product.create", product.id, product.title)
    return ok(serializers.admin_product(product))


@bp.get("/<product_id>")
@admin_required
def product_detail(product_id: str):
    return ok(serializers.admin_product(catalog_service.get_product_or_404(product_id)))


@bp.put("/<product_id>")
@admin_required
def update_product(product_id: str):
    body = request.get_json(silent=True) or {}
    product = catalog_service.update_product(product_id, body)
    audit.log("product.update", product.id, product.title)
    return ok(serializers.admin_product(product))


@bp.patch("/<product_id>/on-sale")
@admin_required
def set_on_sale(product_id: str):
    """上/下架：{onSale: bool}。商品仍保留在库。"""
    body = request.get_json(silent=True) or {}
    product = catalog_service.set_on_sale(product_id, bool(body.get("onSale", True)))
    audit.log("product.on_sale", product.id, "on" if product.on_sale else "off")
    return ok(serializers.admin_product(product))


@bp.delete("/<product_id>")
@admin_required
def delete_product(product_id: str):
    """物理删除商品 + 删其 OSS 图片（弱一致，失败仅记日志）。"""
    catalog_service.delete_product(product_id)
    audit.log("product.delete", product_id)
    return ok(None)
