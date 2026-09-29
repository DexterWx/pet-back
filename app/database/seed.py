"""种子数据：初始管理员 + 默认充值档位。

阶段 F 起，**分类/商品/Banner 均不再灌伪造种子**：全部改由管理后台（pet-web）
真实创建，方便商家自行上架/配置测试；小程序端已支持这些内容为空时正常展示（空态）。
- 初始管理员：仅当无任何管理员时创建一个（默认 admin/admin123，标记为超管；上线前务必改密）。
- 默认充值档位：仅当无任何档位时写入「充 1000 元、赠 100 元」（业务约定：充值必须至少保留一个档位）。
- Banner 管理界面属第二批；补上之前 Banner 需直接改库或等第二批 UI。
幂等：已存在则跳过。
"""
import os

from ..core.constants import gen_id, now_ms
from ..models import AdminUser, RechargeTier, db

# 默认充值档位 (threshold_fen, gift_fen, label, sub, sort)
DEFAULT_RECHARGE_TIER = (100000, 10000, "充1000元", "送100元", 0)


def run_seed() -> dict:
    """灌种子数据（幂等），返回各类新增条数。"""
    added = {"admins": 0, "recharge_tiers": 0}

    # 初始管理员：仅当无任何管理员时创建（默认 admin / admin123，超管；上线前务必改密）
    if AdminUser.query.count() == 0:
        admin = AdminUser(
            id=gen_id("a"),
            username=os.getenv("SEED_ADMIN_USERNAME", "admin"),
            display_name="超级管理员",
            is_active=True,
            is_super=True,
            created_at=now_ms(),
            last_login_at=0,
        )
        admin.set_password(os.getenv("SEED_ADMIN_PASSWORD", "admin123"))
        db.session.add(admin)
        added["admins"] += 1

    # 默认充值档位：不可无档位，仅空表时写入一次
    if RechargeTier.query.count() == 0:
        threshold_fen, gift_fen, label, sub, sort = DEFAULT_RECHARGE_TIER
        db.session.add(RechargeTier(
            threshold_fen=threshold_fen, gift_fen=gift_fen, label=label, sub=sub, sort=sort,
        ))
        added["recharge_tiers"] += 1

    db.session.commit()
    return added
