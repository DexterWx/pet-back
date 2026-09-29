"""Mock 支付 provider：本地开发用，预下单即视为支付成功（由 payment_service 直接置已付）。

⚠️ 仅用于 PAYMENT_PROVIDER=mock（开发）。生产必须 PAYMENT_PROVIDER=wechat，
否则任何人下单都会被即时标记为已付（无真实资金）。
"""
from .base import PaymentProvider


class MockPaymentProvider(PaymentProvider):
    name = "mock"

    def create_prepay(self, payment, order=None, description: str = "") -> dict:
        # 无需真实拉起；payment_service 收到 mock=True 会直接标记支付成功
        return {"mock": True, "payParams": {}}

    def parse_notify(self, headers, body) -> dict | None:
        return None  # Mock 不走外部回调

    def refund(self, payment, after_sale) -> str:
        return f"mockrefund_{after_sale.id}"

    def parse_refund_notify(self, headers, body) -> dict | None:
        return None  # Mock 不走外部退款回调

    def query_refund(self, out_refund_no: str) -> str | None:
        return "SUCCESS"  # Mock 退款视为即时成功，补偿查单可直接收尾
