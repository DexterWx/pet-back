"""认证接口：微信登录 / 当前用户快照。"""
from flask import Blueprint, g, request

from ....core.constants import gen_id, gen_token, now_ms
from ....core.response import ok
from ....core.security import login_required
from ....models import ApiToken, User, db
from ....services import serializers
from ....services.wechat import code2session

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.post("/wechat-login")
def wechat_login():
    """微信一键登录：code 换 openid -> 按 openid 找/建用户 -> 轮换 token。

    返回 {token, user, isNewUser}，与 Mock 一致；首次登录即注册，无独立注册流程。
    """
    body = request.get_json(silent=True) or {}
    openid = code2session(str(body.get("code", "")))

    user = User.query.filter_by(openid=openid).first()
    is_new_user = user is None
    if is_new_user:
        user = User(
            id=gen_id("u"),
            openid=openid,
            nickname="微信用户",
            avatar="",
            balance_fen=0,
            points=0,
            coupons=0,
            created_at=now_ms(),
        )
        db.session.add(user)
    else:
        # 已存在直接登录：删除旧 token（轮换，旧 token 即失效）
        ApiToken.query.filter_by(user_id=user.id).delete()

    token = gen_token()
    db.session.add(ApiToken(user_id=user.id, token=token, created_at=now_ms()))
    db.session.commit()

    return ok({"token": token, "user": serializers.public_user(user), "isNewUser": is_new_user})


@bp.get("/profile")
@login_required
def profile():
    """当前登录用户快照（不含 openid/token）。"""
    return ok(serializers.public_user(g.current_user))
