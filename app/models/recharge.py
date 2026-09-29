"""余额充值：档位配置与充值流水（充值单自身就是待支付/已支付的交易记录）。"""
from . import db


class RechargeTier(db.Model):
    """充值档位 {id,thresholdFen,giftFen,label,sub}：用户只能点选档位，不可自输金额。"""

    __tablename__ = "recharge_tiers"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    threshold_fen = db.Column(db.Integer, nullable=False, default=0)  # 满多少分
    gift_fen = db.Column(db.Integer, nullable=False, default=0)  # 赠送多少分
    label = db.Column(db.String(32), nullable=False, default="")
    sub = db.Column(db.String(32), nullable=False, default="")
    sort = db.Column(db.Integer, nullable=False, default=0)


class RechargeRecord(db.Model):
    """充值单/流水：走真实微信支付，到账由回调驱动（不再直接入账）。

    - payment_no 以 `RC` 前缀，支付回调据此路由到充值而非订单；
    - 金额/赠送额均在服务端由档位算定，不信任前端；
    - **充值单不提供退款入口**（按业务约定走客服线下处理）；
    - source=ADMIN 为后台管理员手动调整（测试用途，可正可负），
      无支付单、不计入“充值预收”，与用户真实付款严格区分。
    """

    __tablename__ = "recharge_records"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False, index=True)
    amount_fen = db.Column(db.Integer, nullable=False, default=0)  # 实充金额（分；后台调减时为负）
    gift_fen = db.Column(db.Integer, nullable=False, default=0)  # 赠送金额（分）
    created_at = db.Column(db.BigInteger, nullable=False, default=0)

    # 以下为支付相关字段（与 payments 表同构语义，因为 order_id 外键不适用于充值）
    payment_no = db.Column(db.String(32), unique=True, nullable=True, index=True)  # out_trade_no（RC 前缀）
    transaction_id = db.Column(db.String(64), nullable=True)  # 微信支付订单号
    prepay_id = db.Column(db.String(64), nullable=False, default="")
    provider = db.Column(db.String(16), nullable=False, default="mock")  # mock | wechat | admin
    status = db.Column(db.String(16), nullable=False, default="PENDING", index=True)  # RechargeStatus
    payer_openid = db.Column(db.String(64), nullable=False, default="")
    tier_id = db.Column(db.Integer, nullable=True)  # 所用档位（档位后续变更不影响历史）
    paid_at = db.Column(db.BigInteger, nullable=False, default=0)

    # 来源与操作人（区分用户付款与后台手动调整）
    source = db.Column(db.String(8), nullable=False, default="USER", index=True)  # USER | ADMIN
    admin_id = db.Column(db.String(32), nullable=False, default="")  # 操作管理员（source=ADMIN 时）
    note = db.Column(db.String(255), nullable=False, default="")  # 调整原因/备注
