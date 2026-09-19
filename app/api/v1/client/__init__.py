"""小程序端接口（命名空间 /api/v1/client）。

聚合各资源子蓝图；接口路径与 pet-mini/mock/server.js 一一对应，
小程序联调时将 config.baseURL 设为 http://127.0.0.1:8000/api/v1/client 并 useMock=false 即可。
"""
from flask import Blueprint

client_bp = Blueprint("client", __name__, url_prefix="/api/v1/client")

from . import auth, cart, catalog, contact, home, order, user  # noqa: E402

client_bp.register_blueprint(auth.bp)
client_bp.register_blueprint(home.bp)
client_bp.register_blueprint(catalog.bp)
client_bp.register_blueprint(cart.bp)
client_bp.register_blueprint(order.bp)
client_bp.register_blueprint(user.bp)
client_bp.register_blueprint(contact.bp)
