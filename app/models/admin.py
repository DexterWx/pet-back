"""管理端账号：管理员与管理员 Token（与小程序用户体系完全隔离）。

- 密码经 werkzeug generate_password_hash 存储，绝不明文；
- 登录发独立随机 token 存 admin_tokens 表，鉴权走 core/security.admin_required；
- 不复用 client 的 ApiToken / @login_required（见 docs/architecture.md 第 11 节）。
"""
from werkzeug.security import check_password_hash, generate_password_hash

from . import db


class AdminUser(db.Model):
    """管理员账号（多账号、可禁用、可改密）。"""

    __tablename__ = "admin_users"

    id = db.Column(db.String(32), primary_key=True)  # a + uuid hex
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(64), nullable=False, default="")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_super = db.Column(db.Boolean, nullable=False, default=False)  # 超管才能管理管理员账号
    created_at = db.Column(db.BigInteger, nullable=False, default=0)
    last_login_at = db.Column(db.BigInteger, nullable=False, default=0)

    tokens = db.relationship("AdminToken", backref="admin", cascade="all, delete-orphan")

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)

    def verify_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)


class AdminToken(db.Model):
    """管理员登录 Token（每次登录轮换：删旧发新）。"""

    __tablename__ = "admin_tokens"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    admin_id = db.Column(db.String(32), db.ForeignKey("admin_users.id"), nullable=False, index=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.BigInteger, nullable=False, default=0)
