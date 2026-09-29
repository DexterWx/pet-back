"""管理端 CSV 导出：订单 / 商品 / 用户（后端生成，utf-8-sig 便于 Excel 打开中文）。

只导出运营需要的列；金额统一转元保留两位。数据量为当前全量（本地阶段可接受）。
"""
import csv
import io
import time

from flask import Blueprint, Response

from ....core.constants import OrderStatus
from ....core.security import admin_required
from ....models import Category, Order, Product, User

bp = Blueprint("admin_export", __name__, url_prefix="/export")


def _csv_response(filename: str, header: list[str], rows: list[list]) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    # utf-8-sig 带 BOM，Excel 打开中文不乱码
    data = buf.getvalue().encode("utf-8-sig")
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _yuan(fen) -> str:
    return f"{(fen or 0) / 100:.2f}"


def _ts(ms) -> str:
    if not ms:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ms / 1000))


_STATUS_TEXT = {
    OrderStatus.PENDING_PAY: "待付款",
    OrderStatus.PAID_UNSHIPPED: "待发货",
    OrderStatus.SHIPPED: "待收货",
    OrderStatus.COMPLETED: "已完成",
    OrderStatus.CLOSED: "已关闭",
    OrderStatus.REFUNDING: "退款中",
    OrderStatus.REFUNDED: "已退款",
}


@bp.get("/orders")
@admin_required
def export_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    rows = [
        [
            o.order_no,
            _STATUS_TEXT.get(o.status, o.status),
            "自提" if o.delivery_type == "SELF_PICKUP" else "快递",
            _yuan(o.goods_total_fen),
            _yuan(o.freight_fen),
            _yuan(o.total_fen),
            o.receiver_name,
            o.receiver_phone,
            _ts(o.created_at),
            _ts(o.paid_at),
        ]
        for o in orders
    ]
    return _csv_response(
        "orders.csv",
        ["订单号", "状态", "配送", "商品金额(元)", "运费(元)", "合计(元)", "收货人", "电话", "下单时间", "支付时间"],
        rows,
    )


@bp.get("/products")
@admin_required
def export_products():
    cats = {c.id: c.name for c in Category.query.all()}
    products = Product.query.order_by(Product.sort.asc(), Product.id.asc()).all()
    rows = [
        [
            p.id,
            p.title,
            cats.get(p.category_id, ""),
            _yuan(p.price_fen),
            p.sold,
            "上架" if p.on_sale else "下架",
            p.sort,
        ]
        for p in products
    ]
    return _csv_response(
        "products.csv",
        ["商品ID", "标题", "分类", "价格(元)", "销量", "状态", "排序"],
        rows,
    )


@bp.get("/users")
@admin_required
def export_users():
    users = User.query.order_by(User.created_at.desc()).all()
    rows = []
    for u in users:
        order_count = Order.query.filter_by(user_id=u.id).count()
        rows.append([
            u.id,
            u.nickname or "",
            u.phone or "",
            _yuan(u.balance_fen),
            order_count,
            _ts(u.created_at),
        ])
    return _csv_response(
        "users.csv",
        ["用户ID", "昵称", "手机号", "余额(元)", "订单数", "注册时间"],
        rows,
    )
