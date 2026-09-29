"""管理端售后（退款）接口（全部需管理员登录）：待处理列表 / 同意 / 驳回 / 同步退款状态。

售后与订单履约状态解耦：同意=进入 REFUNDING，渠道到账后（同步渠道立即/微信回调或查单）转 REFUNDED；
驳回=订单状态不变且锁定用户自助再申请。
"""
from flask import Blueprint, g, request

from ....core.response import ok
from ....core.security import admin_required
from ....services import audit, order_service, payment_service, serializers

bp = Blueprint("admin_aftersale", __name__, url_prefix="/after-sales")


@bp.get("")
@admin_required
def list_after_sales():
    """售后单列表。status 默认 PENDING（待处理）；可传 REFUNDING 看退款中的。"""
    status = request.args.get("status", "") or "PENDING"
    rows = order_service.list_pending_after_sales(status=status)
    return ok([serializers.after_sale(a) for a in rows])


@bp.post("/<after_sale_id>/approve")
@admin_required
def approve(after_sale_id: str):
    """同意退款：{note}；全额退则订单转 REFUNDED 并回退销量。"""
    body = request.get_json(silent=True) or {}
    after_sale = order_service.get_after_sale_or_404(after_sale_id)
    after_sale = order_service.admin_approve_refund(after_sale, g.current_admin.id, str(body.get("note", "")))
    payment_service.refund_after_sale(after_sale)  # 已支付订单发起渠道退款（mock 为记账），回填 wx_refund_id
    audit.log("aftersale.approve", after_sale.id, f"{after_sale.refund_fen}fen")
    return ok(serializers.after_sale(after_sale))


@bp.post("/<after_sale_id>/reject")
@admin_required
def reject(after_sale_id: str):
    """驳回退款：{note}；订单状态不变。"""
    body = request.get_json(silent=True) or {}
    after_sale = order_service.get_after_sale_or_404(after_sale_id)
    after_sale = order_service.admin_reject_refund(after_sale, g.current_admin.id, str(body.get("note", "")))
    audit.log("aftersale.reject", after_sale.id, str(body.get("note", ""))[:60])
    return ok(serializers.after_sale(after_sale))


@bp.post("/<after_sale_id>/sync")
@admin_required
def sync_refund(after_sale_id: str):
    """主动查渠道退款单状态（掉单补偿）：REFUNDING 且渠道已 SUCCESS 则收尾为 REFUNDED。"""
    after_sale = order_service.get_after_sale_or_404(after_sale_id)
    payment_service.compensate_refund(after_sale)
    audit.log("aftersale.sync", after_sale.id, after_sale.status)
    return ok(serializers.after_sale(after_sale))
