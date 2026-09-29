"""收货地址簿接口（全部需登录，按用户隔离）。

约定：首个地址自动设为默认；设为默认会清除该用户其他地址的默认标记；
删除默认地址后，若还剩地址则把最早创建的一条置为默认。
"""
from flask import Blueprint, g, request

from ....core.constants import gen_id, now_ms
from ....core.response import ApiError, ok
from ....core.security import login_required
from ....models import Address, db
from ....services import serializers

bp = Blueprint("address", __name__, url_prefix="/addresses")


def _own_or_404(address_id: str) -> Address:
    address = db.session.get(Address, address_id)
    if address is None or address.user_id != g.current_user.id:
        raise ApiError(404, "地址不存在")
    return address


def _clear_default(user_id: str) -> None:
    Address.query.filter_by(user_id=user_id, is_default=True).update({"is_default": False})


def _read_fields(body: dict) -> dict:
    receiver_name = str(body.get("receiverName", "")).strip()
    phone = str(body.get("phone", "")).strip()
    if not receiver_name:
        raise ApiError(400, "请填写收货人姓名")
    if not phone:
        raise ApiError(400, "请填写联系电话")
    return {
        "receiver_name": receiver_name[:64],
        "phone": phone[:32],
        "province": str(body.get("province", "")).strip()[:32],
        "city": str(body.get("city", "")).strip()[:32],
        "district": str(body.get("district", "")).strip()[:32],
        "detail": str(body.get("detail", "")).strip()[:255],
    }


def _payload_list(user_id: str) -> list[dict]:
    rows = (
        Address.query.filter_by(user_id=user_id)
        .order_by(Address.is_default.desc(), Address.created_at.asc())
        .all()
    )
    return [serializers.address(a) for a in rows]


@bp.get("")
@login_required
def list_addresses():
    return ok(_payload_list(g.current_user.id))


@bp.post("/add")
@login_required
def add_address():
    body = request.get_json(silent=True) or {}
    fields = _read_fields(body)
    user_id = g.current_user.id
    is_first = Address.query.filter_by(user_id=user_id).count() == 0
    is_default = bool(body.get("isDefault")) or is_first
    if is_default:
        _clear_default(user_id)

    now = now_ms()
    address = Address(
        id=gen_id("ad"), user_id=user_id, is_default=is_default, created_at=now, updated_at=now, **fields
    )
    db.session.add(address)
    db.session.commit()
    return ok(_payload_list(user_id))


@bp.post("/update")
@login_required
def update_address():
    body = request.get_json(silent=True) or {}
    address = _own_or_404(str(body.get("id", "")))
    for key, value in _read_fields(body).items():
        setattr(address, key, value)

    if "isDefault" in body:
        want_default = bool(body.get("isDefault"))
        if want_default:
            _clear_default(address.user_id)
        address.is_default = want_default
        # 不允许没有任何默认地址：取消默认时若为唯一默认，则强制保持默认
        if not want_default and not Address.query.filter_by(user_id=address.user_id, is_default=True).first():
            address.is_default = True

    address.updated_at = now_ms()
    db.session.commit()
    return ok(_payload_list(address.user_id))


@bp.post("/remove")
@login_required
def remove_address():
    body = request.get_json(silent=True) or {}
    address = _own_or_404(str(body.get("id", "")))
    user_id = address.user_id
    was_default = address.is_default
    db.session.delete(address)
    db.session.commit()

    # 删除了默认地址：把剩下最早的一条补为默认
    if was_default and not Address.query.filter_by(user_id=user_id, is_default=True).first():
        fallback = (
            Address.query.filter_by(user_id=user_id).order_by(Address.created_at.asc()).first()
        )
        if fallback is not None:
            fallback.is_default = True
            db.session.commit()
    return ok(_payload_list(user_id))
