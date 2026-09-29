"""管理端用户接口：列表 / 详情 / 余额调整（仅超管）。只读部分任何管理员可用。"""
from flask import Blueprint, g, request

from ....core.response import ok
from ....core.security import admin_required, super_required
from ....services import audit, catalog_service, serializers

bp = Blueprint("admin_user", __name__, url_prefix="/users")


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


@bp.get("")
@admin_required
def list_users():
    """用户列表：keyword 匹配手机号/昵称，分页，含订单数聚合。"""
    data = catalog_service.list_users(
        page=_int_arg("page", 1),
        page_size=_int_arg("pageSize", 20),
        keyword=request.args.get("keyword", ""),
    )
    return ok(data)


@bp.get("/<user_id>")
@admin_required
def user_detail(user_id: str):
    """用户详情：余额/累计消费/最近 10 单。"""
    return ok(catalog_service.get_user_detail_or_404(user_id))


@bp.post("/<user_id>/balance-adjust")
@super_required
def adjust_balance(user_id: str):
    """手动调整用户余额（测试用）：`{amountFen, note}`，amountFen 可负表示扣减。

    仅超管可用（相当于凭空发行余额）；产成的是 source=ADMIN 流水，
    无支付单、不计入仪表盘“充值预收”。
    """
    body = request.get_json(silent=True) or {}
    user = catalog_service.adjust_balance(
        user_id,
        body.get("amountFen"),
        str(body.get("note", "")),
        g.current_admin.id,
    )
    audit.log("user.balance_adjust", user_id, f"{body.get('amountFen')}fen")
    return ok(serializers.public_user(user))
