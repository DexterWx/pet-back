"""应用工厂：创建并配置 Flask 应用。

结构约定：
- app/core       基础设施（配置、统一响应、认证、常量）
- app/models     SQLAlchemy 模型
- app/api/v1     接口层，按端划分命名空间：client（小程序端）/ admin（管理端，预留）
- app/services   业务逻辑层（接口层与未来管理端复用）
- app/database   种子数据与数据库维护命令
"""
from pathlib import Path

from flask import Flask, send_from_directory
from flask_cors import CORS
from sqlalchemy import text

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
        _auto_migrate()

    # 上传资源（头像等）的静态访问路由：/uploads/<filename> -> UPLOAD_DIR
    _register_upload_routes(app)

    return app


def _register_upload_routes(app: Flask) -> None:
    from .services.storage import UPLOAD_URL_PREFIX

    upload_dir = app.config["UPLOAD_DIR"]
    Path(upload_dir).mkdir(parents=True, exist_ok=True)

    @app.route(f"{UPLOAD_URL_PREFIX}/<path:filename>")
    def uploaded_file(filename: str):  # noqa: D401
        return send_from_directory(upload_dir, filename)


def _auto_migrate() -> None:
    """轻量字段迁移（无 Alembic）：create_all 只建新表不会改已有表。

    用 PRAGMA table_info 检查后幂等地补列（ADD）或删列（DROP，仅 SQLite >= 3.35），
    保留其余现有数据。新增/删除模型字段时同步在此登记。
    """
    add_columns = [
        # (表名, 列名, ALTER 补列 DDL, 补列后的一次性修正 SQL 可选)
        ("products", "on_sale", "ALTER TABLE products ADD COLUMN on_sale BOOLEAN NOT NULL DEFAULT 1", None),
        ("admin_users", "is_super", "ALTER TABLE admin_users ADD COLUMN is_super BOOLEAN NOT NULL DEFAULT 0", None),
        # 充值单转为真实支付交易：新增支付相关字段
        ("recharge_records", "status", "ALTER TABLE recharge_records ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'PENDING'", None),
        ("recharge_records", "payment_no", "ALTER TABLE recharge_records ADD COLUMN payment_no VARCHAR(32)", None),
        ("recharge_records", "transaction_id", "ALTER TABLE recharge_records ADD COLUMN transaction_id VARCHAR(64)", None),
        ("recharge_records", "prepay_id", "ALTER TABLE recharge_records ADD COLUMN prepay_id VARCHAR(64) NOT NULL DEFAULT ''", None),
        ("recharge_records", "provider", "ALTER TABLE recharge_records ADD COLUMN provider VARCHAR(16) NOT NULL DEFAULT 'mock'", None),
        ("recharge_records", "payer_openid", "ALTER TABLE recharge_records ADD COLUMN payer_openid VARCHAR(64) NOT NULL DEFAULT ''", None),
        ("recharge_records", "tier_id", "ALTER TABLE recharge_records ADD COLUMN tier_id INTEGER", None),
        ("recharge_records", "paid_at", "ALTER TABLE recharge_records ADD COLUMN paid_at BIGINT NOT NULL DEFAULT 0", None),
        # 余额变动来源：存量流水均为用户真实充值，DEFAULT 'USER' 对已有行自动生效
        ("recharge_records", "source", "ALTER TABLE recharge_records ADD COLUMN source VARCHAR(8) NOT NULL DEFAULT 'USER'", None),
        ("recharge_records", "admin_id", "ALTER TABLE recharge_records ADD COLUMN admin_id VARCHAR(32) NOT NULL DEFAULT ''", None),
        ("recharge_records", "note", "ALTER TABLE recharge_records ADD COLUMN note VARCHAR(255) NOT NULL DEFAULT ''", None),
        # 运费：订单金额拆分为商品金额 + 运费；历史订单无运费，商品金额回填为原总额
        ("orders", "goods_total_fen", "ALTER TABLE orders ADD COLUMN goods_total_fen INTEGER NOT NULL DEFAULT 0",
         "UPDATE orders SET goods_total_fen = total_fen WHERE goods_total_fen = 0"),
        ("orders", "freight_fen", "ALTER TABLE orders ADD COLUMN freight_fen INTEGER NOT NULL DEFAULT 0", None),
        # 交易完成（确认收货）：存量已发货订单无需回填，满 N 天后由读取时的惰性检查自动转 COMPLETED
        ("orders", "completed_at", "ALTER TABLE orders ADD COLUMN completed_at BIGINT NOT NULL DEFAULT 0", None),
        ("orders", "complete_source", "ALTER TABLE orders ADD COLUMN complete_source VARCHAR(8) NOT NULL DEFAULT ''", None),
        # Banner 启停开关：存量 banner 默认启用
        ("banners", "enabled", "ALTER TABLE banners ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT 1", None),
        ("banners", "product_id", "ALTER TABLE banners ADD COLUMN product_id VARCHAR(32)", None),
    ]
    drop_columns = [
        # (表名, 列名) 已确认无索引/约束依赖，且列上无业务数据价值，可安全删除
        ("users", "points"),
        ("users", "coupons"),
    ]
    changed = False
    added_columns = set()
    for entry in add_columns:
        table, column, ddl = entry[0], entry[1], entry[2]
        post_sql = entry[3] if len(entry) > 3 else None
        cols = _table_columns(table)
        if cols and column not in cols:
            db.session.execute(text(ddl))
            added_columns.add((table, column))
            if post_sql:
                db.session.execute(text(post_sql))
            changed = True
    for table, column in drop_columns:
        cols = _table_columns(table)
        if cols and column in cols:
            db.session.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
            changed = True

    # 复合索引（查询性能）：create_all 只会给「新建的表」建索引，存量表必须在这里幂等补建。
    # 定义同时写在各模型的 __table_args__ 里（保证新建库一次到位），两边名字要一致。
    add_indexes = [
        "CREATE INDEX IF NOT EXISTS ix_orders_user_status_created ON orders (user_id, status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_orders_status_created ON orders (status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_orders_status_paid ON orders (status, paid_at)",
        "CREATE INDEX IF NOT EXISTS ix_after_sales_status_created ON after_sales (status, created_at)",
    ]
    if db.engine.dialect.name == "sqlite":  # IF NOT EXISTS 是 SQLite/PG 语法；换库后这份清单改走 Alembic
        for ddl in add_indexes:
            db.session.execute(text(ddl))
            changed = True

    # 一次性数据修正：首次引入充值 status 列时，旧流水均是在旧逻辑下“已入账”的，
    # 统一标为 SUCCESS 并以创建时间作为到账时间，避免被误认为待支付。
    if ("recharge_records", "status") in added_columns:
        db.session.execute(text(
            "UPDATE recharge_records SET status = 'SUCCESS', paid_at = created_at WHERE paid_at = 0"
        ))
        changed = True

    if changed:
        db.session.commit()

    # 存量库兼容：若还没有任何超管，把最早创建的管理员（seed 的 admin）标记为超管
    from .models import AdminUser

    if AdminUser.query.count() > 0 and AdminUser.query.filter_by(is_super=True).count() == 0:
        first = AdminUser.query.order_by(AdminUser.created_at.asc()).first()
        first.is_super = True
        db.session.commit()


def _table_columns(table: str) -> set[str]:
    """返回表当前列名集合；表不存在时返回空集。"""
    rows = db.session.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}
