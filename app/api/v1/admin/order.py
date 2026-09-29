"""管理端订单接口（全部需管理员登录）：列表 / 详情 / 发货 / 发起退款。

业务逻辑复用 services.order_service，与小程序端同一套状态机，不复制规则。
"""
from flask import Blueprint, g, request

from ....core.response import ok
from ....core.security import admin_required
from ....services import audit, order_service, payment_service, serializers

bp = Blueprint("admin_order", __name__, url_prefix="/orders")


@bp.get("")
@admin_required
def list_orders():
    """status 过滤 + keyword（订单号/收货人/电话）搜索；afterSale=1 只看待处理售后的订单。"""
    status = request.args.get("status", "")
    keyword = request.args.get("keyword", "")
    after_sale = request.args.get("afterSale", "") in ("1", "true", "yes")
    orders = order_service.list_all_orders(status=status, keyword=keyword, after_sale=after_sale)
    return ok([serializers.order_payload(o) for o in orders])


@bp.get("/<order_id>")
@admin_required
def order_detail(order_id: str):
    return ok(serializers.order_payload(order_service.get_order_or_404(order_id)))


@bp.post("/<order_id>/ship")
@admin_required
def ship(order_id: str):
    """发货：录入物流信息（快递=carrier+shipNo；自提=shipNo 提货号）。"""
    body = request.get_json(silent=True) or {}
    order = order_service.ship_order(
        order_service.get_order_or_404(order_id),
        carrier=str(body.get("carrier", "")),
        ship_no=str(body.get("shipNo", "")),
    )
    audit.log("order.ship", order.id, order.ship_no)
    return ok(serializers.order_payload(order))


@bp.post("/<order_id>/refund")
@admin_required
def initiate_refund(order_id: str):
    """管理员直接发起退款：{refundFen, note}，金额自定义（可部分退）；全额退则订单转 REFUNDED。"""
    body = request.get_json(silent=True) or {}
    order = order_service.get_order_or_404(order_id)
    after_sale = order_service.admin_initiate_refund(
        order,
        refund_fen=body.get("refundFen", order.total_fen),
        admin_id=g.current_admin.id,
        note=str(body.get("note", "")),
    )
    payment_service.refund_after_sale(after_sale)  # 已支付则发起渠道退款（mock 为记账）
    audit.log("order.refund", order_id, f"{after_sale.refund_fen}fen")
    return ok(serializers.after_sale(after_sale))
