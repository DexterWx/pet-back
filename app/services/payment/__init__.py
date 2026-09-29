"""支付 provider 工厂：按 PAYMENT_PROVIDER 配置返回实现。

- mock（默认，开发）：预下单即成功；
- wechat：微信商户支付 v3（凭证缺失时在首次调用抛错）。
"""
from flask import current_app

from .base import PaymentProvider
from .mock import MockPaymentProvider


def get_payment_provider() -> PaymentProvider:
    name = current_app.config.get("PAYMENT_PROVIDER", "mock")
    if name == "wechat":
        from .wechat_pay import WechatPayProvider

        return WechatPayProvider()
    return MockPaymentProvider()


__all__ = ["PaymentProvider", "MockPaymentProvider", "get_payment_provider"]
