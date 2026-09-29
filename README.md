# pet-back 宠物商城后端

Flask + SQLAlchemy(SQLite) + gunicorn，为 `pet-mini` 小程序端与 `pet-web` 管理后台提供 API。

详细文档：[docs/architecture.md](docs/architecture.md)（架构与约定）、[docs/current.md](docs/current.md)（进度交接与遗留）。

## 环境要求

- Python 3.12（`.python-version` 已固定，由 uv 自动匹配）
- [uv](https://docs.astral.sh/uv/)（已用 brew 安装；虚拟环境建在 `pet-back/.venv`，不污染系统环境）

## 快速开始

```bash
cd pet-back
make setup    # uv sync 安装依赖（首次）
cp .env.example .env   # 可选，默认配置即可本地联调
make reset    # 建表 + 灌种子数据（阶段F 起仅创建初始超管 admin，不再灌任何伪造业务数据）
make serve    # gunicorn 启动：http://127.0.0.1:8000
# 或 make dev # Flask 调试模式（带 reload）
```

## 小程序联调切换

`pet-mini/config/index.js`：

```js
useMock: false,
baseURL: 'http://127.0.0.1:8000/api/v1/client',
```

微信开发者工具需勾选「不校验合法域名」。接口路径、响应结构与 Mock 完全一致，页面/services 零改动。

## 接口约定

- 命名空间：小程序端 `/api/v1/client/...`；管理端 `/api/v1/admin/...`（pet-web 管理后台）。
- 统一响应体 `{code, data, message}`：`0` 成功；`400` 业务错误；`401` 未登录；`404` 不存在；`500` 服务异常。HTTP 状态码与 body code 一致。
- 认证：`Authorization: Bearer <token>`；受保护路径 `/cart`、`/orders`、`/user`、`/addresses`、`/auth/profile`（`/payments/notify` 为微信回调，免登录但验签）。
- 金额一律「分」（整数）；时间戳一律毫秒整数。

### 接口清单（对齐 pet-mini mock/server.js）

小程序端 `/api/v1/client`：

| 方法 | 路径 | 说明 | 登录 |
|---|---|---|---|
| POST | /auth/wechat-login | 微信登录（{code, phoneCode}：换 openid + 授权手机号并绑定，未授权不能登录；轮换 token） | - |
| GET | /auth/profile | 当前用户快照 | 是 |
| GET | /home/banner | 首页轮播 | - |
| GET | /home/entries | 首页功能入口 | - |
| GET | /categories | 分类列表 | - |
| GET | /products | 商品列表（categoryId/keyword/sort/order/page/pageSize） | - |
| GET | /products/:id | 商品详情（含 categoryName） | - |
| GET | /shipping/config | 运费规则（基础运费 + 包邮门槛，供详情页/购物车/结算页展示包邮标识） | - |
| GET | /cart | 购物车（join 商品实时价格） | 是 |
| POST | /cart/add | 加购（校验单笔上限） | 是 |
| POST | /cart/update | 改数量/勾选（qty<=0 即删） | 是 |
| POST | /cart/remove | 删除行 | 是 |
| GET | /addresses | 收货地址列表 | 是 |
| POST | /addresses/add | 新增地址（首个自动默认） | 是 |
| POST | /addresses/update | 修改地址/设默认 | 是 |
| POST | /addresses/remove | 删除地址（自动补默认） | 是 |
| GET | /orders | 订单列表（tab：''/PENDING_PAY/PAID_UNSHIPPED/SHIPPED/AFTER_SALE） | 是 |
| POST | /orders/create | 下单（需 deliveryType+addressId）→ 待付款 PENDING_PAY | 是 |
| GET | /orders/:id | 订单详情 | 是 |
| POST | /orders/:id/cancel | 取消待付款单（PENDING_PAY→CLOSED） | 是 |
| POST | /orders/:id/confirm | 确认收货（SHIPPED→COMPLETED，终态不可自助退） | 是 |
| POST | /orders/:id/refund | 申请退款（整单全额，生成 PENDING 售后单；未发货/已发货可申） | 是 |
| POST | /orders/:id/refund/revoke | 撤回退款申请 | 是 |
| POST | /orders/:id/pay | 发起支付（body.method=`wechat`默认/`balance`，**不可混用**，余额不足则 400）| 是 |
| GET | /orders/:id/payment | 查本订单已支付单（对账/展示） | 是 |
| POST | /payments/notify | 微信支付结果回调（验签+幂等；按 `RC` 前缀路由到充值） | 否(验签) |
| POST | /payments/refunds/notify | 微信退款结果回调（验签+幂等；REFUNDING→REFUNDED） | 否(验签) |
| GET | /user/balance | 当前余额 | 是 |
| POST | /user/profile | 更新用户资料（当前仅昵称） | 是 |
| POST | /user/phone/rebind | 换绑手机号（重走 getPhoneNumber 授权） | 是 |
| GET | /user/recharge-tiers | 可充档位（含 id，用户只能点选） | 是 |
| POST | /user/recharge/prepay | 按档位预下单充值 `{tierId}`（金额/赠送服务端算定，入账由回调驱动） | 是 |
| GET | /user/recharge/record | 轮询充值单到账 `?paymentNo=` | 是 |
| GET | /user/recharge-records | 我的充值记录（仅已到账，分页） | 是 |
| GET | /user/favorites | 收藏列表 | 是 |
| POST | /user/favorites/toggle | 收藏/取消收藏 | 是 |

管理端 `/api/v1/admin`（账号密码登录，与用户 token 完全隔离）：

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| POST | /auth/login | 管理员登录（返回 token，轮换） | - |
| POST | /auth/logout | 登出（清当前 token） | 管理员 |
| GET | /auth/me | 当前管理员（含 isSuper） | 管理员 |
| POST | /auth/change-password | 改自己密码（成功后 token 全失效） | 管理员 |
| GET | /orders | 全部订单（status/keyword：订单号/收货人/电话/订单id；afterSale=1 只看待处理售后） | 管理员 |
| GET | /orders/:id | 订单详情 | 管理员 |
| POST | /orders/:id/ship | 发货（录入 carrier+shipNo；自提仅需 shipNo） | 管理员 |
| POST | /orders/:id/refund | 管理员发起退款（refundFen 自定义，可部分；全额则订单转 REFUNDED） | 管理员 |
| GET | /after-sales | 待处理售后单列表（PENDING） | 管理员 |
| POST | /after-sales/:id/approve | 同意退款（全额则订单转 REFUNDED 并回退销量） | 管理员 |
| POST | /after-sales/:id/reject | 驳回退款（订单状态不变） | 管理员 |
| POST | /upload/image | 上传图片（multipart file）→ {url}（OSS/本地由 IMAGE_PROVIDER 定） | 管理员 |
| GET | /products | 商品列表（page/pageSize/keyword/categoryId/onSale，含下架） | 管理员 |
| POST | /products | 创建商品（title/categoryId/priceFen/images/desc/sort/onSale） | 管理员 |
| GET | /products/:id | 商品详情（含 onSale/sort） | 管理员 |
| PUT | /products/:id | 更新商品（部分字段） | 管理员 |
| PATCH | /products/:id/on-sale | 上/下架（{onSale}，保留在库可恢复） | 管理员 |
| DELETE | /products/:id | 物理删除 + 删 OSS/本地图（弱一致，不可恢复） | 管理员 |
| GET | /categories | 分类列表（含 productCount） | 管理员 |
| POST | /categories | 创建分类（name/sort） | 管理员 |
| PUT | /categories/:id | 更新分类 | 管理员 |
| DELETE | /categories/:id | 删除分类（有商品引用则 400） | 管理员 |
| GET | /users | 用户列表（page/pageSize/keyword 手机号/昵称，含订单数） | 管理员 |
| GET | /users/:id | 用户详情（余额/累计消费/最近 10 单） | 管理员 |
| POST | /users/:id/balance-adjust | 手动调整余额 `{amountFen,note}`（可负；测试用，记 source=ADMIN） | **超管** |
| GET | /recharge-tiers | 充值档位列表 | 管理员 |
| POST | /recharge-tiers | 新增档位 `{thresholdFen,giftFen,label,sub,sort}` | 管理员 |
| PUT | /recharge-tiers/:id | 更新档位 | 管理员 |
| DELETE | /recharge-tiers/:id | 删除档位（**至少保留一个**，否则 400） | 管理员 |
| GET | /shipping-config | 当前运费规则 | 管理员 |
| PUT | /shipping-config | 更新运费规则 `{baseFreightFen,freeThresholdFen}`（分；0=不收/不启用） | 管理员 |
| GET | /order-config | 交易配置（`{autoCompleteDays}` 自动确认/退款窗口天数） | 管理员 |
| PUT | /order-config | 更新交易配置 `{autoCompleteDays}`（1~365 天） | 管理员 |
| GET | /dashboard | 经营概览聚合（?period=today/month/custom&start=&end=；销售额/订单/买家/新客/退款 + 实时待办 + 累计资金口径分列） | 管理员 |
| GET | /export/orders · /export/products · /export/users | CSV 导出（utf-8-sig） | 管理员 |
| GET | /audit-logs | 操作溯源分页（仅超管） | **超管** |
| GET/POST/PUT/DELETE | /banners[/:id] | 广告牌 CRUD + 启停（enabled）+ 跳转商品（productId） | 管理员 |
| POST | /after-sales/:id/sync | 主动查渠道退款单补偿（REFUNDING→REFUNDED） | 管理员 |
| GET | /admins | 管理员列表 | 管理员 |
| POST | /admins | 创建管理员（username/password/displayName/isSuper/isActive） | **超管** |
| PUT | /admins/:id | 更新管理员（资料/密码/启用/超管；自保护） | **超管** |
| DELETE | /admins/:id | 删除管理员（不能删自己/最后一个启用超管） | **超管** |

## 目录结构

```
pet-back/
  wsgi.py               gunicorn/flask 入口
  Makefile              setup / dev / serve / seed / reset
  app/
    __init__.py         create_app 应用工厂
    core/               config / response(统一响应+错误处理) / security(Bearer Token) / constants(订单状态机)
    models/             user(+ApiToken) / catalog(Category,Product,Banner) / order(+OrderItem) / cart(+Favorite) / recharge / shipping(ShippingConfig)
    api/v1/
      client/           小程序端接口（auth/home/catalog/cart/order/user/address/payment/shipping）
      admin/            管理端（auth/order/aftersale/upload/product/category/user/admin_account/recharge_tier/shipping）
    services/           wechat(code2Session) / order_service(订单状态机) / catalog_service(商品分类用户管理员 CRUD) / payment_service / shipping_service(运费规则) / storage(图片 Local/OSS) / serializers
    database/           seed(种子数据，幂等) / cli(flask db seed|reset)
  instance/petstore.db  SQLite 数据文件（gitignore）
```

## 微信登录模式

- 默认 `WECHAT_MOCK_LOGIN=true`：不调微信接口，固定 openid（`mock_openid_dev`）模拟单一身份，本地联调开箱即用。
- 接真实微信登录：`.env` 中设 `WECHAT_MOCK_LOGIN=false` 并填 `WECHAT_APPID` / `WECHAT_SECRET`，走标准 jscode2session。

## 常用命令

```bash
make setup   # 安装依赖
make dev     # 调试启动（reload）
make serve   # gunicorn（127.0.0.1:8000，SQLite 本地固定单 worker）
make seed    # 灌种子（幂等）
make reset   # 删表重建 + 灌种子
```
