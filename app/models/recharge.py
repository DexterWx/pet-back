"""余额充值：档位配置与充值流水。"""
from . import db


class RechargeTier(db.Model):
    """充值档位 {thresholdFen,giftFen,label,sub}（对齐 Mock /user/recharge-tiers）。"""

    __tablename__ = "recharge_tiers"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    threshold_fen = db.Column(db.Integer, nullable=False, default=0)  # 满多少分
    gift_fen = db.Column(db.Integer, nullable=False, default=0)  # 赠送多少分
    label = db.Column(db.String(32), nullable=False, default="")
    sub = db.Column(db.String(32), nullable=False, default="")
    sort = db.Column(db.Integer, nullable=False, default=0)


class RechargeRecord(db.Model):
    """充值流水（本地 Demo 无真实资金流，支付成功后直接入账并记账）。"""

    __tablename__ = "recharge_records"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False, index=True)
    amount_fen = db.Column(db.Integer, nullable=False, default=0)  # 实充金额（分）
    gift_fen = db.Column(db.Integer, nullable=False, default=0)  # 赠送金额（分）
    created_at = db.Column(db.BigInteger, nullable=False, default=0)
