"""订单接口（全部需登录）。业务逻辑集中在 services.order_service。"""
from flask import Blueprint, g, request

from ....core.response import ok
from ....core.security import login_required
from ....services import order_service, serializers

bp = Blueprint("order", __name__, url_prefix="/orders")


@bp.get("")
@login_required
def list_orders():
    """订单列表；status=PAID_UNSHIPPED 时为“未发货”tab（含 REFUND_REQUESTED 分组）。"""
    status = request.args.get("status", "")
    orders = order_service.list_orders(g.current_user.id, status)
    return ok([serializers.order_payload(o) for o in orders])


@bp.post("/create")
@login_required
def create_order():
    """支付成功后创建订单（扣库存、加销量、清购物车对应商品）。"""
    body = request.get_json(silent=True) or {}
    order = order_service.create_order(g.current_user.id, body.get("items") or [])
    return ok(serializers.order_payload(order))


@bp.get("/<order_id>")
@login_required
def order_detail(order_id: str):
    order = order_service.get_user_order(order_id, g.current_user.id)
    return ok(serializers.order_payload(order))


@bp.post("/<order_id>/ship")
@login_required
def ship_order(order_id: str):
    """模拟发货（Demo 按钮触发；真实场景应移至管理端）。"""
    order = order_service.get_user_order(order_id, g.current_user.id)
    return ok(serializers.order_payload(order_service.ship_order(order)))


@bp.post("/<order_id>/refund")
@login_required
def apply_refund(order_id: str):
    """用户申请退款：PAID_UNSHIPPED -> REFUND_REQUESTED。"""
    order = order_service.get_user_order(order_id, g.current_user.id)
    return ok(serializers.order_payload(order_service.apply_refund(order)))


@bp.post("/<order_id>/refund/revoke")
@login_required
def revoke_refund(order_id: str):
    """用户撤回退款申请：REFUND_REQUESTED -> PAID_UNSHIPPED。"""
    order = order_service.get_user_order(order_id, g.current_user.id)
    return ok(serializers.order_payload(order_service.revoke_refund(order)))


@bp.post("/<order_id>/cancel")
@login_required
def cancel_order(order_id: str):
    """商家同意退款/直接取消：-> CANCELLED，回补库存回退销量。

    真实场景由 web 管理端调用；小程序内为“模拟商家同意退款(Demo)”。
    """
    order = order_service.get_user_order(order_id, g.current_user.id)
    return ok(serializers.order_payload(order_service.cancel_order(order)))
