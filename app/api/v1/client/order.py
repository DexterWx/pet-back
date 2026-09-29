"""订单接口（全部需登录）。业务逻辑集中在 services.order_service。

用户侧能力：下单（待付款）、查列表/详情、取消待付款单、确认收货、申请退款/撤回。
支付、发货、售后处理属商家侧/支付回调，见 /api/v1/admin 与 C 阶段支付回调。
"""
from flask import Blueprint, g, request

from ....core.constants import DeliveryType
from ....core.response import ApiError, ok
from ....core.security import login_required
from ....models import Address, db
from ....services import order_service, serializers

bp = Blueprint("order", __name__, url_prefix="/orders")


def _reload(order_id: str):
    return order_service.get_user_order(order_id, g.current_user.id)


@bp.get("")
@login_required
def list_orders():
    """订单列表。tab: ''/PENDING_PAY/PAID_UNSHIPPED/SHIPPED/AFTER_SALE（有进行中售后）。"""
    tab = request.args.get("status", "") or request.args.get("tab", "")
    orders = order_service.list_orders(g.current_user.id, tab)
    return ok([serializers.order_payload(o) for o in orders])


@bp.post("/create")
@login_required
def create_order():
    """下单：{items, deliveryType, addressId} -> 待付款订单（PENDING_PAY）。

    从地址簿取 addressId 并校验归属，快照收货信息；清购物车对应商品。支付成功后由回调转已付款。
    """
    body = request.get_json(silent=True) or {}
    delivery_type = str(body.get("deliveryType") or DeliveryType.EXPRESS)
    address_id = str(body.get("addressId", ""))

    address = db.session.get(Address, address_id)
    if address is None or address.user_id != g.current_user.id:
        raise ApiError(400, "请选择有效的收货地址")

    order = order_service.create_order(
        user_id=g.current_user.id,
        items=body.get("items") or [],
        delivery_type=delivery_type,
        receiver_name=address.receiver_name,
        receiver_phone=address.phone,
        receiver_address=address.full_address,
    )
    return ok(serializers.order_payload(order))


@bp.get("/<order_id>")
@login_required
def order_detail(order_id: str):
    order = order_service.get_user_order(order_id, g.current_user.id)
    return ok(serializers.order_payload(order))


@bp.post("/<order_id>/cancel")
@login_required
def cancel_order(order_id: str):
    """用户取消待付款订单：PENDING_PAY -> CLOSED。"""
    order = order_service.get_user_order(order_id, g.current_user.id)
    return ok(serializers.order_payload(order_service.close_order(order)))


@bp.post("/<order_id>/confirm")
@login_required
def confirm_order(order_id: str):
    """用户确认收货：SHIPPED -> COMPLETED（终态，此后不可自助退款）。"""
    order = order_service.get_user_order(order_id, g.current_user.id)
    return ok(serializers.order_payload(order_service.confirm_receive(order)))


@bp.post("/<order_id>/refund")
@login_required
def apply_refund(order_id: str):
    """用户申请退款（整单全额）：生成 PENDING 售后单，等待管理员处理。"""
    order = order_service.get_user_order(order_id, g.current_user.id)
    body = request.get_json(silent=True) or {}
    order_service.apply_refund(order, reason=str(body.get("reason", "")))
    return ok(serializers.order_payload(_reload(order_id)))


@bp.post("/<order_id>/refund/revoke")
@login_required
def revoke_refund(order_id: str):
    """用户撤回退款申请：删除 PENDING 售后单。"""
    order = order_service.get_user_order(order_id, g.current_user.id)
    order_service.revoke_refund(order)
    return ok(serializers.order_payload(_reload(order_id)))
