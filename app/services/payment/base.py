"""支付 provider 抽象接口。

统一五能力：预下单(create_prepay)、解析支付回调(parse_notify)、退款(refund)、
解析退款回调(parse_refund_notify)、主动查退款单(query_refund)。
新增其他支付渠道时实现本接口并在 get_payment_provider() 注册即可，业务层无改动。
"""


class PaymentProvider:
    name = "base"

    def create_prepay(self, payment, order=None, description: str = "") -> dict:
        """预下单，返回给小程序拉起支付的参数。

        `payment` 只需暴露 `payment_no / amount_fen / payer_openid`（订单支付单与充值单均满足）；
        `order` 可为 None（如余额充值不属于订单），此时必须传 `description` 作为商品描述。
        约定返回：{'mock': bool, 'payParams': {...}} ；mock=True 表示本地即时成功、无需拉起。
        """
        raise NotImplementedError

    def parse_notify(self, headers, body) -> dict | None:
        """解析并验签支付结果通知。

        返回归一化 dict：{'payment_no','transaction_id','success','amount_fen','raw'}；
        验签/解密失败返回 None（调用方据此拒绝）。
        """
        raise NotImplementedError

    def refund(self, payment, after_sale) -> str:
        """发起退款，返回渠道退款单号（用于对账）。"""
        raise NotImplementedError

    def parse_refund_notify(self, headers, body) -> dict | None:
        """解析并验签退款结果通知。

        返回归一化 dict：{'out_refund_no','refund_id','success','raw'}；验签/解密失败返回 None。
        out_refund_no 约定为 'R'+after_sale.id，供回调反查售后单。
        """
        raise NotImplementedError

    def query_refund(self, out_refund_no: str) -> str | None:
        """主动查询渠道退款状态（掉单补偿用）。返回 'SUCCESS'/'PROCESSING'/... 或 None。"""
        raise NotImplementedError
