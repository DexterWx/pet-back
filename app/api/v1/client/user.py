"""用户接口（全部需登录）：资料 / 余额 / 充值 / 收藏。"""
from flask import Blueprint, g, request

from ....core.constants import now_ms
from ....core.response import ApiError, ok
from ....core.security import login_required
from ....models import Favorite, Product, RechargeRecord, RechargeTier, db
from ....services import serializers

bp = Blueprint("user", __name__, url_prefix="/user")


@bp.get("/balance")
@login_required
def balance():
    u = g.current_user
    return ok({"balanceFen": u.balance_fen, "points": u.points, "coupons": u.coupons})


@bp.post("/profile")
@login_required
def update_profile():
    """更新头像昵称（微信头像昵称填写能力）；昵称 trim 后非空且 ≤20 字。"""
    body = request.get_json(silent=True) or {}
    u = g.current_user

    if "nickname" in body:
        nickname = str(body.get("nickname") or "").strip()[:20]
        if not nickname:
            raise ApiError(400, "昵称不能为空")
        u.nickname = nickname
    if "avatar" in body:
        u.avatar = str(body.get("avatar") or "")

    db.session.commit()
    return ok(serializers.public_user(u))


@bp.get("/recharge-tiers")
@login_required
def recharge_tiers():
    tiers = RechargeTier.query.order_by(RechargeTier.sort.asc()).all()
    return ok([
        {
            "thresholdFen": t.threshold_fen,
            "giftFen": t.gift_fen,
            "label": t.label,
            "sub": t.sub,
        }
        for t in tiers
    ])


@bp.post("/recharge")
@login_required
def recharge():
    """充值入账（Demo 无真实资金流：支付成功后直接入账并记流水）。

    赠送金额以服务端档位为准（取满足门槛的最高档），不信任前端传入的 giftFen。
    """
    body = request.get_json(silent=True) or {}
    try:
        amount_fen = int(body.get("amountFen", 0))
    except (TypeError, ValueError):
        amount_fen = 0
    if amount_fen <= 0:
        raise ApiError(400, "充值金额不正确")

    # 服务端计算赠送金额：满足 threshold 的最高档
    tier = (
        RechargeTier.query.filter(RechargeTier.threshold_fen <= amount_fen)
        .order_by(RechargeTier.threshold_fen.desc())
        .first()
    )
    gift_fen = tier.gift_fen if tier else 0

    u = g.current_user
    u.balance_fen += amount_fen + gift_fen
    db.session.add(RechargeRecord(
        user_id=u.id, amount_fen=amount_fen, gift_fen=gift_fen, created_at=now_ms(),
    ))
    db.session.commit()
    return ok({"balanceFen": u.balance_fen})


@bp.get("/favorites")
@login_required
def favorites():
    rows = (
        Favorite.query.filter_by(user_id=g.current_user.id)
        .order_by(Favorite.id.asc())
        .all()
    )
    items = []
    for row in rows:
        product = db.session.get(Product, row.product_id)
        if product is not None:
            items.append(serializers.product_brief(product))
    return ok(items)


@bp.post("/favorites/toggle")
@login_required
def toggle_favorite():
    body = request.get_json(silent=True) or {}
    product_id = str(body.get("productId", ""))
    if db.session.get(Product, product_id) is None:
        raise ApiError(404, "商品不存在")

    row = Favorite.query.filter_by(user_id=g.current_user.id, product_id=product_id).first()
    if row:
        db.session.delete(row)
        favorited = False
    else:
        db.session.add(Favorite(user_id=g.current_user.id, product_id=product_id, created_at=now_ms()))
        favorited = True
    db.session.commit()

    ids = [
        f.product_id
        for f in Favorite.query.filter_by(user_id=g.current_user.id).order_by(Favorite.id.asc()).all()
    ]
    return ok({"favorited": favorited, "ids": ids})
