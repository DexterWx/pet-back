"""管理端运费设置：读取 / 更新全局运费规则（基础运费 + 满多少免运费）。

规则为全站一套（单行配置）；自提一律免运费，免运费判定只看商品金额合计。
"""
from flask import Blueprint, request

from ....core.response import ok
from ....core.security import admin_required
from ....services import audit, shipping_service

bp = Blueprint("admin_shipping", __name__, url_prefix="/shipping-config")


@bp.get("")
@admin_required
def get_config():
    return ok(shipping_service.config_payload(shipping_service.get_config()))


@bp.put("")
@admin_required
def update_config():
    """更新运费规则 `{baseFreightFen, freeThresholdFen}`（分；0=不收/不启用）。"""
    body = request.get_json(silent=True) or {}
    cfg = shipping_service.update_config(body)
    audit.log("shipping.update", "", f"base={cfg.base_freight_fen},free={cfg.free_threshold_fen}")
    return ok(shipping_service.config_payload(cfg))
