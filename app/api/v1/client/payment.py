"""支付接口：小程序发起支付 + 微信支付/退款结果回调。

- POST /orders/:id/pay  （需登录）对待付款订单发起支付；body.method = 'wechat'（默认）| 'balance'。
  两种支付方式**不可混用**：余额不足则 400，由前端引导改走微信。
- POST /payments/notify （免登录，验签）微信支付成功回调 -> 幂等驱动订单转已付 / 充值到账。
- POST /payments/refunds/notify （免登录，验签）微信退款成功回调 -> 幂等驱动 REFUNDING→REFUNDED。
"""
from flask import Blueprint, g, request

from ....core.constants import PayMethod
from ....core.response import ApiError, ok
from ....core.security import login_required
from ....services import order_service, payment_service

bp = Blueprint("client_payment", __name__)


@bp.post("/orders/<order_id>/pay")
@login_required
def pay_order(order_id: str):
    """支付待付款订单：按 method 分派余额支付或微信预下单。"""
    body = request.get_json(silent=True) or {}
    method = str(body.get("method") or body.get("payMethod") or PayMethod.WECHAT).strip().lower()
    if method not in (PayMethod.WECHAT, PayMethod.BALANCE):
        raise ApiError(400, "支付方式不正确")

    order = order_service.get_user_order(order_id, g.current_user.id)

    if method == PayMethod.BALANCE:
        payment_service.pay_with_balance(order, g.current_user)
        order = order_service.get_user_order(order_id, g.current_user.id)
        return ok({
            "paid": order.status != "PENDING_PAY",
            "status": order.status,
            "method": PayMethod.BALANCE,
            "mock": False,
            "payParams": {},
        })

    payment, result = payment_service.initiate_payment(order, g.current_user.openid)
    # 重新读取订单状态（mock provider 会即时置为已付款）
    order = order_service.get_user_order(order_id, g.current_user.id)
    return ok({
        "paid": order.status != "PENDING_PAY",
        "status": order.status,
        "method": PayMethod.WECHAT,
        "paymentNo": payment.payment_no,
        "mock": bool(result.get("mock")),
        "payParams": result.get("payParams") or {},
    })


@bp.post("/payments/notify")
def payment_notify():
    """微信支付结果通知（免登录）。验签+解密由 provider 负责；成功返回 200 停止重试。"""
    headers = dict(request.headers)
    body = request.get_data(as_text=True)
    try:
        handled, _msg = payment_service.handle_payment_notify(headers, body)
    except ApiError:
        # 处理失败：返回 500 结构，微信会按策略重试
        raise
    return ok({"handled": handled})


@bp.post("/payments/refunds/notify")
def refund_notify():
    """微信退款结果通知（免登录）。按 out_refund_no(R+售后单id) 反查并幂等收尾 REFUNDING→REFUNDED。"""
    headers = dict(request.headers)
    body = request.get_data(as_text=True)
    handled, _msg = payment_service.handle_refund_notify(headers, body)
    return ok({"handled": handled})


# 便于管理端/排障查看某订单支付单（可选）
@bp.get("/orders/<order_id>/payment")
@login_required
def order_payment(order_id: str):
    order_service.get_user_order(order_id, g.current_user.id)
    payment = payment_service.paid_payment_of(order_id)
    if payment is None:
        return ok(None)
    return ok({
        "paymentNo": payment.payment_no,
        "transactionId": payment.transaction_id,
        "status": payment.status,
        "amountFen": payment.amount_fen,
        "paidAt": payment.paid_at,
    })
