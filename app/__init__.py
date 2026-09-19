"""应用工厂：创建并配置 Flask 应用。

结构约定：
- app/core       基础设施（配置、统一响应、认证、常量）
- app/models     SQLAlchemy 模型
- app/api/v1     接口层，按端划分命名空间：client（小程序端）/ admin（管理端，预留）
- app/services   业务逻辑层（接口层与未来管理端复用）
- app/database   种子数据与数据库维护命令
"""
from pathlib import Path

from flask import Flask
from flask_cors import CORS

from .core.config import Config
from .core.response import register_error_handlers
from .models import db


def create_app(config_object: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    # 确保 instance/ 目录存在（SQLite 数据文件位置）
    (Path(app.instance_path)).mkdir(parents=True, exist_ok=True)

    # 扩展
    db.init_app(app)
    CORS(app)  # 本地联调放开跨域（小程序 wx.request 不受限，便于 curl/浏览器调试）

    # 蓝图：/api/v1/client（小程序端）、/api/v1/admin（管理端预留）
    from .api.v1.admin import admin_bp
    from .api.v1.client import client_bp

    app.register_blueprint(client_bp)
    app.register_blueprint(admin_bp)

    # 统一错误处理（ApiError / HTTP 异常 / 未捕获异常 -> {code, data, message}）
    register_error_handlers(app)

    # CLI 命令：flask db seed / flask db reset
    from .database.cli import register_cli

    register_cli(app)

    # 本地开发便利：确保建表（幂等）；种子数据由 flask seed 灌入
    with app.app_context():
        db.create_all()

    return app
