"""订单业务：创建/支付/关闭/发货/确认收货/售后退款/查询。

状态机（core.constants.OrderStatus）集中在本模块，小程序端与管理端复用同一套逻辑：
  PENDING_PAY --支付成功--> PAID_UNSHIPPED --发货--> SHIPPED --确认收货/满N天--> COMPLETED(终态)
  PENDING_PAY --超时/取消--> CLOSED(终态)
  售后(after_sales 表): 用户申请(全额)/管理员发起(自定义额) --> 同意 --> REFUNDED(终态)
无库存概念（下单现做）：支付成功累加销量；全额退款回退销量；待付款关闭不涉及销量。

退款窗口（can_user_refund）：未发货随时可退；已发货仅发货后 N 天内可退；已完成不可自助退（仅管理员可强制退）；
已被驳回过的订单永久不能再自助申请。N = config.ORDER_AUTO_COMPLETE_DAYS。
惰性状态刷新（refresh_order_state）：读取订单时顺带将超时待付款单关闭、将发货满 N 天的已发货单自动完成，
不引入定时任务（单 worker + SQLite，与项目现状一致）。
"""
from flask import current_app, g

from ..core.constants import (
    AfterSaleSource,
    AfterSaleStatus,
    DeliveryType,
    OrderStatus,
    gen_id,
    gen_order_no,
    now_ms,
)
from ..core.response import ApiError
from ..models import AfterSale, CartLine, Order, OrderConfig, OrderItem, Product, db
from . import notify, shipping_service

# 单笔数量上限（无库存后防误拍）
MAX_QTY_PER_ITEM = 99

# 发货后自动确认收货天数的最终兵底（无后台配置且无环境变量时）
DEFAULT_AUTO_COMPLETE_DAYS = 7
CONFIG_ID = 1


def _get_product_or_404(product_id: str) -> Product:
    product = db.session.get(Product, product_id)
    if product is None:
        raise ApiError(404, "商品不存在")
    return product


# ---------- 下单 / 支付 / 关闭 ----------

def create_order(
    user_id: str,
    items: list[dict],
    delivery_type: str = DeliveryType.EXPRESS,
    receiver_name: str = "",
    receiver_phone: str = "",
    receiver_address: str = "",
) -> Order:
    """创建待付款订单：校验商品/数量 -> 写订单快照(含收货信息) -> 清购物车对应商品。

    下单即 PENDING_PAY，不累加销量（销量在支付成功时累加）；无库存不涉及锁定。
    """
    if not items:
        raise ApiError(400, "订单商品不能为空")
    if delivery_type not in (DeliveryType.EXPRESS, DeliveryType.SELF_PICKUP):
        raise ApiError(400, "配送方式不正确")
    if not receiver_name.strip() or not receiver_phone.strip():
        raise ApiError(400, "请填写收货人姓名和联系电话")
    if delivery_type == DeliveryType.EXPRESS and not receiver_address.strip():
        raise ApiError(400, "快递订单需要完整收货地址")

    lines = []
    goods_total_fen = 0
    for it in items:
        product = _get_product_or_404(str(it.get("productId", "")))
        if not product.on_sale:
            raise ApiError(400, f"「{product.title}」已下架，无法下单")
        try:
            qty = int(it.get("qty", 0))
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            raise ApiError(400, f"「{product.title}」数量不正确")
        if qty > MAX_QTY_PER_ITEM:
            raise ApiError(400, f"「{product.title}」单笔最多 {MAX_QTY_PER_ITEM} 件")
        lines.append((product, qty))
        goods_total_fen += product.price_fen * qty

    # 运费由服务端按当前规则算定（不信任前端），与商品金额一起快照到订单
    freight_fen = shipping_service.calc_freight(goods_total_fen, delivery_type)
    total_fen = goods_total_fen + freight_fen

    order = Order(
        id=gen_id("o"),
        order_no=gen_order_no(),
        user_id=user_id,
        total_fen=total_fen,
        goods_total_fen=goods_total_fen,
        freight_fen=freight_fen,
        status=OrderStatus.PENDING_PAY,
        delivery_type=delivery_type,
        receiver_name=receiver_name.strip(),
        receiver_phone=receiver_phone.strip(),
        receiver_address=receiver_address.strip(),
        created_at=now_ms(),
    )
    for product, qty in lines:
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

    ordered_ids = [p.id for p, _ in lines]
    CartLine.query.filter(
        CartLine.user_id == user_id, CartLine.product_id.in_(ordered_ids)
    ).delete(synchronize_session=False)

    db.session.commit()
    return order


def mark_paid(order: Order) -> Order:
    """支付成功：PENDING_PAY -> PAID_UNSHIPPED，累加销量。（C 阶段由支付回调调用）"""
    if order.status != OrderStatus.PENDING_PAY:
        raise ApiError(400, "当前订单状态不可支付")
    order.status = OrderStatus.PAID_UNSHIPPED
    order.paid_at = now_ms()
    for item in order.items:
        product = db.session.get(Product, item.product_id)
        if product is not None:
            product.sold += item.qty
    db.session.commit()
    return order


def _pending_pay_ttl_ms() -> int:
    return int(current_app.config.get("ORDER_PENDING_PAY_TTL_MIN", 30)) * 60 * 1000


def _auto_complete_ms() -> int:
    return get_auto_complete_days() * 86400 * 1000


def get_auto_complete_days() -> int:
    """发货后自动确认收货天数：优先读后台配置(order_configs)，回退环境变量，再回退 7。

    请求级缓存于 g，避免列表循环逐单重复查库。
    """
    cached = getattr(g, "_auto_complete_days", None)
    if cached is not None:
        return cached
    cfg = db.session.get(OrderConfig, CONFIG_ID)
    if cfg is not None:
        days = cfg.auto_complete_days
    else:
        days = int(current_app.config.get("ORDER_AUTO_COMPLETE_DAYS", DEFAULT_AUTO_COMPLETE_DAYS))
    g._auto_complete_days = days
    return days


def get_config() -> OrderConfig:
    """取交易配置；不存在时惰性创建默认（天数取环境变量或 7）。"""
    cfg = db.session.get(OrderConfig, CONFIG_ID)
    if cfg is None:
        cfg = OrderConfig(
            id=CONFIG_ID,
            auto_complete_days=int(current_app.config.get("ORDER_AUTO_COMPLETE_DAYS", DEFAULT_AUTO_COMPLETE_DAYS)),
            updated_at=now_ms(),
        )
        db.session.add(cfg)
        db.session.commit()
    return cfg


def config_payload(cfg: OrderConfig) -> dict:
    return {"autoCompleteDays": cfg.auto_complete_days, "updatedAt": cfg.updated_at}


def update_config(body: dict) -> OrderConfig:
    """更新交易配置（目前仅 autoCompleteDays，1~365 天）。"""
    cfg = get_config()
    if "autoCompleteDays" in body:
        try:
            days = int(body.get("autoCompleteDays"))
        except (TypeError, ValueError):
            raise ApiError(400, "自动确认天数不正确")
        if days < 1 or days > 365:
            raise ApiError(400, "自动确认天数需在 1~365 天之间")
        cfg.auto_complete_days = days
    cfg.updated_at = now_ms()
    db.session.commit()
    return cfg


def _has_rejected_after_sale(order_id: str) -> bool:
    """该订单是否已被驳回过（驳回后永久不能再自助申请）。"""
    return AfterSale.query.filter_by(
        order_id=order_id, status=AfterSaleStatus.REJECTED
    ).first() is not None


def refresh_order_state(order: Order) -> Order:
    """惰性状态刷新（读取订单时调用）：

    1. PENDING_PAY 且超 TTL -> CLOSED；
    2. SHIPPED 且发货满 N 天且无在途售后单 -> COMPLETED（自动确认收货）。
    任一变则 commit 并返回最新 order。
    """
    if order.status == OrderStatus.PENDING_PAY and now_ms() > order.created_at + _pending_pay_ttl_ms():
        order.status = OrderStatus.CLOSED
        order.cancelled_at = now_ms()
        db.session.commit()
    auto_complete_if_due(order)
    return order


def auto_complete_if_due(order: Order) -> Order:
    """发货满 N 天自动确认收货：SHIPPED -> COMPLETED(source=AUTO)。

    存在 PENDING 售后单时不自动完成（否则订单被置完成、售后单悬空），等商家处理完再说。
    """
    if order.status == OrderStatus.SHIPPED and order.shipped_at and now_ms() > order.shipped_at + _auto_complete_ms():
        if _pending_after_sale(order.id) is None:
            order.status = OrderStatus.COMPLETED
            order.completed_at = now_ms()
            order.complete_source = "AUTO"
            db.session.commit()
    return order


def close_order(order: Order) -> Order:
    """关闭待付款订单（用户主动取消/超时）：PENDING_PAY -> CLOSED。"""
    if order.status != OrderStatus.PENDING_PAY:
        raise ApiError(400, "仅待付款订单可取消")
    order.status = OrderStatus.CLOSED
    order.cancelled_at = now_ms()
    db.session.commit()
    return order


def ship_order(order: Order, carrier: str = "", ship_no: str = "") -> Order:
    """发货（管理端）：PAID_UNSHIPPED -> SHIPPED，录入物流信息。

    快递必须有物流公司+单号；**自提无需任何单号**，商家直接点发货即可（用户凭订单到店取货）。
    """
    if order.status not in OrderStatus.SHIPPABLE:
        raise ApiError(400, "当前订单状态不可发货")
    if order.delivery_type == DeliveryType.EXPRESS:
        if not carrier.strip():
            raise ApiError(400, "快递订单请填写物流公司")
        if not ship_no.strip():
            raise ApiError(400, "快递订单请填写物流单号")
    order.status = OrderStatus.SHIPPED
    order.carrier = carrier.strip()
    order.ship_no = ship_no.strip()
    order.shipped_at = now_ms()
    db.session.commit()
    return order


def confirm_receive(order: Order) -> Order:
    """用户确认收货：SHIPPED -> COMPLETED(source=USER)。有在途退款申请时不可确认。"""
    if order.status != OrderStatus.SHIPPED:
        raise ApiError(400, "当前订单状态不可确认收货")
    if _pending_after_sale(order.id) is not None:
        raise ApiError(400, "退款申请处理中，无法确认收货")
    order.status = OrderStatus.COMPLETED
    order.completed_at = now_ms()
    order.complete_source = "USER"
    db.session.commit()
    return order


# ---------- 售后（退款） ----------

def _pending_after_sale(order_id: str) -> AfterSale | None:
    return AfterSale.query.filter_by(order_id=order_id, status=AfterSaleStatus.PENDING).first()


def can_user_refund(order: Order) -> bool:
    """用户能否自助申请退款（单一事实源，前端只读此布尔，不自己算窗口）。

    不可退的情况：已有在途申请 / 曾被驳回 / 已完成等终态 / 已发货但超过退款窗口。
    """
    if _pending_after_sale(order.id) is not None or _has_rejected_after_sale(order.id):
        return False
    if order.status == OrderStatus.PAID_UNSHIPPED:
        return True
    if order.status == OrderStatus.SHIPPED:
        return bool(order.shipped_at) and now_ms() <= order.shipped_at + _auto_complete_ms()
    return False


def can_confirm_receive(order: Order) -> bool:
    """用户能否确认收货：仅已发货且无在途退款申请。"""
    return order.status == OrderStatus.SHIPPED and _pending_after_sale(order.id) is None


def refund_deadline_ms(order: Order) -> int:
    """已发货订单的退款截止时间戳（毫秒）；非 SHIPPED 返回 0。供前端展示“还剩几天”。"""
    if order.status == OrderStatus.SHIPPED and order.shipped_at:
        return order.shipped_at + _auto_complete_ms()
    return 0


def apply_refund(order: Order, reason: str = "") -> AfterSale:
    """用户申请退款（整单全额）：受退款窗口与驳回锁定限制（见 can_user_refund）。"""
    if _pending_after_sale(order.id) is not None:
        raise ApiError(400, "已有退款申请正在处理中")
    if _has_rejected_after_sale(order.id):
        raise ApiError(400, "该订单退款申请已被驳回，不能再自助申请")
    if order.status == OrderStatus.PAID_UNSHIPPED:
        pass  # 未发货，随时可退
    elif order.status == OrderStatus.SHIPPED:
        if not (order.shipped_at and now_ms() <= order.shipped_at + _auto_complete_ms()):
            raise ApiError(400, f"发货已超过 {int(_auto_complete_ms() // 86400000)} 天，不能再申请退款")
    else:
        raise ApiError(400, "当前订单状态不可申请退款")
    after_sale = AfterSale(
        id=gen_id("as"),
        order_id=order.id,
        user_id=order.user_id,
        source=AfterSaleSource.USER,
        refund_fen=order.total_fen,  # 用户申请=整单全额
        reason=str(reason or "").strip()[:255],
        status=AfterSaleStatus.PENDING,
        created_at=now_ms(),
    )
    db.session.add(after_sale)
    order.refund_requested_at = now_ms()
    db.session.commit()
    # commit 后再通知，保证群里提到的单子已经在库里；通知失败不影响申请
    notify.notify_refund_request(after_sale, order)
    return after_sale


def revoke_refund(order: Order) -> None:
    """用户撤回退款申请：删除其 PENDING 售后单。"""
    after_sale = _pending_after_sale(order.id)
    if after_sale is None or after_sale.source != AfterSaleSource.USER:
        raise ApiError(400, "没有可撤回的退款申请")
    db.session.delete(after_sale)
    order.refund_requested_at = 0
    db.session.commit()


def _rollback_sold(order: Order) -> None:
    """全额退款回退销量（下限 0）。"""
    for item in order.items:
        product = db.session.get(Product, item.product_id)
        if product is not None:
            product.sold = max(0, product.sold - item.qty)


def _committed_refund_fen(order_id: str, exclude_id: str | None = None) -> int:
    """该订单已承诺退款的金额（REFUNDING + REFUNDED 之和），用于防累计超退。"""
    q = AfterSale.query.filter(
        AfterSale.order_id == order_id,
        AfterSale.status.in_([AfterSaleStatus.REFUNDING, AfterSaleStatus.REFUNDED]),
    )
    if exclude_id:
        q = q.filter(AfterSale.id != exclude_id)
    return sum(a.refund_fen for a in q.all())


def _is_full_refund(after_sale: AfterSale, order: Order | None) -> bool:
    return order is not None and after_sale.refund_fen >= order.total_fen


def _begin_refund(after_sale: AfterSale, order: Order | None) -> None:
    """售后单进入退款中：置 REFUNDING；全额退则订单同步转 REFUNDING（到账后再 finalize）。"""
    after_sale.status = AfterSaleStatus.REFUNDING
    if _is_full_refund(after_sale, order) and order.status != OrderStatus.REFUNDED:
        order.status = OrderStatus.REFUNDING


def finalize_refund(after_sale: AfterSale) -> bool:
    """退款到账收尾：REFUNDING -> REFUNDED；全额退则订单 REFUNDING -> REFUNDED + 回退销量。

    幂等：非 REFUNDING 直接返回 False（重复回调/重复同步不会二次回退销量）。
    同步渠道（余额/mock/无支付单）在发起后立即调用；微信则由退款回调或主动查单补偿调用。
    """
    if after_sale.status != AfterSaleStatus.REFUNDING:
        return False
    after_sale.status = AfterSaleStatus.REFUNDED
    if not after_sale.handled_at:
        after_sale.handled_at = now_ms()
    order = db.session.get(Order, after_sale.order_id)
    if _is_full_refund(after_sale, order) and order.status == OrderStatus.REFUNDING:
        order.status = OrderStatus.REFUNDED
        order.refunded_at = now_ms()
        _rollback_sold(order)
    db.session.commit()
    return True


def admin_approve_refund(after_sale: AfterSale, admin_id: str, note: str = "") -> AfterSale:
    """同意用户退款：PENDING -> REFUNDING（渠道到账后由 finalize_refund 转 REFUNDED）。

    全额退则订单同步转 REFUNDING；销量在真正到账（finalize）时才回退。
    含防累计超退校验：本单 + 已承诺退款不得超过订单总额。
    """
    if after_sale.status != AfterSaleStatus.PENDING:
        raise ApiError(400, "该售后单不可同意")
    order = db.session.get(Order, after_sale.order_id)
    # 防重复退款：订单已 REFUNDED 说明款已退过，不能再同意这条残留 PENDING 单
    if order is not None and order.status == OrderStatus.REFUNDED:
        raise ApiError(400, "订单已退款，不能重复同意；如为残留申请单请直接驳回")
    if order is not None:
        remaining = order.total_fen - _committed_refund_fen(order.id, exclude_id=after_sale.id)
        if after_sale.refund_fen > remaining:
            raise ApiError(400, f"累计退款将超过订单金额（还可退 ¥{remaining / 100:.2f}）")
    after_sale.admin_id = admin_id
    after_sale.admin_note = str(note or "").strip()[:255]
    after_sale.handled_at = now_ms()
    _begin_refund(after_sale, order)
    db.session.commit()
    return after_sale


def admin_reject_refund(after_sale: AfterSale, admin_id: str, note: str = "") -> AfterSale:
    """管理员驳回用户退款申请：PENDING -> REJECTED，订单状态不变。"""
    if after_sale.status != AfterSaleStatus.PENDING:
        raise ApiError(400, "该售后单不可驳回")
    after_sale.status = AfterSaleStatus.REJECTED
    after_sale.admin_id = admin_id
    after_sale.admin_note = str(note or "").strip()[:255]
    after_sale.handled_at = now_ms()
    order = db.session.get(Order, after_sale.order_id)
    if order is not None:
        order.refund_requested_at = 0
    db.session.commit()
    return after_sale


def admin_initiate_refund(order: Order, refund_fen: int, admin_id: str, note: str = "") -> AfterSale:
    """管理员直接发起退款（金额自定义可部分）：生成 REFUNDING 售后单（到账后 finalize 转 REFUNDED）。

    全额退则订单转 REFUNDING（finalize 时转 REFUNDED + 回退销量）；部分退订单履约状态不变。
    全额退且存在用户申请的 PENDING 单时，一并置 REJECTED 合并关闭（钱由本单退，
    既清掉待处理列表、又锁定其自助再申请，防二次退款）。
    含防累计超退校验。
    """
    if order.status not in OrderStatus.ADMIN_REFUNDABLE:
        raise ApiError(400, "当前订单状态不可退款")
    try:
        refund_fen = int(refund_fen)
    except (TypeError, ValueError):
        refund_fen = 0
    if refund_fen <= 0:
        raise ApiError(400, "退款金额不正确")
    if refund_fen > order.total_fen:
        raise ApiError(400, "退款金额不能超过订单金额")
    remaining = order.total_fen - _committed_refund_fen(order.id)
    if refund_fen > remaining:
        raise ApiError(400, f"累计退款将超过订单金额（还可退 ¥{remaining / 100:.2f}）")

    handled_at = now_ms()
    clean_note = str(note or "").strip()[:255]
    is_full = refund_fen >= order.total_fen

    # 全额退时合并关闭用户 PENDING 申请单（置 REJECTED：钱由本单退）；部分退则保留其待处理
    if is_full:
        for p in AfterSale.query.filter_by(order_id=order.id, status=AfterSaleStatus.PENDING).all():
            p.status = AfterSaleStatus.REJECTED
            p.admin_id = admin_id
            p.admin_note = clean_note or "管理员已直接退款，合并关闭"
            p.handled_at = handled_at

    after_sale = AfterSale(
        id=gen_id("as"),
        order_id=order.id,
        user_id=order.user_id,
        source=AfterSaleSource.ADMIN,
        refund_fen=refund_fen,
        reason=clean_note,
        status=AfterSaleStatus.REFUNDING,
        admin_id=admin_id,
        admin_note=clean_note,
        handled_at=handled_at,
        created_at=now_ms(),
    )
    db.session.add(after_sale)
    _begin_refund(after_sale, order)
    db.session.commit()
    return after_sale


# ---------- 查询 ----------

def _pending_aftersale_order_ids(user_id: str | None = None) -> list[str]:
    """有进行中售后单（PENDING 待处理 / REFUNDING 退款中）的订单 id，供“退款/售后” tab 分组。"""
    q = AfterSale.query.filter(
        AfterSale.status.in_([AfterSaleStatus.PENDING, AfterSaleStatus.REFUNDING])
    )
    if user_id:
        q = q.filter_by(user_id=user_id)
    return [row.order_id for row in q.all()]


def list_orders(user_id: str, tab: str = "") -> list[Order]:
    """用户订单列表（按创建时间倒序）。tab: ''/PENDING_PAY/PAID_UNSHIPPED/SHIPPED/AFTER_SALE。"""
    query = Order.query.filter_by(user_id=user_id)
    if tab == "AFTER_SALE":
        ids = _pending_aftersale_order_ids(user_id)
        if not ids:
            return []
        query = query.filter(Order.id.in_(ids))
    elif tab:
        query = query.filter_by(status=tab)
    orders = query.order_by(Order.created_at.desc()).all()
    for o in orders:
        refresh_order_state(o)  # 惰性刷新：超时关闭待付款 / 满 N 天自动完成
    return orders


def list_all_orders(status: str = "", keyword: str = "", after_sale: bool = False) -> list[Order]:
    """管理端订单列表：按状态过滤 + 关键字（订单号/收货人/电话）搜索 + 仅待处理售后。"""
    query = Order.query
    if after_sale:
        ids = _pending_aftersale_order_ids()
        if not ids:
            return []
        query = query.filter(Order.id.in_(ids))
    if status:
        query = query.filter_by(status=status)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            db.or_(
                Order.id.like(like),
                Order.order_no.like(like),
                Order.receiver_name.like(like),
                Order.receiver_phone.like(like),
            )
        )
    orders = query.order_by(Order.created_at.desc()).all()
    for o in orders:
        refresh_order_state(o)
    return orders


def get_user_order(order_id: str, user_id: str) -> Order:
    order = db.session.get(Order, order_id)
    if order is None or order.user_id != user_id:
        raise ApiError(404, "订单不存在")
    return refresh_order_state(order)


def get_order_or_404(order_id: str) -> Order:
    order = db.session.get(Order, order_id)
    if order is None:
        raise ApiError(404, "订单不存在")
    return refresh_order_state(order)


def get_after_sale_or_404(after_sale_id: str) -> AfterSale:
    after_sale = db.session.get(AfterSale, after_sale_id)
    if after_sale is None:
        raise ApiError(404, "售后单不存在")
    return after_sale


def list_pending_after_sales(status: str = AfterSaleStatus.PENDING) -> list[AfterSale]:
    """管理端售后单列表（默认待处理 PENDING；可传 REFUNDING 看退款中的）。"""
    return AfterSale.query.filter_by(status=status).order_by(AfterSale.created_at.desc()).all()
