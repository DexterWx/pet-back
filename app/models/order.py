"""订单与订单行（下单时的商品快照）。

对齐 pet-mini Mock Order：
{id,orderNo,userId,items[{productId,title,image,priceFen,qty}],totalFen,status,
 createdAt,shippedAt,refundRequestedAt,cancelledAt}
时间戳均为毫秒整数，未发生时为 0（与 Mock 一致）。
"""
from . import db


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.String(32), primary_key=True)  # o + uuid hex
    order_no = db.Column(db.String(32), unique=True, nullable=False, index=True)  # NO+毫秒时间戳
    user_id = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False, index=True)
    total_fen = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(32), nullable=False, index=True)  # OrderStatus
    created_at = db.Column(db.BigInteger, nullable=False, default=0)
    shipped_at = db.Column(db.BigInteger, nullable=False, default=0)
    refund_requested_at = db.Column(db.BigInteger, nullable=False, default=0)
    cancelled_at = db.Column(db.BigInteger, nullable=False, default=0)

    items = db.relationship(
        "OrderItem", backref="order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )


class OrderItem(db.Model):
    """订单行：下单时锁定商品标题/图片/单价快照，后续商品改价不影响历史订单。"""

    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_id = db.Column(db.String(32), db.ForeignKey("orders.id"), nullable=False, index=True)
    product_id = db.Column(db.String(32), nullable=False)
    title = db.Column(db.String(128), nullable=False)
    image = db.Column(db.String(512), nullable=False, default="")
    price_fen = db.Column(db.Integer, nullable=False, default=0)
    qty = db.Column(db.Integer, nullable=False, default=1)
