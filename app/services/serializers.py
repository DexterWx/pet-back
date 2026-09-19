"""序列化：模型 -> 接口响应 dict。

字段名与 pet-mini/mock/server.js 完全一致（camelCase、金额 *Fen、毫秒时间戳），
确保小程序切 useMock=false 后零改动可用。
"""
from ..models import CartLine, Order, Product, User


def public_user(u: User | None) -> dict | None:
    """用户快照（不暴露 openid/token），对齐 Mock publicUser。"""
    if u is None:
        return None
    return {
        "id": u.id,
        "nickname": u.nickname,
        "avatar": u.avatar,
        "balanceFen": u.balance_fen,
        "points": u.points,
        "coupons": u.coupons,
    }


def product_brief(p: Product) -> dict:
    """商品摘要，对齐 Mock productBrief。"""
    return {
        "id": p.id,
        "title": p.title,
        "categoryId": p.category_id,
        "priceFen": p.price_fen,
        "stock": p.stock,
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
    """购物车行：实时 join 商品（价格/库存以商品表为准），对齐 Mock cartLines。"""
    return {
        "productId": line.product_id,
        "qty": line.qty,
        "checked": bool(line.checked),
        "product": {
            "id": product.id,
            "title": product.title,
            "images": list(product.images or []),
            "priceFen": product.price_fen,
            "stock": product.stock,
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
    """订单详情/列表项，对齐 Mock Order（含 userId 与各时间戳，未发生为 0）。"""
    return {
        "id": o.id,
        "orderNo": o.order_no,
        "userId": o.user_id,
        "items": [order_item(i) for i in o.items],
        "totalFen": o.total_fen,
        "status": o.status,
        "createdAt": o.created_at,
        "shippedAt": o.shipped_at,
        "refundRequestedAt": o.refund_requested_at,
        "cancelledAt": o.cancelled_at,
    }
