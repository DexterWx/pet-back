"""微信支付 v3 provider（直连商户，JSAPI/小程序）。基于 wechatpayv3 库封装签名/验签/AEAD 解密。

凭证全部来自 .env（见 config.py）。凭证缺失时首次使用即抛明确错误，避免静默走错分支。
真实链路需线上凭证 + 可达 notify_url 联调；本地用 PAYMENT_PROVIDER=mock 跑通。
"""
import json
import os
import time
import uuid

from flask import current_app

from ...core.response import ApiError
from .base import PaymentProvider

_client_cache = {}


def _load(path: str) -> str:
    if not path or not os.path.exists(path):
        raise ApiError(500, f"微信支付密钥文件缺失或不可读：{path or '(未配置)'}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _get_client():
    cfg = current_app.config
    mchid = cfg["WXPAY_MCHID"]
    if not mchid:
        raise ApiError(500, "未配置 WXPAY_MCHID（PAYMENT_PROVIDER=wechat 必填）")
    key = (mchid, cfg["WXPAY_CERT_SERIAL_NO"])
    if key in _client_cache:
        return _client_cache[key]

    from wechatpayv3 import WeChatPay, WeChatPayType

    private_key = _load(cfg["WXPAY_PRIVATE_KEY_PATH"])
    public_key = _load(cfg["WXPAY_PUBLIC_KEY_PATH"]) if cfg["WXPAY_PUBLIC_KEY_PATH"] else None
    cert_dir = cfg["WXPAY_CERT_DIR"] or os.path.join(cfg.get("UPLOAD_DIR", "."), "..", "wxcert")

    client = WeChatPay(
        wechatpay_type=WeChatPayType.MINIPROG,
        mchid=mchid,
        private_key=private_key,
        cert_serial_no=cfg["WXPAY_CERT_SERIAL_NO"],
        appid=cfg["WECHAT_APPID"],
        apiv3_key=cfg["WXPAY_APIV3_KEY"],
        notify_url=cfg["WXPAY_NOTIFY_URL"] or None,
        cert_dir=cert_dir if not public_key else None,
        public_key=public_key,
        public_key_id=cfg["WXPAY_PUBLIC_KEY_ID"] or None,
    )
    _client_cache[key] = client
    return client


class WechatPayProvider(PaymentProvider):
    name = "wechat"

    def create_prepay(self, payment, order=None, description: str = "") -> dict:
        client = _get_client()
        # 订单支付默认用订单号作描述；充值无订单，靠传入的 description
        title = description or (f"宠物商城-{order.order_no}" if order is not None else "宠物商城")
        code, text = client.pay(
            description=title[:127],
            out_trade_no=payment.payment_no,
            amount={"total": payment.amount_fen, "currency": "CNY"},
            payer={"openid": payment.payer_openid},
        )
        data = json.loads(text) if text else {}
        if code != 200 or "prepay_id" not in data:
            raise ApiError(500, f"微信统一下单失败: {text or code}")
        prepay_id = data["prepay_id"]
        payment.prepay_id = prepay_id

        appid = current_app.config["WECHAT_APPID"]
        timestamp = str(int(time.time()))
        nonce_str = uuid.uuid4().hex.upper()
        package = f"prepay_id={prepay_id}"
        pay_sign = client.sign([appid, timestamp, nonce_str, package])
        pay_params = {
            "appId": appid,
            "timeStamp": timestamp,
            "nonceStr": nonce_str,
            "package": package,
            "signType": "RSA",
            "paySign": pay_sign,
        }
        return {"mock": False, "payParams": pay_params}

    def parse_notify(self, headers, body) -> dict | None:
        client = _get_client()
        data = client.callback(headers, body)  # 验签失败返回 None
        if not data:
            return None
        resource = data.get("resource") or {}
        amount = resource.get("amount") or {}
        return {
            "payment_no": resource.get("out_trade_no"),
            "transaction_id": resource.get("transaction_id"),
            "success": resource.get("trade_state") == "SUCCESS",
            "amount_fen": (amount.get("total") or 0),
            "raw": resource,
        }

    def refund(self, payment, after_sale) -> str:
        client = _get_client()
        out_refund_no = f"R{after_sale.id}"
        code, text = client.refund(
            out_refund_no=out_refund_no,
            amount={"refund": after_sale.refund_fen, "total": payment.amount_fen, "currency": "CNY"},
            transaction_id=payment.transaction_id,
            reason=(after_sale.reason or after_sale.admin_note or "退款")[:80],
            # 不传 notify_url 微信就不会推退款回调，/payments/refunds/notify 会变成死路径（REFUNDING 只能靠后台查单补偿）
            notify_url=current_app.config.get("WXPAY_REFUND_NOTIFY_URL") or None,
        )
        data = json.loads(text) if text else {}
        if code not in (200, 204) or not data.get("refund_id"):
            raise ApiError(500, f"微信退款失败: {text or code}")
        return data["refund_id"]

    def parse_refund_notify(self, headers, body) -> dict | None:
        """解析退款结果通知（callback 通用验签+解密，resource 为退款字段）。"""
        client = _get_client()
        data = client.callback(headers, body)
        if not data:
            return None
        resource = data.get("resource") or {}
        return {
            "out_refund_no": resource.get("out_refund_no"),
            "refund_id": resource.get("refund_id"),
            "success": resource.get("refund_status") == "SUCCESS",
            "raw": resource,
        }

    def query_refund(self, out_refund_no: str) -> str | None:
        """主动查退款单状态（掉单补偿）。返回 SUCCESS/PROCESSING/... 或 None。"""
        client = _get_client()
        code, text = client.query_refund(out_refund_no=out_refund_no)
        data = json.loads(text) if text else {}
        if code != 200 or not data:
            return None
        return data.get("status") or data.get("refund_status")
