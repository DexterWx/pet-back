"""运费规则查询（免登录）：供商品详情页/购物车/结算页展示包邮标识。

只读接口；修改走管理端 `/api/v1/admin/shipping-config`。
"""
from flask import Blueprint

from ....core.response import ok
from ....services import shipping_service

bp = Blueprint("client_shipping", __name__, url_prefix="/shipping")


@bp.get("/config")
def shipping_config():
    """当前运费规则：基础运费 + 包邮门槛（均为分；0 表示不收/不启用）。"""
    return ok(shipping_service.config_payload(shipping_service.get_config()))
