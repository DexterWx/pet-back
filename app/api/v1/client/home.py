"""首页接口：Banner / 功能入口。"""
from flask import Blueprint

from ....core.response import ok
from ....models import Banner

bp = Blueprint("home", __name__, url_prefix="/home")


@bp.get("/banner")
def banner():
    """首页轮播（仅启用项，按 sort 升序）。"""
    banners = Banner.query.filter_by(enabled=True).order_by(Banner.sort.asc()).all()
    return ok([
        {"id": b.id, "image": b.image, "title": b.title, "productId": b.product_id or ""}
        for b in banners
    ])


@bp.get("/entries")
def entries():
    """首页功能入口（静态配置；后续可迁移到管理端配置表）。

    首页不再放“联系我们”入口（客服统一从商品详情底栏 / 「我的」页的原生
    `<button open-type="contact">` 拉起微信客服会话），promos 仅保留充值入口。
    """
    return ok({
        "squares": [
            {"key": "buy", "title": "点击下单", "sub": "提前下单免排队"},
            {"key": "orders", "title": "订单中心", "sub": ""},
        ],
        "promos": [
            {"key": "recharge", "title": "余额充值", "sub": "BALANCE RECHARGE"},
        ],
    })
