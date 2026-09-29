"""模型包：db 实例与全部模型导出（供 create_all / 各层引用）。"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from .admin import AdminToken, AdminUser  # noqa: E402
from .aftersale import AfterSale  # noqa: E402
from .audit import AdminAuditLog  # noqa: E402
from .cart import CartLine, Favorite  # noqa: E402
from .catalog import Banner, Category, Product  # noqa: E402
from .order import Order, OrderConfig, OrderItem  # noqa: E402
from .payment import Payment  # noqa: E402
from .recharge import RechargeRecord, RechargeTier  # noqa: E402
from .shipping import ShippingConfig  # noqa: E402
from .user import Address, ApiToken, User  # noqa: E402

__all__ = [
    "db",
    "User",
    "ApiToken",
    "Address",
    "AdminUser",
    "AdminToken",
    "AdminAuditLog",
    "Category",
    "Product",
    "Banner",
    "Order",
    "OrderItem",
    "OrderConfig",
    "Payment",
    "AfterSale",
    "CartLine",
    "Favorite",
    "RechargeTier",
    "RechargeRecord",
    "ShippingConfig",
]
