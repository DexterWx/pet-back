"""商品目录：分类 / 商品 / 首页 Banner。"""
from . import db


class Category(db.Model):
    """商品分类。id 为种子字符串（如 c_dried），与小程序现有数据兼容。"""

    __tablename__ = "categories"

    id = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    sort = db.Column(db.Integer, nullable=False, default=0)  # 展示排序，小者在前


class Product(db.Model):
    """商品。金额以分存储；images 为 JSON 数组。

    无库存概念：商品均为下单现做，不设 stock；sold 为累计销量（展示用）。
    对齐 pet-mini Mock Product {id,title,categoryId,priceFen,sold,images[],desc}。
    """

    __tablename__ = "products"

    id = db.Column(db.String(32), primary_key=True)  # p001 等种子 id
    title = db.Column(db.String(128), nullable=False)
    category_id = db.Column(db.String(32), db.ForeignKey("categories.id"), nullable=False, index=True)
    price_fen = db.Column(db.Integer, nullable=False, default=0)
    sold = db.Column(db.Integer, nullable=False, default=0)
    images = db.Column(db.JSON, nullable=False, default=list)
    # "desc" 在 Python 中是内置函数名，属性用 description，列名保持 desc 与 Mock 字段一致
    description = db.Column("desc", db.Text, nullable=False, default="")
    sort = db.Column(db.Integer, nullable=False, default=0)  # 默认排序（列表 default 排序，小者在前）
    # 上架中才在小程序端展示/可购买；下架保留在库可随时重新上架（删除才物理移除，见 catalog_service）
    on_sale = db.Column(db.Boolean, nullable=False, default=True)

    category = db.relationship("Category", backref="products")


class Banner(db.Model):
    """首页轮播图（大图美观位）。enabled=False 时小程序不展示（不删图，可随时恢复）。

    product_id 为点击跳转的商品（可空）；配了则小程序点 banner 直达该商品详情。
    """

    __tablename__ = "banners"

    id = db.Column(db.String(32), primary_key=True)
    image = db.Column(db.String(512), nullable=False)
    title = db.Column(db.String(64), nullable=False, default="")
    sort = db.Column(db.Integer, nullable=False, default=0)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    product_id = db.Column(db.String(32), nullable=True)  # 点击跳转的商品 id（可空）
