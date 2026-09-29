"""业务常量。订单状态机与 pet-mini config.orderStatus 完全一致。"""
import time
import uuid


class OrderStatus:
    """订单状态机（与 pet-mini config.orderStatus 保持一致）：

    PENDING_PAY 待付款（下单即此态）
      -> 支付成功 -> PAID_UNSHIPPED 待发货
      -> 超时/取消 -> CLOSED 已关闭（终态）
    PAID_UNSHIPPED -> 管理员发货 -> SHIPPED 已发货/待收货
    SHIPPED -> 用户确认收货 或 发货满 N 天自动确认 -> COMPLETED 已完成（正向履约终态）
    售后退款（after_sales 表驱动）：全额退成功 -> REFUNDED（终态）

    退款窗口：未发货随时可申请；已发货仅发货后 N 天内可申请；一旦已完成不可自助退（仅管理员可强制退）；
    已被驳回过的订单永久不能再自助申请。N = config.ORDER_AUTO_COMPLETE_DAYS。
    """

    PENDING_PAY = "PENDING_PAY"
    PAID_UNSHIPPED = "PAID_UNSHIPPED"
    SHIPPED = "SHIPPED"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"
    REFUNDING = "REFUNDING"
    REFUNDED = "REFUNDED"

    # 可支付（待付款）
    PAYABLE = (PENDING_PAY,)
    # 可发货：仅待发货
    SHIPPABLE = (PAID_UNSHIPPED,)
    # 可确认收货：已发货（是否超期、是否有在途售后由 order_service 判定）
    CONFIRMABLE = (SHIPPED,)
    # 管理员可发起退款（含强制退后门）：已付款及以后的履约态
    ADMIN_REFUNDABLE = (PAID_UNSHIPPED, SHIPPED, COMPLETED)
    # 终态（不可再变更）
    FINAL = (CLOSED, REFUNDED, COMPLETED)


class AfterSaleStatus:
    """售后（退款）单状态。"""

    PENDING = "PENDING"      # 用户已申请，待管理员处理
    REJECTED = "REJECTED"    # 管理员驳回
    REFUNDING = "REFUNDING"  # 管理员已同意，退款处理中（C 阶段微信退款回调置 REFUNDED）
    REFUNDED = "REFUNDED"    # 退款完成


class AfterSaleSource:
    """售后发起方。"""

    USER = "USER"    # 用户申请（整单全额退）
    ADMIN = "ADMIN"  # 管理员发起（金额自定义，可部分退）


class DeliveryType:
    """配送方式：快递 / 自提。自提单由管理端自定义一个提货单号录入，流程与快递一致（发货后不可退）。"""

    EXPRESS = "EXPRESS"
    SELF_PICKUP = "SELF_PICKUP"


class PaymentStatus:
    """支付单状态（payments 表）。"""

    CREATED = "CREATED"  # 已创建/预下单，待支付
    SUCCESS = "SUCCESS"  # 支付成功（回调置此态）
    CLOSED = "CLOSED"    # 已关闭


class RechargeStatus:
    """充值单状态（recharge_records 表）。余额仅在 SUCCESS 时入账。"""

    PENDING = "PENDING"  # 已预下单，待支付
    SUCCESS = "SUCCESS"  # 已到账（回调/本地 mock 驱动），已加余额
    CLOSED = "CLOSED"    # 已关闭（未支付作废）


class RechargeSource:
    """余额变动来源（recharge_records.source）。决不能混算：
    USER 是真实收款（充值预收），ADMIN 是后台手动调整（测试用，无资金流入）。
    """

    USER = "USER"    # 用户自行充值（微信支付/本地 mock）
    ADMIN = "ADMIN"  # 管理员后台手动调整余额（可正可负）


class PayMethod:
    """下单支付方式。二者不可混用：余额不足则整单改走微信。

    balance 不弹收银台，服务端直接扣余额并标记已付；充值单不可退款，故无对应退款分支。
    """

    WECHAT = "wechat"    # 微信支付（默认，兼容未传 method 的老请求）
    BALANCE = "balance"  # 余额支付


def now_ms() -> int:
    """当前毫秒时间戳（前端 format.formatTime 直接消费）。"""
    return int(time.time() * 1000)


def gen_id(prefix: str) -> str:
    """生成带前缀的字符串 id，如 u3f2a.../o9b1c...。"""
    return prefix + uuid.uuid4().hex[:16]


def gen_token() -> str:
    return "tk_" + uuid.uuid4().hex


def gen_order_no() -> str:
    """业务订单号：NO + 毫秒时间戳 + 4 位随机十六进制。

    仅用毫秒时间戳在同一毫秒并发下单会撞唯一约束，因此补随机位。
    例：NO1790603918192D629（长度 19，小于列上限 32）。
    """
    return f"NO{now_ms()}{uuid.uuid4().hex[:4].upper()}"
