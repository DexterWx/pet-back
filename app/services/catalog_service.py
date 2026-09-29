"""管理端目录业务：商品 / 分类 / 用户 / 管理员账号的 CRUD 规则。

接口层（api/v1/admin）只做参数解析，业务规则集中在此，错误一律抛 ApiError。
关键约定（见 HANDOFF / SPEC）：
- 下架 = on_sale=False（保留在库、可重新上架）；删除 = 物理删库 + 删 OSS 图片（省钱，弱一致）。
- 删除商品前清购物车/收藏引用行；OrderItem 是下单快照（product_id 无外键），不受影响。
- 管理员多账号：不能删/禁自己，不能删/禁最后一个启用的超管。
"""
import uuid

from flask import current_app

from ..core.constants import (
    RechargeSource,
    RechargeStatus,
    gen_id,
    now_ms,
)
from ..core.response import ApiError
from ..models import (
    AdminToken,
    AdminUser,
    Banner,
    CartLine,
    Category,
    Favorite,
    Order,
    Product,
    RechargeRecord,
    RechargeTier,
    User,
    db,
)
from . import serializers
from .storage import get_storage

# 商品/分类新 id 前缀（与种子 id 风格一致：p001 / c_dried，新建用 p+hex / c+hex）
_PRODUCT_ID_PREFIX = "p"
_CATEGORY_ID_PREFIX = "c"


def _gen_short_id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:8]


# ---------- 商品 ----------

def list_products(
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    category_id: str = "",
    on_sale: str = "",
) -> dict:
    """管理端商品列表（可看下架）：分页 + keyword(标题) + categoryId + onSale(true/false/'')。"""
    query = Product.query
    if category_id and category_id != "all":
        query = query.filter(Product.category_id == category_id)
    if keyword:
        query = query.filter(Product.title.like(f"%{keyword.strip()}%"))
    if on_sale in ("true", "false"):
        query = query.filter(Product.on_sale == (on_sale == "true"))

    page = max(page, 1)
    page_size = max(page_size, 1)
    total = query.count()
    items = (
        query.order_by(Product.sort.asc(), Product.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "list": [serializers.admin_product(p) for p in items],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    }


def get_product_or_404(product_id: str) -> Product:
    product = db.session.get(Product, product_id)
    if product is None:
        raise ApiError(404, "商品不存在")
    return product


def _clean_product_fields(body: dict, *, partial: bool, product: Product | None = None) -> dict:
    """校验并归一化商品可写字段。partial=True 时仅处理传入的键（更新用）。"""
    fields: dict = {}

    def _present(key: str) -> bool:
        return (not partial) or (key in body)

    if _present("title"):
        title = str(body.get("title", "")).strip()
        if not title:
            raise ApiError(400, "商品标题不能为空")
        fields["title"] = title[:128]

    if _present("categoryId"):
        category_id = str(body.get("categoryId", "")).strip()
        if not category_id or db.session.get(Category, category_id) is None:
            raise ApiError(400, "所选分类不存在")
        fields["category_id"] = category_id

    if _present("priceFen"):
        try:
            price_fen = int(body.get("priceFen", 0))
        except (TypeError, ValueError):
            price_fen = 0
        if price_fen <= 0:
            raise ApiError(400, "价格必须大于 0")
        fields["price_fen"] = price_fen

    if _present("images"):
        raw = body.get("images", [])
        if not isinstance(raw, list) or any(not isinstance(x, str) for x in raw):
            raise ApiError(400, "图片格式不正确")
        fields["images"] = [x.strip() for x in raw if x.strip()]

    if _present("desc"):
        fields["description"] = str(body.get("desc", ""))

    if _present("sort"):
        try:
            fields["sort"] = int(body.get("sort", 0))
        except (TypeError, ValueError):
            fields["sort"] = 0

    if _present("onSale"):
        fields["on_sale"] = bool(body.get("onSale"))

    # 创建时必填校验
    if not partial:
        for key, msg in (("title", "商品标题不能为空"), ("category_id", "请选择分类")):
            if not fields.get(key):
                raise ApiError(400, msg)
        if fields.get("price_fen", 0) <= 0:
            raise ApiError(400, "价格必须大于 0")

    return fields


def create_product(body: dict) -> Product:
    """创建商品：id 自动生成 p+hex8，sold 从 0 起，默认上架。"""
    fields = _clean_product_fields(body, partial=False)
    product = Product(
        id=_gen_short_id(_PRODUCT_ID_PREFIX),
        title=fields["title"],
        category_id=fields["category_id"],
        price_fen=fields["price_fen"],
        sold=0,
        images=fields.get("images", []),
        description=fields.get("description", ""),
        sort=fields.get("sort", 0),
        on_sale=fields.get("on_sale", True),
    )
    db.session.add(product)
    db.session.commit()
    return product


def update_product(product_id: str, body: dict) -> Product:
    """更新商品：仅覆盖传入字段（partial）。"""
    product = get_product_or_404(product_id)
    fields = _clean_product_fields(body, partial=True)
    for key, value in fields.items():
        setattr(product, key, value)
    db.session.commit()
    return product


def set_on_sale(product_id: str, on_sale: bool) -> Product:
    """上/下架：仅改 on_sale，商品仍保留在库。"""
    product = get_product_or_404(product_id)
    product.on_sale = bool(on_sale)
    db.session.commit()
    return product


def delete_product(product_id: str) -> None:
    """物理删除商品：清购物车/收藏引用 -> 删记录并提交 -> 删 OSS 图片（弱一致，失败记日志）。

    省钱要点：删除商品时同步删其全部图片对象（用户确认「直接全删」）。
    OrderItem 为下单快照，product_id 无外键，历史订单不受影响。
    """
    product = get_product_or_404(product_id)
    images = list(product.images or [])

    CartLine.query.filter_by(product_id=product_id).delete(synchronize_session=False)
    Favorite.query.filter_by(product_id=product_id).delete(synchronize_session=False)
    db.session.delete(product)
    db.session.commit()  # 先落库删除，再清图片：图片删除失败不影响商品已删

    storage = get_storage()
    for url in images:
        try:
            if not storage.delete_image(url):
                current_app.logger.info("商品图片未删除（非本存储或已不存在）：%s", url)
        except Exception as e:  # noqa: BLE001 弱一致，绝不阻断
            current_app.logger.warning("删除商品图片失败 %s：%s", url, e)


# ---------- 分类 ----------

def list_categories() -> list[dict]:
    """分类列表（含每类商品数），按 sort 升序。"""
    categories = Category.query.order_by(Category.sort.asc(), Category.id.asc()).all()
    result = []
    for c in categories:
        result.append({
            "id": c.id,
            "name": c.name,
            "sort": c.sort,
            "productCount": Product.query.filter_by(category_id=c.id).count(),
        })
    return result


def get_category_or_404(category_id: str) -> Category:
    category = db.session.get(Category, category_id)
    if category is None:
        raise ApiError(404, "分类不存在")
    return category


def create_category(body: dict) -> Category:
    name = str(body.get("name", "")).strip()
    if not name:
        raise ApiError(400, "分类名称不能为空")
    try:
        sort = int(body.get("sort", 0))
    except (TypeError, ValueError):
        sort = 0
    category = Category(id=_gen_short_id(_CATEGORY_ID_PREFIX), name=name[:64], sort=sort)
    db.session.add(category)
    db.session.commit()
    return category


def update_category(category_id: str, body: dict) -> Category:
    category = get_category_or_404(category_id)
    if "name" in body:
        name = str(body.get("name", "")).strip()
        if not name:
            raise ApiError(400, "分类名称不能为空")
        category.name = name[:64]
    if "sort" in body:
        try:
            category.sort = int(body.get("sort", 0))
        except (TypeError, ValueError):
            category.sort = 0
    db.session.commit()
    return category


def delete_category(category_id: str) -> None:
    """删除分类：存在商品引用时拒绝（避免商品悬空）。"""
    category = get_category_or_404(category_id)
    if Product.query.filter_by(category_id=category_id).count() > 0:
        raise ApiError(400, "该分类下仍有商品，无法删除")
    db.session.delete(category)
    db.session.commit()


# ---------- 用户 ----------

def list_users(page: int = 1, page_size: int = 20, keyword: str = "") -> dict:
    """用户列表：keyword 匹配 phone/nickname，返回带订单数聚合。"""
    query = User.query
    keyword = keyword.strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(db.or_(User.phone.like(like), User.nickname.like(like)))

    page = max(page, 1)
    page_size = max(page_size, 1)
    total = query.count()
    users = query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for u in users:
        count = Order.query.filter_by(user_id=u.id).count()
        result.append(serializers.admin_user(u, order_count=count))
    return {
        "list": result,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    }


def get_user_detail_or_404(user_id: str) -> dict:
    """用户详情：公开字段 + 订单数 + 累计消费（分，已支付及以后）+ 最近 10 条订单摘要。"""
    user = db.session.get(User, user_id)
    if user is None:
        raise ApiError(404, "用户不存在")

    orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()
    paid_statuses = ("PAID_UNSHIPPED", "SHIPPED", "REFUNDING", "REFUNDED")
    spent_fen = sum(o.total_fen for o in orders if o.status in paid_statuses)
    recent = [serializers.order_payload(o) for o in orders[:10]]

    data = serializers.admin_user(user, order_count=len(orders))
    data["spentFen"] = spent_fen
    data["recentOrders"] = recent
    return data


def adjust_balance(user_id: str, amount_fen, note: str, admin_id: str) -> User:
    """管理员手动调整用户余额（测试用途）：可正可负，并记一条 source=ADMIN 的流水。

    与用户真实充值的严格区别：**无支付单、无档位、不产生资金流入**，
    因此不得计入仪表盘“充值预收”（按 source 区分）。调减不允许把余额扣成负数。
    """
    user = db.session.get(User, user_id)
    if user is None:
        raise ApiError(404, "用户不存在")
    try:
        amount_fen = int(amount_fen)
    except (TypeError, ValueError):
        raise ApiError(400, "调整金额不正确")
    if amount_fen == 0:
        raise ApiError(400, "调整金额不能为 0")
    if abs(amount_fen) > 100000000:
        raise ApiError(400, "单次调整金额过大（上限 100 万元）")
    if user.balance_fen + amount_fen < 0:
        raise ApiError(400, f"余额不足，当前最多可扣减 ¥{user.balance_fen / 100:.2f}")

    ts = now_ms()
    user.balance_fen += amount_fen
    db.session.add(RechargeRecord(
        user_id=user.id,
        amount_fen=amount_fen,
        gift_fen=0,
        created_at=ts,
        provider="admin",
        status=RechargeStatus.SUCCESS,
        paid_at=ts,
        source=RechargeSource.ADMIN,
        admin_id=admin_id,
        note=str(note or "").strip()[:255],
    ))
    db.session.commit()
    return user


# ---------- Banner ----------

def list_banners() -> list:
    return Banner.query.order_by(Banner.sort.asc(), Banner.id.asc()).all()


def create_banner(body: dict) -> Banner:
    image = str(body.get("image", "")).strip()
    if not image:
        raise ApiError(400, "请上传 banner 图片")
    banner = Banner(
        id=gen_id("bn"),
        image=image,
        title=str(body.get("title", "")).strip()[:64],
        sort=_to_int(body.get("sort"), 0),
        enabled=bool(body.get("enabled", True)),
        product_id=str(body.get("productId", "")).strip() or None,
    )
    db.session.add(banner)
    db.session.commit()
    return banner


def update_banner(banner_id: str, body: dict) -> Banner:
    banner = db.session.get(Banner, banner_id)
    if banner is None:
        raise ApiError(404, "banner 不存在")
    if "image" in body and str(body.get("image", "")).strip():
        banner.image = str(body["image"]).strip()
    if "title" in body:
        banner.title = str(body.get("title", "")).strip()[:64]
    if "sort" in body:
        banner.sort = _to_int(body.get("sort"), banner.sort)
    if "enabled" in body:
        banner.enabled = bool(body["enabled"])
    if "productId" in body:
        banner.product_id = str(body.get("productId", "")).strip() or None
    db.session.commit()
    return banner


def delete_banner(banner_id: str) -> None:
    banner = db.session.get(Banner, banner_id)
    if banner is None:
        raise ApiError(404, "banner 不存在")
    image = banner.image
    db.session.delete(banner)
    db.session.commit()
    # 图片尽力删（弱一致），省存储成本
    try:
        get_storage().delete_image(image)
    except Exception:  # noqa: BLE001
        current_app.logger.warning("删除 banner 图片失败（忽略）: %s", image)


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------- 管理员账号 ----------

def list_admins() -> list[dict]:
    admins = AdminUser.query.order_by(AdminUser.created_at.asc()).all()
    return [serializers.admin_account(a) for a in admins]


def get_admin_or_404(admin_id: str) -> AdminUser:
    admin = db.session.get(AdminUser, admin_id)
    if admin is None:
        raise ApiError(404, "管理员不存在")
    return admin


def create_admin(body: dict) -> AdminUser:
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username:
        raise ApiError(400, "账号不能为空")
    if len(password) < 6:
        raise ApiError(400, "密码至少 6 位")
    if AdminUser.query.filter_by(username=username).first() is not None:
        raise ApiError(400, "账号已存在")

    admin = AdminUser(
        id=gen_id("a"),
        username=username[:64],
        display_name=str(body.get("displayName", "")).strip()[:64],
        is_active=bool(body.get("isActive", True)),
        is_super=bool(body.get("isSuper", False)),
        created_at=now_ms(),
        last_login_at=0,
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    return admin


def _active_super_count() -> int:
    return AdminUser.query.filter_by(is_active=True, is_super=True).count()


def update_admin(admin_id: str, body: dict, operator: AdminUser) -> AdminUser:
    """改资料/密码/启用禁用/超管。保护：不能禁用或撤超管自己；不能撤掉最后一个启用超管。"""
    admin = get_admin_or_404(admin_id)

    if "displayName" in body:
        admin.display_name = str(body.get("displayName", "")).strip()[:64]
    if "password" in body and str(body.get("password", "")):
        password = str(body.get("password"))
        if len(password) < 6:
            raise ApiError(400, "密码至少 6 位")
        admin.set_password(password)

    if "isActive" in body:
        active = bool(body.get("isActive"))
        if not active:
            if admin.id == operator.id:
                raise ApiError(400, "不能禁用当前登录的自己")
            if admin.is_super and _active_super_count() <= 1:
                raise ApiError(400, "至少保留一个启用的超级管理员")
        admin.is_active = active

    if "isSuper" in body:
        is_super = bool(body.get("isSuper"))
        if not is_super:
            if admin.id == operator.id:
                raise ApiError(400, "不能撤销自己的超管权限")
            if admin.is_active and _active_super_count() <= 1:
                raise ApiError(400, "至少保留一个启用的超级管理员")
        admin.is_super = is_super

    db.session.commit()
    return admin


def delete_admin(admin_id: str, operator: AdminUser) -> None:
    """删除管理员（级联删其 token）。保护：不能删自己；不能删最后一个启用超管。"""
    admin = get_admin_or_404(admin_id)
    if admin.id == operator.id:
        raise ApiError(400, "不能删除当前登录的自己")
    if admin.is_active and admin.is_super and _active_super_count() <= 1:
        raise ApiError(400, "至少保留一个启用的超级管理员")

    AdminToken.query.filter_by(admin_id=admin_id).delete(synchronize_session=False)
    db.session.delete(admin)
    db.session.commit()


def change_password(admin: AdminUser, old_password: str, new_password: str) -> None:
    """管理员改自己密码：校验旧密码，改密后删其全部 token 强制重新登录。"""
    if not admin.verify_password(old_password or ""):
        raise ApiError(400, "原密码不正确")
    if len(new_password or "") < 6:
        raise ApiError(400, "新密码至少 6 位")
    admin.set_password(new_password)
    db.session.commit()
    AdminToken.query.filter_by(admin_id=admin.id).delete(synchronize_session=False)
    db.session.commit()


# ---------- 充值档位（运营活动） ----------
#
# 约定：用户只能从档位里点选（不可自输金额）；必须至少保留一个档位，
# 所以默认档「充 1000 赠 100」在新增其他档位之前不可删除。

def list_recharge_tiers() -> list[dict]:
    tiers = RechargeTier.query.order_by(RechargeTier.sort.asc(), RechargeTier.id.asc()).all()
    return [
        {
            "id": t.id,
            "thresholdFen": t.threshold_fen,
            "giftFen": t.gift_fen,
            "label": t.label,
            "sub": t.sub,
            "sort": t.sort,
        }
        for t in tiers
    ]


def _clean_tier_fields(body: dict, *, partial: bool) -> dict:
    fields: dict = {}

    def _present(key: str) -> bool:
        return (not partial) or (key in body)

    if _present("thresholdFen"):
        try:
            threshold_fen = int(body.get("thresholdFen", 0))
        except (TypeError, ValueError):
            threshold_fen = 0
        if threshold_fen <= 0:
            raise ApiError(400, "充值门槛金额必须大于 0")
        fields["threshold_fen"] = threshold_fen

    if _present("giftFen"):
        try:
            gift_fen = int(body.get("giftFen", 0))
        except (TypeError, ValueError):
            gift_fen = 0
        if gift_fen < 0:
            raise ApiError(400, "赠送金额不能为负")
        fields["gift_fen"] = gift_fen

    if _present("label"):
        fields["label"] = str(body.get("label", "")).strip()[:32]
    if _present("sub"):
        fields["sub"] = str(body.get("sub", "")).strip()[:32]
    if _present("sort"):
        try:
            fields["sort"] = int(body.get("sort", 0))
        except (TypeError, ValueError):
            fields["sort"] = 0

    if not partial and "threshold_fen" not in fields:
        raise ApiError(400, "请填写充值门槛金额")
    return fields


def create_recharge_tier(body: dict) -> RechargeTier:
    fields = _clean_tier_fields(body, partial=False)
    tier = RechargeTier(
        threshold_fen=fields["threshold_fen"],
        gift_fen=fields.get("gift_fen", 0),
        label=fields.get("label", ""),
        sub=fields.get("sub", ""),
        sort=fields.get("sort", 0),
    )
    db.session.add(tier)
    db.session.commit()
    return tier


def get_tier_or_404(tier_id: int) -> RechargeTier:
    tier = db.session.get(RechargeTier, tier_id)
    if tier is None:
        raise ApiError(404, "充值档位不存在")
    return tier


def update_recharge_tier(tier_id: int, body: dict) -> RechargeTier:
    tier = get_tier_or_404(tier_id)
    for key, value in _clean_tier_fields(body, partial=True).items():
        setattr(tier, key, value)
    db.session.commit()
    return tier


def delete_recharge_tier(tier_id: int) -> None:
    """删除档位：必须至少保留一个（充值入口不能空）。"""
    tier = get_tier_or_404(tier_id)
    if RechargeTier.query.count() <= 1:
        raise ApiError(400, "至少保留一个充值档位，请先新增其他档位再删除")
    db.session.delete(tier)
    db.session.commit()
