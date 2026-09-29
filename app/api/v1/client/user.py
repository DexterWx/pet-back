"""用户接口（全部需登录）：资料 / 余额 / 充值 / 收藏。"""
from flask import Blueprint, g, request

from ....core.constants import RechargeSource, RechargeStatus, now_ms
from ....core.response import ApiError, ok
from ....core.security import login_required
from ....models import Favorite, Product, RechargeRecord, RechargeTier, db
from ....services import payment_service, serializers
from ....services.wechat import get_phone_number

bp = Blueprint("user", __name__, url_prefix="/user")


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


@bp.get("/balance")
@login_required
def balance():
    u = g.current_user
    return ok({"balanceFen": u.balance_fen})


@bp.post("/profile")
@login_required
def update_profile():
    """更新用户资料（当前仅昵称）；昵称 trim 后非空且 20 字。

    头像不再持久化：小程序侧 chooseAvatar 仅本地展示，不入库；服务端不接收 avatar。
    """
    body = request.get_json(silent=True) or {}
    u = g.current_user

    if "nickname" in body:
        nickname = str(body.get("nickname") or "").strip()[:20]
        if not nickname:
            raise ApiError(400, "昵称不能为空")
        u.nickname = nickname

    db.session.commit()
    return ok(serializers.public_user(u))


@bp.post("/phone/rebind")
@login_required
def rebind_phone():
    """换绑手机号：重新走微信 getPhoneNumber 授权（取当前微信号绑定手机）。

    未接短信服务商，故不能改成任意号码，只能重新授权取微信担保的号。
    """
    body = request.get_json(silent=True) or {}
    phone = get_phone_number(str(body.get("phoneCode", "")))
    g.current_user.phone = phone
    db.session.commit()
    return ok(serializers.public_user(g.current_user))


@bp.get("/recharge-tiers")
@login_required
def recharge_tiers():
    """可充档位（用户只能从这些档位里点选，不可自输金额）。"""
    tiers = RechargeTier.query.order_by(RechargeTier.sort.asc(), RechargeTier.id.asc()).all()
    return ok([
        {
            "id": t.id,
            "thresholdFen": t.threshold_fen,
            "giftFen": t.gift_fen,
            "label": t.label,
            "sub": t.sub,
        }
        for t in tiers
    ])


@bp.post("/recharge/prepay")
@login_required
def recharge_prepay():
    """按选定档位发起充值预下单。

    金额与赠送额都由服务端根据 `tierId` 算定（不信任前端）；
    **余额入账发生在支付回调到账之后**，本接口不会直接加余额。
    """
    body = request.get_json(silent=True) or {}
    try:
        tier_id = int(body.get("tierId"))
    except (TypeError, ValueError):
        raise ApiError(400, "请选择充值档位")

    tier = db.session.get(RechargeTier, tier_id)
    if tier is None or tier.threshold_fen <= 0:
        raise ApiError(400, "充值档位不存在")

    record, result = payment_service.initiate_recharge(g.current_user, tier)
    return ok({
        "paymentNo": record.payment_no,
        "amountFen": record.amount_fen,
        "giftFen": record.gift_fen,
        "status": record.status,
        "settled": record.status == RechargeStatus.SUCCESS,  # mock 即时到账
        "balanceFen": g.current_user.balance_fen,
        "mock": bool(result.get("mock")),
        "payParams": result.get("payParams") or {},
    })


@bp.get("/recharge/record")
@login_required
def recharge_record_query():
    """轮询充值单到账状态（小程序拉起支付后以服务端为准）。"""
    record = payment_service.recharge_record_of(
        g.current_user.id, str(request.args.get("paymentNo", ""))
    )
    if record is None:
        raise ApiError(404, "充值单不存在")
    return ok({
        "paymentNo": record.payment_no,
        "status": record.status,
        "amountFen": record.amount_fen,
        "giftFen": record.gift_fen,
        "paidAt": record.paid_at,
        "balanceFen": g.current_user.balance_fen,
    })


@bp.get("/recharge-records")
@login_required
def recharge_records():
    """我的充值记录（仅用户自己成功支付的充值，倒序分页）。

    排除 source=ADMIN 的后台手动调整（测试用余额），不应让用户看到内部调账流水。
    """
    page = max(_int_arg("page", 1), 1)
    page_size = max(_int_arg("pageSize", 20), 1)
    query = (
        RechargeRecord.query
        .filter_by(
            user_id=g.current_user.id,
            status=RechargeStatus.SUCCESS,
            source=RechargeSource.USER,
        )
        .order_by(RechargeRecord.created_at.desc())
    )
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return ok({
        "list": [
            {
                "id": r.id,
                "amountFen": r.amount_fen,
                "giftFen": r.gift_fen,
                "totalFen": r.amount_fen + r.gift_fen,
                "provider": r.provider,
                "paidAt": r.paid_at,
                "createdAt": r.created_at,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    })


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
