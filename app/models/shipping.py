"""运费配置：全局一套（基础运费 + 满多少免运费）。

单行表（id 固定为 1）：运费规则全站通用，不按分类/商品差异计价，
避免过度设计；后续若真要分区域运费，再扩展为多行 + 区域字段。
"""
from . import db


class ShippingConfig(db.Model):
    """运费规则。free_threshold_fen=0 表示不启用包邮（一律收基础运费）。"""

    __tablename__ = "shipping_configs"

    id = db.Column(db.Integer, primary_key=True)  # 固定 1
    base_freight_fen = db.Column(db.Integer, nullable=False, default=0)  # 基础运费（分），0=包邮
    free_threshold_fen = db.Column(db.Integer, nullable=False, default=0)  # 商品金额满多少免运费（分），0=不启用
    updated_at = db.Column(db.BigInteger, nullable=False, default=0)
