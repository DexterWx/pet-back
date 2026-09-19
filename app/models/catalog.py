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

    对齐 pet-mini Mock Product {id,title,categoryId,priceFen,stock,sold,images[],desc}。
    """

    __tablename__ = "products"

    id = db.Column(db.String(32), primary_key=True)  # p001 等种子 id
    title = db.Column(db.String(128), nullable=False)
    category_id = db.Column(db.String(32), db.ForeignKey("categories.id"), nullable=False, index=True)
    price_fen = db.Column(db.Integer, nullable=False, default=0)
    stock = db.Column(db.Integer, nullable=False, default=0)
    sold = db.Column(db.Integer, nullable=False, default=0)
    images = db.Column(db.JSON, nullable=False, default=list)
    # "desc" 在 Python 中是内置函数名，属性用 description，列名保持 desc 与 Mock 字段一致
    description = db.Column("desc", db.Text, nullable=False, default="")
    sort = db.Column(db.Integer, nullable=False, default=0)  # 默认排序（推荐位取前 N）

    category = db.relationship("Category", backref="products")


class Banner(db.Model):
    """首页轮播图。"""

    __tablename__ = "banners"

    id = db.Column(db.String(32), primary_key=True)
    image = db.Column(db.String(512), nullable=False)
    title = db.Column(db.String(64), nullable=False, default="")
    sort = db.Column(db.Integer, nullable=False, default=0)
