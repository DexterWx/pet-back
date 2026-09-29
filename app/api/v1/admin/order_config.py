"""管理端交易配置：读取 / 更新全局交易参数（目前为发货后自动确认收货天数 = 退款窗口）。

与运费配置一致的语义：全站一套、单行配置；修改只影响之后的判定（历史订单已完成/退款不受影响）。
"""
from flask import Blueprint, request

from ....core.response import ok
from ....core.security import admin_required
from ....services import audit, order_service

bp = Blueprint("admin_order_config", __name__, url_prefix="/order-config")


@bp.get("")
@admin_required
def get_config():
    return ok(order_service.config_payload(order_service.get_config()))


@bp.put("")
@admin_required
def update_config():
    """更新交易配置 `{autoCompleteDays}`（1~365 天）。"""
    body = request.get_json(silent=True) or {}
    cfg = order_service.update_config(body)
    audit.log("order_config.update", "", f"days={cfg.auto_complete_days}")
    return ok(order_service.config_payload(cfg))
