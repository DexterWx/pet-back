"""管理端充值档位接口（全部需管理员登录）：列表 / 创建 / 更新 / 删除。

业务规则在 catalog_service：金额单位为分、门槛必须 > 0、且**必须至少保留一个档位**
（否则充值入口会空，默认档「充 1000 赠 100」在新档建立前不可删）。
"""
from flask import Blueprint, request

from ....core.response import ApiError, ok
from ....core.security import admin_required
from ....services import audit, catalog_service

bp = Blueprint("admin_recharge_tier", __name__, url_prefix="/recharge-tiers")


@bp.get("")
@admin_required
def list_tiers():
    return ok(catalog_service.list_recharge_tiers())


@bp.post("")
@admin_required
def create_tier():
    body = request.get_json(silent=True) or {}
    tier = catalog_service.create_recharge_tier(body)
    audit.log("recharge_tier.create", str(tier.id), tier.label)
    return ok({
        "id": tier.id,
        "thresholdFen": tier.threshold_fen,
        "giftFen": tier.gift_fen,
        "label": tier.label,
        "sub": tier.sub,
        "sort": tier.sort,
    })


@bp.put("/<int:tier_id>")
@admin_required
def update_tier(tier_id: int):
    body = request.get_json(silent=True) or {}
    tier = catalog_service.update_recharge_tier(tier_id, body)
    audit.log("recharge_tier.update", str(tier.id), tier.label)
    return ok({
        "id": tier.id,
        "thresholdFen": tier.threshold_fen,
        "giftFen": tier.gift_fen,
        "label": tier.label,
        "sub": tier.sub,
        "sort": tier.sort,
    })


@bp.delete("/<tier_id>")
@admin_required
def delete_tier(tier_id: str):
    try:
        pk = int(tier_id)
    except (TypeError, ValueError):
        raise ApiError(400, "档位 ID 不合法")
    catalog_service.delete_recharge_tier(pk)
    audit.log("recharge_tier.delete", str(pk))
    return ok(None)
