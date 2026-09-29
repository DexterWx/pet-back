"""支付编排：Payment 记录 + provider 调用 + 订单转已付 + 退款联动 + 充值单。

幂等要点：支付回调可重复投递，只允许 CREATED→SUCCESS 单向、且只对 PENDING_PAY 订单生效。
两种支付主体共用一个回调地址，按 out_trade_no 前缀路由：`RC` 为充值单，其余为订单。
支付方式不可混用：余额支付走 `pay_with_balance`（直接扣余额，不起渠道），不足则整单改走微信。
"""
import uuid

from ..core.constants import (
    AfterSaleStatus,
    OrderStatus,
    PayMethod,
    PaymentStatus,
    RechargeStatus,
    gen_id,
    now_ms,
)
from ..core.response import ApiError
from ..models import AfterSale, Order, Payment, RechargeRecord, User, db
from . import notify, order_service
from .payment import get_payment_provider


def _new_payment_no() -> str:
    return "P" + uuid.uuid4().hex[:20]  # ≤32，字符集安全，全局唯一


def _new_recharge_no() -> str:
    """充值单 out_trade_no：RC 前缀，供回调路由区分于订单支付。"""
    return "RC" + uuid.uuid4().hex[:18]


def _new_balance_no() -> str:
    """余额支付流水号：BAL 前缀，不对渠道发起。"""
    return "BAL" + uuid.uuid4().hex[:18]


def initiate_payment(order: Order, payer_openid: str):
    """对某订单发起支付：取/建 CREATED 支付单 -> provider 预下单。

    返回 (payment, result)。result['mock']=True 表示本地即时成功，本函数已直接置订单已付。
    """
    if order.status != OrderStatus.PENDING_PAY:
        raise ApiError(400, "订单状态不可支付")

    provider = get_payment_provider()
    payment = Payment.query.filter_by(order_id=order.id, status=PaymentStatus.CREATED).first()
    if payment is None:
        payment = Payment(
            id=gen_id("pm"),
            order_id=order.id,
            payment_no=_new_payment_no(),
            provider=provider.name,
            amount_fen=order.total_fen,
            status=PaymentStatus.CREATED,
            payer_openid=payer_openid or "",
            created_at=now_ms(),
        )
        db.session.add(payment)
        db.session.commit()

    result = provider.create_prepay(payment, order)
    db.session.commit()

    if result.get("mock"):
        _settle_payment(payment, transaction_id="mocktxn_" + payment.payment_no)
    return payment, result


def _settle_payment(payment: Payment, transaction_id: str = "", raw: dict | None = None) -> bool:
    """标记支付单成功并驱动订单转已付款；幂等（已 SUCCESS 直接返回 False 表示无变更）。

    仅在订单**本次**真的转为已付时推企业微信新订单通知（重复回调不重发）。
    """
    if payment.status == PaymentStatus.SUCCESS:
        return False
    order = db.session.get(Order, payment.order_id)
    payment.status = PaymentStatus.SUCCESS
    payment.transaction_id = transaction_id or payment.transaction_id
    payment.paid_at = now_ms()
    if raw is not None:
        payment.raw_notify = raw
    settled = False
    if order is not None and order.status == OrderStatus.PENDING_PAY:
        order_service.mark_paid(order)
        settled = True
    db.session.commit()
    if settled:
        # commit 后通知；notify 内部保证不抛异常
        notify.notify_new_order(order)
    return True


def handle_payment_notify(headers, body):
    """处理支付结果回调（验签/解密 + 幂等）。返回 (是否已处理, 说明)。

    同一地址同时接收「订单支付」与「充值到账」通知，按 out_trade_no 前缀 `RC` 路由。
    """
    provider = get_payment_provider()
    data = provider.parse_notify(headers, body)
    if not data or not data.get("payment_no"):
        raise ApiError(400, "回调验签或解析失败")

    payment_no = data["payment_no"]
    if payment_no.startswith("RC"):
        return _handle_recharge_notify(payment_no, data)

    payment = Payment.query.filter_by(payment_no=payment_no).first()
    if payment is None:
        raise ApiError(404, "支付单不存在")

    if not data.get("success"):
        return False, "非成功通知，已忽略"
    if payment.status == PaymentStatus.SUCCESS:
        return True, "已处理（幂等）"
    if data.get("amount_fen") and data["amount_fen"] != payment.amount_fen:
        raise ApiError(400, "回调金额与支付单不一致")

    _settle_payment(payment, transaction_id=data.get("transaction_id") or "", raw=data.get("raw"))
    return True, "OK"


def paid_payment_of(order_id: str) -> Payment | None:
    return Payment.query.filter_by(order_id=order_id, status=PaymentStatus.SUCCESS).first()


def refund_after_sale(after_sale) -> str:
    """对 REFUNDING 售后单发起渠道退款，回填退款单号。

    同步渠道（无支付单/余额/mock）发起后立即 finalize（REFUNDING→REFUNDED）；
    微信为异步：发起后保持 REFUNDING，等 /payments/refunds/notify 回调或主动查单补偿收尾。
    按**支付单实际 provider** 分流：余额支付退回用户余额（不调渠道）。
    """
    if after_sale.status != AfterSaleStatus.REFUNDING:
        return ""
    payment = paid_payment_of(after_sale.order_id)
    if payment is None:
        order_service.finalize_refund(after_sale)  # 未接支付/未支付：记账即到账
        return ""
    if payment.provider == PayMethod.BALANCE:
        user = db.session.get(User, after_sale.user_id)
        if user is not None:
            user.balance_fen += after_sale.refund_fen
        after_sale.wx_refund_id = f"balance_{after_sale.id}"
        db.session.commit()
        order_service.finalize_refund(after_sale)
        return after_sale.wx_refund_id
    provider = get_payment_provider()
    wx_refund_id = provider.refund(payment, after_sale)
    after_sale.wx_refund_id = wx_refund_id
    db.session.commit()
    if provider.name == "mock":
        order_service.finalize_refund(after_sale)  # mock 同步到账
    # wechat：保持 REFUNDING，等退款回调或查单补偿
    return wx_refund_id


def handle_refund_notify(headers, body):
    """处理微信退款结果回调（验签/解密 + 幂等）。返回 (是否已处理, 说明)。

    out_refund_no 约定为 'R'+after_sale.id，据此反查售后单。
    """
    provider = get_payment_provider()
    data = provider.parse_refund_notify(headers, body)
    if not data or not data.get("out_refund_no"):
        raise ApiError(400, "退款回调验签或解析失败")
    out_refund_no = data["out_refund_no"]
    if not out_refund_no.startswith("R"):
        return False, "非本系统退款单，已忽略"
    after_sale = db.session.get(AfterSale, out_refund_no[1:])
    if after_sale is None:
        raise ApiError(404, "售后单不存在")
    if not data.get("success"):
        return False, "退款未成功通知，已忽略（可人工/补偿处理）"
    if after_sale.status != AfterSaleStatus.REFUNDING:
        return True, "已处理（幂等）"
    if data.get("refund_id"):
        after_sale.wx_refund_id = data["refund_id"]
    order_service.finalize_refund(after_sale)
    return True, "OK"


def compensate_refund(after_sale) -> str:
    """主动查单补偿：对 REFUNDING 售后单查渠道退款状态，SUCCESS 则 finalize。

    用于回调丢失/延迟时人工触发（管理端“同步退款状态”）。返回处理后状态。
    """
    if after_sale.status != AfterSaleStatus.REFUNDING:
        return after_sale.status
    payment = paid_payment_of(after_sale.order_id)
    if payment is None or payment.provider == PayMethod.BALANCE:
        order_service.finalize_refund(after_sale)  # 无渠道/余额本应同步到账，兼底收尾
        return after_sale.status
    provider = get_payment_provider()
    if provider.query_refund(f"R{after_sale.id}") == "SUCCESS":
        order_service.finalize_refund(after_sale)
    return after_sale.status


# ---------- 余额支付（下单） ----------

def pay_with_balance(order: Order, user: User) -> Payment:
    """余额支付待付款订单：服务端校余额 -> 扣减 -> 建已付支付单 -> 订单转已付。

    与微信支付**不可混用**：余额不足直接 400，由前端引导改走微信支付。
    扣余额与订单转态在同一事务内提交（mark_paid 会再 commit一次），失败则整体回滚。
    """
    if order.status != OrderStatus.PENDING_PAY:
        raise ApiError(400, "订单状态不可支付")
    if order.total_fen <= 0:
        raise ApiError(400, "订单金额异常，请联系客服")
    if user.balance_fen < order.total_fen:
        raise ApiError(400, f"余额不足（当前 ¥{user.balance_fen / 100:.2f}，需 ¥{order.total_fen / 100:.2f}），请改选微信支付")

    paid_at = now_ms()
    payment = Payment(
        id=gen_id("pm"),
        order_id=order.id,
        payment_no=_new_balance_no(),
        transaction_id=None,
        prepay_id="",
        provider=PayMethod.BALANCE,
        amount_fen=order.total_fen,
        status=PaymentStatus.SUCCESS,
        payer_openid=user.openid,
        paid_at=paid_at,
        created_at=paid_at,
    )
    user.balance_fen -= order.total_fen
    db.session.add(payment)
    db.session.commit()

    order_service.mark_paid(order)  # 转 PAID_UNSHIPPED + 累加销量
    notify.notify_new_order(order)  # commit 后通知，失败不影响已完成的支付
    return payment


# ---------- 余额充值（真实微信支付） ----------

def initiate_recharge(user: User, tier) -> tuple[RechargeRecord, dict]:
    """按选定档位创建充值单并预下单。金额/赠送额均由服务端档位算定，不信任前端。

    mock provider 会即时到账（仅开发）；wechat 下返回 payParams，入账由支付回调驱动。
    """
    provider = get_payment_provider()
    record = RechargeRecord(
        user_id=user.id,
        amount_fen=tier.threshold_fen,
        gift_fen=tier.gift_fen,
        tier_id=tier.id,
        status=RechargeStatus.PENDING,
        payment_no=_new_recharge_no(),
        provider=provider.name,
        payer_openid=user.openid,
        created_at=now_ms(),
    )
    db.session.add(record)
    db.session.commit()

    desc = f"宠物商城-余额充值¥{record.amount_fen / 100:.2f}"
    result = provider.create_prepay(record, None, description=desc)
    db.session.commit()
    if result.get("mock"):
        _settle_recharge(record, transaction_id="mocktxn_" + record.payment_no)
    return record, result


def _settle_recharge(record: RechargeRecord, transaction_id: str = "") -> bool:
    """充值到账：幂等（已 SUCCESS 返回 False）；在此步才将余额入账（含赠送）。"""
    if record.status == RechargeStatus.SUCCESS:
        return False
    record.status = RechargeStatus.SUCCESS
    record.transaction_id = transaction_id or record.transaction_id
    record.paid_at = now_ms()
    user = db.session.get(User, record.user_id)
    if user is not None:
        user.balance_fen += record.amount_fen + record.gift_fen
    db.session.commit()
    return True


def _handle_recharge_notify(payment_no: str, data: dict):
    """充值到账回调（幂等 + 金额校验）。"""
    record = RechargeRecord.query.filter_by(payment_no=payment_no).first()
    if record is None:
        raise ApiError(404, "充值单不存在")
    if not data.get("success"):
        return False, "非成功通知，已忽略"
    if record.status == RechargeStatus.SUCCESS:
        return True, "已处理（幂等）"
    if data.get("amount_fen") and data["amount_fen"] != record.amount_fen:
        raise ApiError(400, "回调金额与充值单不一致")
    _settle_recharge(record, transaction_id=data.get("transaction_id") or "")
    return True, "OK"


def recharge_record_of(user_id: str, payment_no: str) -> RechargeRecord | None:
    """查本人充值单（供小程序支付后轮询到账）。"""
    if not payment_no:
        return None
    return RechargeRecord.query.filter_by(payment_no=payment_no, user_id=user_id).first()
