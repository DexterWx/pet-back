"""用户与登录 Token。"""
from . import db


class User(db.Model):
    """微信用户（无独立注册，首次微信登录即建号）。

    对齐 pet-mini Mock User 模型 {id,openid,nickname,avatar,balanceFen,points,coupons}；
    对外序列化经 serializers.public_user，不暴露 openid/token。
    """

    __tablename__ = "users"

    id = db.Column(db.String(32), primary_key=True)  # u + uuid hex
    openid = db.Column(db.String(64), unique=True, nullable=False, index=True)
    nickname = db.Column(db.String(64), nullable=False, default="微信用户")
    avatar = db.Column(db.String(512), nullable=False, default="")
    balance_fen = db.Column(db.Integer, nullable=False, default=0)  # 余额（分）
    points = db.Column(db.Integer, nullable=False, default=0)  # 积分
    coupons = db.Column(db.Integer, nullable=False, default=0)  # 优惠券数
    created_at = db.Column(db.BigInteger, nullable=False, default=0)  # 毫秒时间戳

    tokens = db.relationship("ApiToken", backref="user", cascade="all, delete-orphan")


class ApiToken(db.Model):
    """登录 Token（每次微信登录轮换：删旧发新，旧 token 即失效）。"""

    __tablename__ = "api_tokens"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False, index=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.BigInteger, nullable=False, default=0)  # 毫秒时间戳
