"""管理端接口（命名空间 /api/v1/admin）。

与小程序端完全隔离：
- 认证：账号密码登录，token 存 admin_tokens 表，鉴权走 core/security.admin_required；
- 业务：复用 app/services 层（订单发货/取消/强制退款等），不复制规则。
"""
from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")

from . import aftersale, audit, auth, banner, category, dashboard, export, order, order_config, product, recharge_tier, shipping, upload, user, admin_account  # noqa: E402

admin_bp.register_blueprint(auth.bp)
admin_bp.register_blueprint(order.bp)
admin_bp.register_blueprint(order_config.bp)
admin_bp.register_blueprint(aftersale.bp)
admin_bp.register_blueprint(upload.bp)
admin_bp.register_blueprint(product.bp)
admin_bp.register_blueprint(category.bp)
admin_bp.register_blueprint(user.bp)
admin_bp.register_blueprint(admin_account.bp)
admin_bp.register_blueprint(recharge_tier.bp)
admin_bp.register_blueprint(shipping.bp)
admin_bp.register_blueprint(banner.bp)
admin_bp.register_blueprint(dashboard.bp)
admin_bp.register_blueprint(export.bp)
admin_bp.register_blueprint(audit.bp)
