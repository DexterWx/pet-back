"""用户与登录 Token。"""
from . import db


class User(db.Model):
    """微信用户（无独立注册，首次微信登录即建号）。

    对外序列化经 serializers.public_user，不暴露 openid/token。
    曾有的 points/coupons 已全链路废弃并删列（无积分/优惠券业务）。
    """

    __tablename__ = "users"

    id = db.Column(db.String(32), primary_key=True)  # u + uuid hex
    openid = db.Column(db.String(64), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(32), nullable=False, default="", index=True)  # 微信授权手机号（非全局唯一，供后台检索/联系）
    nickname = db.Column(db.String(64), nullable=False, default="微信用户")
    avatar = db.Column(db.String(512), nullable=False, default="")
    balance_fen = db.Column(db.Integer, nullable=False, default=0)  # 余额（分，充值而来，可用于下单抵扣）
    created_at = db.Column(db.BigInteger, nullable=False, default=0)  # 毫秒时间戳

    tokens = db.relationship("ApiToken", backref="user", cascade="all, delete-orphan")


class Address(db.Model):
    """收货地址簿（按用户隔离）：支持多地址、单一默认。

    自提单可用（仅取姓名+电话），快递单需完整省市区+详细地址。
    对外序列化 camelCase；phone 属于敏感信息，仅在下单/订单详情等自有接口回显。
    """

    __tablename__ = "addresses"

    id = db.Column(db.String(32), primary_key=True)  # ad + uuid hex
    user_id = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False, index=True)
    receiver_name = db.Column(db.String(64), nullable=False)
    phone = db.Column(db.String(32), nullable=False)
    province = db.Column(db.String(32), nullable=False, default="")
    city = db.Column(db.String(32), nullable=False, default="")
    district = db.Column(db.String(32), nullable=False, default="")
    detail = db.Column(db.String(255), nullable=False, default="")  # 街道/门牌等详细地址
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.BigInteger, nullable=False, default=0)
    updated_at = db.Column(db.BigInteger, nullable=False, default=0)

    @property
    def full_address(self) -> str:
        """拼接完整地址（省+市+区+详细），自提时可能仅返回部分。"""
        return "".join([self.province, self.city, self.district, self.detail]).strip()


class ApiToken(db.Model):
    """登录 Token（每次微信登录轮换：删旧发新，旧 token 即失效）。"""

    __tablename__ = "api_tokens"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False, index=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.BigInteger, nullable=False, default=0)  # 毫秒时间戳
