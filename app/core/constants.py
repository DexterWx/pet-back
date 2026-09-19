"""业务常量。订单状态机与 pet-mini config.orderStatus 完全一致。"""
import time
import uuid


class OrderStatus:
    """订单状态机（对齐 pet-mini/config/index.js orderStatus）：

    PAID_UNSHIPPED 已付款未发货
      -> REFUND_REQUESTED 用户申请退款（可撤回到 PAID_UNSHIPPED）
      -> CANCELLED 商家同意退款/直接取消（终态，回补库存回退销量）
      -> SHIPPED 已发货（不可取消）
    REFUNDING / REFUNDED 为接入真实支付后预留：CANCELLED -> REFUNDING -> REFUNDED
    """

    PAID_UNSHIPPED = "PAID_UNSHIPPED"
    REFUND_REQUESTED = "REFUND_REQUESTED"
    CANCELLED = "CANCELLED"
    SHIPPED = "SHIPPED"
    # 接入真实支付后启用：
    REFUNDING = "REFUNDING"
    REFUNDED = "REFUNDED"

    # “未发货” tab 分组：尚未取消且未发货（含退款申请中）
    UNSHIPPED_GROUP = (PAID_UNSHIPPED, REFUND_REQUESTED)
    # 可取消（商家同意退款/直接取消）的状态
    CANCELLABLE = (PAID_UNSHIPPED, REFUND_REQUESTED)


def now_ms() -> int:
    """当前毫秒时间戳（前端 format.formatTime 直接消费）。"""
    return int(time.time() * 1000)


def gen_id(prefix: str) -> str:
    """生成带前缀的字符串 id，如 u3f2a.../o9b1c...。"""
    return prefix + uuid.uuid4().hex[:16]


def gen_token() -> str:
    return "tk_" + uuid.uuid4().hex
