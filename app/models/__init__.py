"""模型包：db 实例与全部模型导出（供 create_all / 各层引用）。"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from .cart import CartLine, Favorite  # noqa: E402
from .catalog import Banner, Category, Product  # noqa: E402
from .order import Order, OrderItem  # noqa: E402
from .recharge import RechargeRecord, RechargeTier  # noqa: E402
from .user import ApiToken, User  # noqa: E402

__all__ = [
    "db",
    "User",
    "ApiToken",
    "Category",
    "Product",
    "Banner",
    "Order",
    "OrderItem",
    "CartLine",
    "Favorite",
    "RechargeTier",
    "RechargeRecord",
]
