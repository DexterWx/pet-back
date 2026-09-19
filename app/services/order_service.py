"""订单业务：创建/查询/发货/退款申请与撤回/取消。

状态机校验集中在本模块，小程序端接口与未来管理端（/api/v1/admin）复用同一套逻辑。
订单仅在支付成功后创建（无待付款态）；下单扣库存加销量并清购物车，取消回补库存回退销量。
"""
from ..core.constants import OrderStatus, gen_id, now_ms
from ..core.response import ApiError
from ..models import CartLine, Order, OrderItem, Product, db


def _get_product_or_404(product_id: str) -> Product:
    product = db.session.get(Product, product_id)
    if product is None:
        raise ApiError(404, "商品不存在")
    return product


def create_order(user_id: str, items: list[dict]) -> Order:
    """创建已支付订单：校验库存 -> 扣库存/加销量 -> 建订单快照 -> 清购物车对应商品。"""
    if not items:
        raise ApiError(400, "订单商品不能为空")

    lines = []
    total_fen = 0
    for it in items:
        product = _get_product_or_404(str(it.get("productId", "")))
        try:
            qty = int(it.get("qty", 0))
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            raise ApiError(400, f"「{product.title}」数量不正确")
        if product.stock < qty:
            raise ApiError(400, f"「{product.title}」库存不足")
        lines.append((product, qty))
        total_fen += product.price_fen * qty

    now = now_ms()
    order = Order(
        id=gen_id("o"),
        order_no=f"NO{now}",
        user_id=user_id,
        total_fen=total_fen,
        status=OrderStatus.PAID_UNSHIPPED,
        created_at=now,
        shipped_at=0,
        refund_requested_at=0,
        cancelled_at=0,
    )
    for product, qty in lines:
        # 扣减库存、累加销量
        product.stock -= qty
        product.sold += qty
        order.items.append(
            OrderItem(
                product_id=product.id,
                title=product.title,
                image=(product.images or [""])[0],
                price_fen=product.price_fen,
                qty=qty,
            )
        )
    db.session.add(order)

    # 下单后清空购物车中对应商品
    ordered_ids = [p.id for p, _ in lines]
    CartLine.query.filter(
        CartLine.user_id == user_id, CartLine.product_id.in_(ordered_ids)
    ).delete(synchronize_session=False)

    db.session.commit()
    return order


def list_orders(user_id: str, status: str = "") -> list[Order]:
    """订单列表（按创建时间倒序）。status=PAID_UNSHIPPED 时为“未发货” tab 分组过滤。"""
    query = Order.query.filter_by(user_id=user_id)
    if status == OrderStatus.PAID_UNSHIPPED:
        # “未发货” tab：尚未取消且未发货（含退款申请中）
        query = query.filter(Order.status.in_(OrderStatus.UNSHIPPED_GROUP))
    elif status:
        query = query.filter_by(status=status)
    return query.order_by(Order.created_at.desc()).all()


def get_user_order(order_id: str, user_id: str) -> Order:
    """取当前用户的订单，不存在（或不属于该用户）返回 404。"""
    order = db.session.get(Order, order_id)
    if order is None or order.user_id != user_id:
        raise ApiError(404, "订单不存在")
    return order


def ship_order(order: Order) -> Order:
    """发货（Demo：由小程序“模拟发货”按钮触发；真实场景应移至管理端）。"""
    order.status = OrderStatus.SHIPPED
    order.shipped_at = now_ms()
    db.session.commit()
    return order


def apply_refund(order: Order) -> Order:
    """用户申请退款：PAID_UNSHIPPED -> REFUND_REQUESTED。"""
    if order.status != OrderStatus.PAID_UNSHIPPED:
        raise ApiError(400, "当前订单状态不可申请退款")
    order.status = OrderStatus.REFUND_REQUESTED
    order.refund_requested_at = now_ms()
    db.session.commit()
    return order


def revoke_refund(order: Order) -> Order:
    """用户撤回退款申请：REFUND_REQUESTED -> PAID_UNSHIPPED。"""
    if order.status != OrderStatus.REFUND_REQUESTED:
        raise ApiError(400, "当前订单状态不可撤回申请")
    order.status = OrderStatus.PAID_UNSHIPPED
    order.refund_requested_at = 0
    db.session.commit()
    return order


def cancel_order(order: Order) -> Order:
    """商家同意退款/直接取消：-> CANCELLED（终态），回补库存、回退销量。

    SHIPPED 拒绝。真实场景由 web 管理端调用；小程序内为“模拟商家同意退款(Demo)”。
    """
    if order.status not in OrderStatus.CANCELLABLE:
        raise ApiError(400, "当前订单状态不可取消")
    order.status = OrderStatus.CANCELLED
    order.cancelled_at = now_ms()
    for item in order.items:
        product = db.session.get(Product, item.product_id)
        if product is not None:
            product.stock += item.qty
            product.sold -= item.qty
    db.session.commit()
    return order
