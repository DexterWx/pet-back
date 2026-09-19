"""客服/联系方式接口（占位，与 Mock 一致）。"""
from flask import Blueprint

from ....core.response import ok

bp = Blueprint("contact", __name__, url_prefix="/contact")


@bp.get("/info")
def info():
    return ok({
        "phone": "400-000-0000",
        "wechat": "danghuang-pet",
        "hours": "9:00 - 18:00",
        "notice": "客服功能即将接入微信客服，敬请期待",
    })
