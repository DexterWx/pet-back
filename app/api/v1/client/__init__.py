"""小程序端接口（命名空间 /api/v1/client）。

聚合各资源子蓝图；接口路径与字段命名以本后端为唯一契约（旧 Mock 已删除）。
小程序联调：`config.baseURL = http://<电脑局域网IP>:8000/api/v1/client`（真机必须用局域网 IP，
不能用 127.0.0.1），可用 `sh pet-mini/scripts/set-dev-host.sh` 自动回写。
"""
from flask import Blueprint

client_bp = Blueprint("client", __name__, url_prefix="/api/v1/client")

from . import address, auth, cart, catalog, home, order, payment, shipping, user  # noqa: E402

client_bp.register_blueprint(auth.bp)
client_bp.register_blueprint(home.bp)
client_bp.register_blueprint(catalog.bp)
client_bp.register_blueprint(cart.bp)
client_bp.register_blueprint(address.bp)
client_bp.register_blueprint(order.bp)
client_bp.register_blueprint(payment.bp)
client_bp.register_blueprint(user.bp)
client_bp.register_blueprint(shipping.bp)
