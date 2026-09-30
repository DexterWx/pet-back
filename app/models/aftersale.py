"""售后（退款）单：与订单履约状态解耦，记录退款申请/处理全过程。

- source=USER：用户在订单上申请退款（整单全额），status 从 PENDING 起，等管理员同意/驳回；
- source=ADMIN：管理员直接发起退款（金额自定义，可部分退），无需用户申请。
- 退款是否"完成"由管理员决定；真实微信退款在 C 阶段接入（wx_refund_id 记录微信退款单号）。
"""
from . import db


class AfterSale(db.Model):
    __tablename__ = "after_sales"

    # 待处理售后列表：按 status 筛选 + created_at 排序（存量库由 _auto_migrate() 补建）
    __table_args__ = (
        db.Index("ix_after_sales_status_created", "status", "created_at"),
    )

    id = db.Column(db.String(32), primary_key=True)  # as + uuid hex
    order_id = db.Column(db.String(32), db.ForeignKey("orders.id"), nullable=False, index=True)
    user_id = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False, index=True)
    source = db.Column(db.String(8), nullable=False, default="USER")  # AfterSaleSource
    refund_fen = db.Column(db.Integer, nullable=False, default=0)  # 退款金额（分）
    reason = db.Column(db.String(255), nullable=False, default="")  # 用户申请原因 / 管理员退款说明
    status = db.Column(db.String(16), nullable=False, default="PENDING", index=True)  # AfterSaleStatus
    admin_id = db.Column(db.String(32), nullable=False, default="")  # 处理管理员
    admin_note = db.Column(db.String(255), nullable=False, default="")  # 处理备注
    wx_refund_id = db.Column(db.String(64), nullable=False, default="")  # 微信退款单号（C 阶段填）
    handled_at = db.Column(db.BigInteger, nullable=False, default=0)
    created_at = db.Column(db.BigInteger, nullable=False, default=0)

    order = db.relationship("Order", backref=db.backref("after_sales", order_by="AfterSale.created_at.desc()"))
