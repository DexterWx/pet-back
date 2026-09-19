"""种子数据：分类 / 商品 / Banner / 充值档位。

内容照搬 pet-mini/mock/db.js（id、价格、库存、图片、文案一致），保证联调时前后端数据同源。
幂等：已存在的记录跳过，不覆盖运行期产生的库存/销量变化。
"""
from ..models import Banner, Category, Product, RechargeTier, db


def _img(seed: str) -> str:
    return f"https://picsum.photos/seed/{seed}/600/600"


# (id, name)，顺序即展示顺序
CATEGORIES = [
    ("c_notice", "购买须知"),
    ("c_dried", "烘干肉"),
    ("c_veg", "蔬菜肉"),
    ("c_fruit", "水果肉"),
    ("c_fresh", "灭菌鲜食"),
    ("c_freeze", "冻干类"),
    ("c_teeth", "磨牙肉"),
    ("c_cheese", "芝士肉"),
    ("c_coat", "美毛亮肤"),
    ("c_cookie", "脆脆饼干"),
    ("c_reward", "奖励零食"),
]

# (id, title, categoryId, priceFen, stock, sold, images, desc)
PRODUCTS = [
    ("p001", "中秋月饼（上新，9.20号统一发出）", "c_reward", 4900, 1988, 38,
     [_img("mooncake"), _img("mooncake2")],
     "节日限定宠物月饼，天然食材手工制作，下单后统一发出。"),
    ("p002", "99元随心配", "c_dried", 9900, 720, 460,
     [_img("pack99"), _img("pack99b")],
     "99 元随心搭配礼包，掌柜根据库存搭配多款零食，只多不少。"),
    ("p003", "199元随心配", "c_dried", 19900, 888, 203,
     [_img("pack199"), _img("pack199b")],
     "199 元大容量随心配，适合多宠家庭囤货。"),
    ("p004", "必看！购买须知！！", "c_notice", 99900, 1000, 0,
     [_img("notice")],
     "所有零食均为人食用级别、无防腐剂；称重类手工称重只多不少；下单先做最新鲜。"),
    ("p005", "鸡肉酿猪耳朵（超级大）", "c_teeth", 4800, 320, 79,
     [_img("pigear"), _img("pigear2")],
     "大块猪耳裹鸡胸肉，磨牙洁齿首选，超级大份量。"),
    ("p006", "鸡肉燕麦球（上新）", "c_reward", 1990, 500, 66,
     [_img("oatball"), _img("oatball2"), _img("oatball3")],
     "鲜鸡胸肉+熟燕麦粉+大米粉，黄蓝双色由天然果蔬粉调色，训练奖励、日常洁齿解馋都合适。"),
    ("p007", "鸭肉秋葵饼", "c_veg", 1690, 430, 147,
     [_img("okra")],
     "鸭肉绕秋葵切片烘干，清脆口感，补充膳食纤维。"),
    ("p008", "鸡鸭双拼羊扇骨", "c_dried", 2990, 260, 111,
     [_img("fanbone")],
     "鸡鸭双拼裹羊扇骨，大块耐咬，适合中大型犬。"),
    ("p009", "冻干鸡肉粒", "c_freeze", 3990, 610, 289,
     [_img("freezechicken")],
     "-38℃ 冻干锁鲜鸡胸肉粒，高蛋白低脂肪。"),
    ("p010", "芝士鸡肉块", "c_cheese", 2590, 380, 154,
     [_img("cheese")],
     "浓郁芝士裹鸡胸，香浓诱人，奖励神器。"),
    ("p011", "三文鱼美毛饼", "c_coat", 3290, 290, 98,
     [_img("salmon")],
     "深海三文鱼富含 Omega-3，助力美毛亮肤。"),
    ("p012", "南瓜鸡肉脆饼", "c_cookie", 1890, 470, 132,
     [_img("pumpkin")],
     "南瓜+鸡胸烘烤脆饼，酥脆可口，易消化。"),
    ("p013", "苹果鸡肉粒", "c_fruit", 2190, 350, 87,
     [_img("apple")],
     "苹果丁裹鸡胸肉，果香清新，维生素补充。"),
    ("p014", "低温灭菌鸡肉鲜食", "c_fresh", 4590, 200, 76,
     [_img("fresh")],
     "低温慢煮+灭菌工艺鲜食，开袋即食，冷链发货。"),
]

# (id, image, title)
BANNERS = [
    ("b1", "https://picsum.photos/seed/banner1/750/360", "新品上市"),
    ("b2", "https://picsum.photos/seed/banner2/750/360", "满减优惠"),
    ("b3", "https://picsum.photos/seed/banner3/750/360", "会员日"),
]

# (thresholdFen, giftFen, label, sub)
RECHARGE_TIERS = [
    (50000, 3000, "满500元", "赠送30元"),
    (100000, 10000, "满1000元", "赠送100元"),
]


def run_seed() -> dict:
    """灌种子数据（幂等），返回各类新增条数。"""
    added = {"categories": 0, "products": 0, "banners": 0, "recharge_tiers": 0}

    for sort, (cid, name) in enumerate(CATEGORIES):
        if db.session.get(Category, cid) is None:
            db.session.add(Category(id=cid, name=name, sort=sort))
            added["categories"] += 1

    for sort, (pid, title, category_id, price_fen, stock, sold, images, desc) in enumerate(PRODUCTS):
        if db.session.get(Product, pid) is None:
            db.session.add(Product(
                id=pid, title=title, category_id=category_id, price_fen=price_fen,
                stock=stock, sold=sold, images=images, description=desc, sort=sort,
            ))
            added["products"] += 1

    for sort, (bid, image, title) in enumerate(BANNERS):
        if db.session.get(Banner, bid) is None:
            db.session.add(Banner(id=bid, image=image, title=title, sort=sort))
            added["banners"] += 1

    if RechargeTier.query.count() == 0:
        for sort, (threshold_fen, gift_fen, label, sub) in enumerate(RECHARGE_TIERS):
            db.session.add(RechargeTier(
                threshold_fen=threshold_fen, gift_fen=gift_fen, label=label, sub=sub, sort=sort,
            ))
            added["recharge_tiers"] += 1

    db.session.commit()
    return added
