"""订单与订单行（下单时的商品快照）。

对齐 pet-mini Mock Order：
{id,orderNo,userId,items[{productId,title,image,priceFen,qty}],totalFen,status,
 createdAt,shippedAt,refundRequestedAt,cancelledAt}
时间戳均为毫秒整数，未发生时为 0（与 Mock 一致）。
"""
from . import db


class Order(db.Model):
    __tablename__ = "orders"

    # 复合索引：对应当前三类高频查询（单列索引由字段 index=True 继续生成，冗余但无害，写入量极小）。
    # 存量库不会由 create_all 自动补建，已登记在 app/__init__.py:_auto_migrate() 里幂等创建。
    __table_args__ = (
        db.Index("ix_orders_user_status_created", "user_id", "status", "created_at"),  # 小程序订单列表：用户+状态筛选、时间倒序
        db.Index("ix_orders_status_created", "status", "created_at"),  # 管理端订单列表 / 售后 tab
        db.Index("ix_orders_status_paid", "status", "paid_at"),  # 仪表盘：按已支付状态 + 支付时间区间聚合
    )

    id = db.Column(db.String(32), primary_key=True)  # o + uuid hex
    order_no = db.Column(db.String(32), unique=True, nullable=False, index=True)  # NO+毫秒+4位随机（core.constants.gen_order_no）
    user_id = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False, index=True)
    total_fen = db.Column(db.Integer, nullable=False, default=0)  # 应付总额 = 商品金额 + 运费
    # 金额快照：total_fen = goods_total_fen + freight_fen；下单时按当时运费规则算定并固化，
    # 之后改运费配置不影响历史订单（与商品单价/标题快照同理）。
    goods_total_fen = db.Column(db.Integer, nullable=False, default=0)  # 商品金额合计（分，不含运费）
    freight_fen = db.Column(db.Integer, nullable=False, default=0)  # 运费（分；自提或达包邮门槛为 0）
    status = db.Column(db.String(32), nullable=False, index=True)  # OrderStatus

    # 配送方式：EXPRESS 快递 / SELF_PICKUP 自提（DeliveryType）
    delivery_type = db.Column(db.String(16), nullable=False, default="EXPRESS")
    # 收货/取货信息：下单时从地址簿快照写入，后续地址修改不影响历史订单（自提可无详细地址）
    receiver_name = db.Column(db.String(64), nullable=False, default="")
    receiver_phone = db.Column(db.String(32), nullable=False, default="")
    receiver_address = db.Column(db.String(255), nullable=False, default="")
    # 物流信息：由管理端录入。快递填公司+单号；自提自定义一个提货单号（carrier 可空）
    carrier = db.Column(db.String(64), nullable=False, default="")
    ship_no = db.Column(db.String(64), nullable=False, default="")

    created_at = db.Column(db.BigInteger, nullable=False, default=0)
    paid_at = db.Column(db.BigInteger, nullable=False, default=0)  # 支付成功时间（PENDING_PAY -> PAID_UNSHIPPED）
    shipped_at = db.Column(db.BigInteger, nullable=False, default=0)
    completed_at = db.Column(db.BigInteger, nullable=False, default=0)  # 交易完成时间（SHIPPED -> COMPLETED）
    complete_source = db.Column(db.String(8), nullable=False, default="")  # 完成方式：USER 用户确认 / AUTO 发货满 N 天自动 / '' 未完成
    refund_requested_at = db.Column(db.BigInteger, nullable=False, default=0)
    cancelled_at = db.Column(db.BigInteger, nullable=False, default=0)
    refunded_at = db.Column(db.BigInteger, nullable=False, default=0)  # 商家强制退款完成（REFUNDED）时间

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


class OrderConfig(db.Model):
    """交易配置（全局一套，单行 id=1）：目前只有发货后自动确认收货/退款窗口天数。

    与 shipping_configs 同模式：商家可在管理后台调整，默认 7 天；自提与快递一致。
    无行时回退到环境变量 ORDER_AUTO_COMPLETE_DAYS（再缺省 7）。
    """

    __tablename__ = "order_configs"

    id = db.Column(db.Integer, primary_key=True)  # 固定 1
    auto_complete_days = db.Column(db.Integer, nullable=False, default=7)  # 发货后自动确认收货天数（=退款窗口）
    updated_at = db.Column(db.BigInteger, nullable=False, default=0)
