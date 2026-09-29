"""运费规则：全局一套配置（基础运费 + 满多少免运费），单行配置 id=1。

下单时由服务端算定并快照到订单（goods_total_fen / freight_fen / total_fen），
之后修改配置不影响历史订单。免运费判定**只看商品金额合计**，不计入运费本身。

规则优先级：
1. 自提（SELF_PICKUP）一律免运费；
2. `free_threshold_fen > 0` 且商品金额 >= 门槛 -> 免运费；
3. 否则收 `base_freight_fen`（为 0 即全站包邮，也是未配置时的默认行为）。
"""
from ..core.constants import DeliveryType, now_ms
from ..core.response import ApiError
from ..models import ShippingConfig, db

CONFIG_ID = 1


def get_config() -> ShippingConfig:
    """取全局运费配置；不存在时惰性创建默认（基础运费 0、不启用门槛 = 全站包邮）。"""
    cfg = db.session.get(ShippingConfig, CONFIG_ID)
    if cfg is None:
        cfg = ShippingConfig(id=CONFIG_ID, base_freight_fen=0, free_threshold_fen=0, updated_at=now_ms())
        db.session.add(cfg)
        db.session.commit()
    return cfg


def config_payload(cfg: ShippingConfig) -> dict:
    return {
        "baseFreightFen": cfg.base_freight_fen,
        "freeThresholdFen": cfg.free_threshold_fen,
        "updatedAt": cfg.updated_at,
    }


def _read_int(body: dict, key: str, label: str) -> int:
    try:
        value = int(body.get(key))
    except (TypeError, ValueError):
        raise ApiError(400, f"{label}金额不正确")
    if value < 0:
        raise ApiError(400, f"{label}不能为负")
    return value


def update_config(body: dict) -> ShippingConfig:
    """更新运费配置（仅覆盖传入字段）。"""
    cfg = get_config()
    if "baseFreightFen" in body:
        cfg.base_freight_fen = _read_int(body, "baseFreightFen", "基础运费")
    if "freeThresholdFen" in body:
        cfg.free_threshold_fen = _read_int(body, "freeThresholdFen", "包邮门槛")
    cfg.updated_at = now_ms()
    db.session.commit()
    return cfg


def calc_freight(goods_total_fen: int, delivery_type: str) -> int:
    """按当前规则计算应付运费（分）。"""
    if delivery_type == DeliveryType.SELF_PICKUP:
        return 0
    cfg = get_config()
    if cfg.free_threshold_fen > 0 and goods_total_fen >= cfg.free_threshold_fen:
        return 0
    return cfg.base_freight_fen
