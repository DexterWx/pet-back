"""企业微信群机器人通知：新订单已支付 / 用户提交退款申请。

设计要点：
- **尽力而为**：任何异常（网络/超时/配置缺失/接口报错）只记 warning 日志，**绝不抛出**，
  避免通知失败连带影响支付回调、下单、退款申请等主流程。
- 配置来自 .env：`WECOM_WEBHOOK_URL`（空则静默跳过）、`WECOM_NOTIFY_ENABLED=false` 可整体关闭
  （本地开发与冒烟测试务必关掉，否则会往真实群里刷测试消息）。
- 调用时机必须在**数据已 commit 之后**，否则群里的单子在库里还不存在。
"""
from flask import current_app
import requests

# 通知不能拖慢主流程：短超时（秒）
_TIMEOUT = 3


def _yuan(fen) -> str:
    return f"{(fen or 0) / 100:.2f}"


def _delivery_label(delivery_type: str) -> str:
    return "自提" if delivery_type == "SELF_PICKUP" else "快递"


def _post(content: str) -> bool:
    """向群机器人发一条文本消息。返回是否已发出（失败仅记日志，不抛异常）。"""
    cfg = current_app.config
    url = cfg.get("WECOM_WEBHOOK_URL") or ""
    if not url:
        return False
    if not cfg.get("WECOM_NOTIFY_ENABLED", True):
        current_app.logger.info("企业微信通知已禁用（WECOM_NOTIFY_ENABLED=false），跳过")
        return False
    try:
        resp = requests.post(
            url,
            json={"msgtype": "text", "text": {"content": content[:2000]}},
            timeout=_TIMEOUT,
        )
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if data.get("errcode") not in (0, None):
            current_app.logger.warning("企业微信通知被拒: %s", data)
            return False
        return True
    except Exception as e:  # noqa: BLE001 通知失败绝不影响业务
        current_app.logger.warning("企业微信通知异常（已忽略）: %s", e)
        return False


def notify_new_order(order) -> bool:
    """支付成功的新订单提醒。"""
    goods = "；".join(f"{i.title}×{i.qty}" for i in (order.items or []))
    lines = [
        "🛒 新订单已支付",
        f"订单号：{order.order_no}",
        f"金额：¥{_yuan(order.total_fen)}",
        f"配送：{_delivery_label(order.delivery_type)}",
        f"商品：{goods or '-'}",
        f"收货人：{order.receiver_name} {order.receiver_phone}",
    ]
    if order.receiver_address:
        lines.append(f"地址：{order.receiver_address}")
    return _post("\n".join(lines))


def notify_refund_request(after_sale, order) -> bool:
    """用户提交的退款申请提醒（待管理员到后台审核）。"""
    lines = [
        "⚠️ 新的退款申请",
        f"订单号：{order.order_no}",
        f"退款金额：¥{_yuan(after_sale.refund_fen)}",
        f"原因：{after_sale.reason or '未填写'}",
        f"收货人：{order.receiver_name} {order.receiver_phone}",
        "请前往管理后台「售后处理」审核。",
    ]
    return _post("\n".join(lines))
