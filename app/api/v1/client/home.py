"""首页接口：Banner / 功能入口。"""
from flask import Blueprint

from ....core.response import ok
from ....models import Banner

bp = Blueprint("home", __name__, url_prefix="/home")


@bp.get("/banner")
def banner():
    banners = Banner.query.order_by(Banner.sort.asc()).all()
    return ok([{"id": b.id, "image": b.image, "title": b.title} for b in banners])


@bp.get("/entries")
def entries():
    """首页功能入口（静态配置，与 Mock 一致；后续可挪到管理端配置表）。"""
    return ok({
        "squares": [
            {"key": "buy", "title": "点击下单", "sub": "提前下单免排队"},
            {"key": "orders", "title": "订单中心", "sub": ""},
        ],
        "promos": [
            {"key": "contact", "title": "联系我们", "sub": "CONTACT US"},
            {"key": "recharge", "title": "余额充值", "sub": "BALANCE RECHARGE"},
        ],
    })
