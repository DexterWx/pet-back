"""购物车接口（全部需登录）。

行为对齐 Mock：add/update 校验库存；update 传 qty<=0 即删除该行；
所有写操作返回完整购物车行列表（实时 join 商品价格/库存）。
"""
from flask import Blueprint, g, request

from ....core.response import ApiError, ok
from ....core.security import login_required
from ....models import CartLine, Product, db
from ....services import serializers

bp = Blueprint("cart", __name__, url_prefix="/cart")


def _get_product_or_404(product_id: str) -> Product:
    product = db.session.get(Product, product_id)
    if product is None:
        raise ApiError(404, "商品不存在")
    return product


def _lines_payload(user_id: str) -> list[dict]:
    """当前用户购物车行（join 商品；商品已下架/删除的行自动跳过）。"""
    lines = CartLine.query.filter_by(user_id=user_id).order_by(CartLine.id.asc()).all()
    payload = []
    for line in lines:
        product = db.session.get(Product, line.product_id)
        if product is None:
            continue
        payload.append(serializers.cart_line(line, product))
    return payload


def _int_or_none(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError(400, "数量格式不正确")


@bp.get("")
@login_required
def get_cart():
    return ok(_lines_payload(g.current_user.id))


@bp.post("/add")
@login_required
def add_to_cart():
    body = request.get_json(silent=True) or {}
    product = _get_product_or_404(str(body.get("productId", "")))
    qty = _int_or_none(body.get("qty", 1)) or 1
    if qty <= 0:
        raise ApiError(400, "数量格式不正确")

    line = CartLine.query.filter_by(user_id=g.current_user.id, product_id=product.id).first()
    target = (line.qty if line else 0) + qty
    if target > product.stock:
        raise ApiError(400, "库存不足")
    if line:
        line.qty = target
    else:
        db.session.add(CartLine(user_id=g.current_user.id, product_id=product.id, qty=qty, checked=True))
    db.session.commit()
    return ok(_lines_payload(g.current_user.id))


@bp.post("/update")
@login_required
def update_cart():
    body = request.get_json(silent=True) or {}
    product_id = str(body.get("productId", ""))
    line = CartLine.query.filter_by(user_id=g.current_user.id, product_id=product_id).first()
    if line is None:
        raise ApiError(404, "购物车中不存在该商品")

    qty = _int_or_none(body.get("qty"))
    if qty is not None:
        if qty <= 0:
            db.session.delete(line)
            db.session.commit()
            return ok(_lines_payload(g.current_user.id))
        product = _get_product_or_404(product_id)
        if qty > product.stock:
            raise ApiError(400, "库存不足")
        line.qty = qty

    checked = body.get("checked")
    if checked is not None:
        line.checked = bool(checked)

    db.session.commit()
    return ok(_lines_payload(g.current_user.id))


@bp.post("/remove")
@login_required
def remove_from_cart():
    body = request.get_json(silent=True) or {}
    CartLine.query.filter_by(
        user_id=g.current_user.id, product_id=str(body.get("productId", ""))
    ).delete()
    db.session.commit()
    return ok(_lines_payload(g.current_user.id))
