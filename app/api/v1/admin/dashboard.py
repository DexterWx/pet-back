"""管理端仪表盘：经营概览聚合，支持 当日 / 当月(自然月) / 自定义日期区间 三种口径。

设计原则（轻查询、不给 SQLite 压力）：
- 全部用带索引列（paid_at/created_at/handled_at）的 COUNT/SUM 聚合，一条 SQL 出结果；
- 趋势仅"当月/自定义"计算，且用一条 GROUP BY 天完成，不逐日查库；
- "实时待办"(待发货/待处理售后) 与 "累计资金口径" 不分周期，始终展示。

口径（与前端展示一致）：
- 销售额 = 区间内支付、且当前未整单退的订单 total_fen 合计（含运费）；
- 退款额 = 区间内完成退款（after_sales.status=REFUNDED）的 refund_fen 合计；
- 成交买家数 = 区间内有已支付订单的去重用户数；新客数 = 区间内新注册用户数；
- 累计区（不随周期/退款/注销变）：总用户数、总订单数、总流水（均为历史累计，含已退款）。
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, request
from sqlalchemy import func

from ....core.constants import (
    AfterSaleStatus,
    OrderStatus,
)
from ....core.response import ApiError, ok
from ....core.security import admin_required
from ....models import AfterSale, Order, User, db

bp = Blueprint("admin_dashboard", __name__, url_prefix="/dashboard")

# 计入"销售额/订单数"的订单状态（已支付且未整单退）
_SALES_STATUSES = (OrderStatus.PAID_UNSHIPPED, OrderStatus.SHIPPED, OrderStatus.COMPLETED)
# 曾支付过的订单状态（算总流水/总订单数/成交买家，**含已退款、不扣减**）
_PAID_STATUSES = (
    OrderStatus.PAID_UNSHIPPED, OrderStatus.SHIPPED, OrderStatus.COMPLETED,
    OrderStatus.REFUNDING, OrderStatus.REFUNDED,
)


def _day_start_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day).timestamp() * 1000)


def _resolve_range():
    """按 period 解析 [start_ms, end_ms) 与展示信息。custom 需 start/end=YYYY-MM-DD。"""
    period = (request.args.get("period") or "today").strip().lower()
    today = date.today()

    if period == "month":
        first = today.replace(day=1)
        nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)  # 下月 1 号
        return period, _day_start_ms(first), _day_start_ms(nxt), first.isoformat(), today.isoformat(), "本月"
    if period == "custom":
        start_s = (request.args.get("start") or "").strip()
        end_s = (request.args.get("end") or "").strip()
        try:
            start_d = datetime.strptime(start_s, "%Y-%m-%d").date()
            end_d = datetime.strptime(end_s, "%Y-%m-%d").date()
        except ValueError:
            raise ApiError(400, "请选择完整的开始与结束日期（YYYY-MM-DD）")
        if start_d > end_d:
            raise ApiError(400, "开始日期不能晚于结束日期")
        if (end_d - start_d).days > 366:
            raise ApiError(400, "自定义区间最长 366 天")
        return period, _day_start_ms(start_d), _day_start_ms(end_d + timedelta(days=1)), start_s, end_s, f"{start_s} ~ {end_s}"
    # 默认 today
    return "today", _day_start_ms(today), _day_start_ms(today + timedelta(days=1)), today.isoformat(), today.isoformat(), "今日"


def _scalar_sum(col, *filters) -> int:
    q = db.session.query(func.coalesce(func.sum(col), 0))
    for f in filters:
        q = q.filter(f)
    return int(q.scalar() or 0)


def _scalar_count(*filters) -> int:
    q = db.session.query(func.count(Order.id))
    for f in filters:
        q = q.filter(f)
    return int(q.scalar() or 0)


def _trend(start_ms: int, end_ms: int) -> list[dict]:
    """按天聚合已支付订单的销售额与单数（一条 GROUP BY，不逐日查库）。"""
    day = func.strftime("%Y-%m-%d", func.datetime(Order.paid_at / 1000, "unixepoch", "localtime"))
    rows = (
        db.session.query(day.label("d"), func.count(Order.id), func.coalesce(func.sum(Order.total_fen), 0))
        .filter(Order.status.in_(_SALES_STATUSES), Order.paid_at >= start_ms, Order.paid_at < end_ms)
        .group_by("d").order_by("d").all()
    )
    return [{"date": r[0], "orderCount": int(r[1]), "salesFen": int(r[2])} for r in rows]


@bp.get("")
@admin_required
def dashboard():
    period, start_ms, end_ms, start_str, end_str, label = _resolve_range()
    in_range_paid = (Order.paid_at >= start_ms, Order.paid_at < end_ms)

    order_count = _scalar_count(Order.status.in_(_SALES_STATUSES), *in_range_paid)
    sales_fen = _scalar_sum(Order.total_fen, Order.status.in_(_SALES_STATUSES), *in_range_paid)
    buyer_count = int(
        db.session.query(func.count(func.distinct(Order.user_id)))
        .filter(Order.status.in_(_PAID_STATUSES), *in_range_paid).scalar() or 0
    )
    new_customers = int(db.session.query(func.count(User.id)).filter(
        User.created_at >= start_ms, User.created_at < end_ms).scalar() or 0)
    refund_fen = _scalar_sum(AfterSale.refund_fen,
                             AfterSale.status == AfterSaleStatus.REFUNDED,
                             AfterSale.handled_at >= start_ms, AfterSale.handled_at < end_ms)
    refund_count = int(db.session.query(func.count(AfterSale.id)).filter(
        AfterSale.status == AfterSaleStatus.REFUNDED,
        AfterSale.handled_at >= start_ms, AfterSale.handled_at < end_ms).scalar() or 0)

    result = {
        "period": period,
        "range": {"start": start_str, "end": end_str, "label": label},
        "metrics": {
            "orderCount": order_count,
            "salesFen": sales_fen,
            "buyerCount": buyer_count,
            "newCustomerCount": new_customers,
            "refundFen": refund_fen,
            "refundCount": refund_count,
            "avgOrderFen": int(sales_fen / order_count) if order_count else 0,
        },
        # 实时待办（不分周期）
        "pending": {
            "pendingShipCount": int(db.session.query(func.count(Order.id)).filter(
                Order.status == OrderStatus.PAID_UNSHIPPED).scalar() or 0),
            "pendingAfterSaleCount": int(db.session.query(func.count(AfterSale.id)).filter(
                AfterSale.status == AfterSaleStatus.PENDING).scalar() or 0),
        },
        # 累计口径（不随退款/注销扣减）
        "fundamentals": {
            "userCount": int(db.session.query(func.count(User.id)).scalar() or 0),
            "totalOrderCount": int(db.session.query(func.count(Order.id)).filter(
                Order.status.in_(_PAID_STATUSES)).scalar() or 0),
            "totalFlowFen": _scalar_sum(Order.total_fen, Order.status.in_(_PAID_STATUSES)),
        },
    }
    # 趋势仅当月/自定义（今日无意义）
    if period in ("month", "custom"):
        result["trend"] = _trend(start_ms, end_ms)
    return ok(result)
