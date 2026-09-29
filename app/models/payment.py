"""支付单：一笔订单可能多次预下单（重试/换支付），每次一行。

- payment_no = 传给微信的 out_trade_no（本系统生成，唯一，≤32，字符集安全）；
- transaction_id = 微信支付订单号（支付成功后回调回填，唯一）；
- 支付与订单解耦：订单 orders.paid_at 由支付回调驱动；退款在 after_sales 记录。
"""
from . import db


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.String(32), primary_key=True)  # pm + uuid hex
    order_id = db.Column(db.String(32), db.ForeignKey("orders.id"), nullable=False, index=True)
    payment_no = db.Column(db.String(32), unique=True, nullable=False, index=True)  # out_trade_no
    transaction_id = db.Column(db.String(64), unique=True, nullable=True)  # 微信支付订单号（成功后回填）
    prepay_id = db.Column(db.String(64), nullable=False, default="")
    provider = db.Column(db.String(16), nullable=False, default="mock")  # mock | wechat
    amount_fen = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(16), nullable=False, default="CREATED", index=True)  # PaymentStatus
    payer_openid = db.Column(db.String(64), nullable=False, default="")
    raw_notify = db.Column(db.JSON, nullable=True)  # 回调解密原文（排障/对账）
    paid_at = db.Column(db.BigInteger, nullable=False, default=0)
    created_at = db.Column(db.BigInteger, nullable=False, default=0)
