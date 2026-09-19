"""管理端接口（预留命名空间 /api/v1/admin）。

本期不实现任何接口。未来 pet-web 管理端在此扩展：
- 认证方式将与 client 端分离（如管理员账号 + 独立 Token）
- 业务逻辑复用 app/services 层（如 order_service.cancel_order 即商家取消订单）
"""
from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")
