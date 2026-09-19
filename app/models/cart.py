"""购物车行与收藏（均按用户隔离）。"""
from . import db


class CartLine(db.Model):
    """购物车行 {productId,qty,checked}；返回时实时 join 商品（价格/库存以商品表为准）。"""

    __tablename__ = "cart_lines"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False, index=True)
    product_id = db.Column(db.String(32), db.ForeignKey("products.id"), nullable=False)
    qty = db.Column(db.Integer, nullable=False, default=1)
    checked = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (db.UniqueConstraint("user_id", "product_id", name="uq_cart_user_product"),)


class Favorite(db.Model):
    """收藏：一行一个 (user, product)。"""

    __tablename__ = "favorites"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False, index=True)
    product_id = db.Column(db.String(32), db.ForeignKey("products.id"), nullable=False)
    created_at = db.Column(db.BigInteger, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint("user_id", "product_id", name="uq_fav_user_product"),)
