"""管理端操作溯源：记录管理员的关键写操作，供超管审计。

只记"谁在什么时候对什么做了什么"，不记敏感明文（密码等）。username 做快照，
避免账号被删后日志无法溯源。
"""
from . import db


class AdminAuditLog(db.Model):
    __tablename__ = "admin_audit_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    admin_id = db.Column(db.String(32), nullable=False, index=True)
    username = db.Column(db.String(64), nullable=False, default="")  # 快照，防账号删除后失联
    action = db.Column(db.String(64), nullable=False, index=True)  # 如 product.create / order.ship
    target = db.Column(db.String(128), nullable=False, default="")  # 目标 id / 描述
    detail = db.Column(db.String(512), nullable=False, default="")  # 摘要
    ip = db.Column(db.String(64), nullable=False, default="")
    created_at = db.Column(db.BigInteger, nullable=False, default=0, index=True)
