"""序列化：模型 -> 接口响应 dict。

字段名与 pet-mini/mock/server.js 完全一致（camelCase、金额 *Fen、毫秒时间戳），
确保小程序切 useMock=false 后零改动可用。
"""
from ..models import Address, AdminUser, CartLine, Order, Product, User


def public_user(u: User | None) -> dict | None:
    """用户快照（不暴露 openid/token）。积分/优惠券已废弃移除。"""
    if u is None:
        return None
    return {
        "id": u.id,
        "nickname": u.nickname,
        "avatar": u.avatar,
        "phone": u.phone,
        "balanceFen": u.balance_fen,
    }


def address(a: Address) -> dict:
    """收货地址（camelCase）；address 为拼接后的完整地址，便于前端直接展示。"""
    return {
        "id": a.id,
        "receiverName": a.receiver_name,
        "phone": a.phone,
        "province": a.province,
        "city": a.city,
        "district": a.district,
        "detail": a.detail,
        "address": a.full_address,
        "isDefault": bool(a.is_default),
        "createdAt": a.created_at,
        "updatedAt": a.updated_at,
    }


def product_brief(p: Product) -> dict:
    """商品摘要，对齐 Mock productBrief（无库存）。"""
    return {
        "id": p.id,
        "title": p.title,
        "categoryId": p.category_id,
        "priceFen": p.price_fen,
        "sold": p.sold,
        "images": list(p.images or []),
        "desc": p.description,
    }


def product_detail(p: Product) -> dict:
    """商品详情：摘要 + 分类名。"""
    data = product_brief(p)
    data["categoryName"] = p.category.name if p.category else ""
    return data


def cart_line(line: CartLine, product: Product) -> dict:
    """购物车行：实时 join 商品（价格以商品表为准），对齐 Mock cartLines（无库存）。"""
    return {
        "productId": line.product_id,
        "qty": line.qty,
        "checked": bool(line.checked),
        "product": {
            "id": product.id,
            "title": product.title,
            "images": list(product.images or []),
            "priceFen": product.price_fen,
        },
    }


def order_item(item) -> dict:
    """订单行快照，对齐 Mock order.items 元素。"""
    return {
        "productId": item.product_id,
        "title": item.title,
        "image": item.image,
        "priceFen": item.price_fen,
        "qty": item.qty,
    }


def order_payload(o: Order) -> dict:
    """订单详情/列表项，对齐 Mock Order + 配送/物流/收货/支付时间 + 最新售后概要。

    canRefund/canConfirm/refundDeadlineAt 由 order_service 统一算定（含退款窗口/驳回锁定），
    前端直接读布尔渲染，不重复实现业务规则。
    """
    from . import order_service  # 延迟导入避免循环依赖

    after_sales = list(o.after_sales or [])
    latest = after_sale(after_sales[0]) if after_sales else None
    return {
        "id": o.id,
        "orderNo": o.order_no,
        "userId": o.user_id,
        "items": [order_item(i) for i in o.items],
        "totalFen": o.total_fen,
        # 金额拆分（前端展示明细）：totalFen = goodsTotalFen + freightFen
        "goodsTotalFen": o.goods_total_fen,
        "freightFen": o.freight_fen,
        "status": o.status,
        "deliveryType": o.delivery_type,
        "receiverName": o.receiver_name,
        "receiverPhone": o.receiver_phone,
        "address": o.receiver_address,
        "carrier": o.carrier,
        "shipNo": o.ship_no,
        "createdAt": o.created_at,
        "paidAt": o.paid_at,
        "shippedAt": o.shipped_at,
        "completedAt": o.completed_at,
        "completeSource": o.complete_source,
        "refundRequestedAt": o.refund_requested_at,
        "cancelledAt": o.cancelled_at,
        "refundedAt": o.refunded_at,
        # 用户侧可操作性（服务端统一判定）：是否可申请退款 / 可确认收货 / 退款截止时间
        "canRefund": order_service.can_user_refund(o),
        "canConfirm": order_service.can_confirm_receive(o),
        "refundDeadlineAt": order_service.refund_deadline_ms(o),
        "afterSale": latest,
    }


def after_sale(a) -> dict:
    """售后（退款）单。"""
    return {
        "id": a.id,
        "orderId": a.order_id,
        "source": a.source,
        "refundFen": a.refund_fen,
        "reason": a.reason,
        "status": a.status,
        "adminNote": a.admin_note,
        "wxRefundId": a.wx_refund_id,
        "createdAt": a.created_at,
        "handledAt": a.handled_at,
    }


# ---------- 管理端（pet-web）专用序列化 ----------

def admin_product(p: Product) -> dict:
    """管理端商品：在 client product_detail 基础上补 onSale/sort/createdAt 等运营字段。"""
    data = product_detail(p)
    data["onSale"] = bool(p.on_sale)
    data["sort"] = p.sort
    return data


def admin_banner(b) -> dict:
    """管理端 banner：含启停、排序与跳转商品。"""
    return {
        "id": b.id,
        "image": b.image,
        "title": b.title,
        "sort": b.sort,
        "enabled": bool(b.enabled),
        "productId": b.product_id or "",
    }


def admin_account(a: AdminUser) -> dict:
    """管理端账号列表项（绝不含 password_hash）。"""
    return {
        "id": a.id,
        "username": a.username,
        "displayName": a.display_name,
        "isActive": bool(a.is_active),
        "isSuper": bool(a.is_super),
        "createdAt": a.created_at,
        "lastLoginAt": a.last_login_at,
    }


def admin_user(u: User, order_count: int = 0) -> dict:
    """管理端用户列表项：公开字段 + 订单数（不暴露 openid）。"""
    data = public_user(u)
    data["orderCount"] = order_count
    data["createdAt"] = u.created_at
    return data
