# pet-back 架构说明（Architecture）

> 适用范围：仅 `/pet-store/pet-back`（商城后端）。`pet-mini`、`pet-web` 为独立项目，本文只描述与它们的契约关系。
> 当前阶段：本地开发联调（SQLite 单文件库 + gunicorn 单 worker），无生产部署。
> 接手前请先读本文，再看 [current.md](./current.md) 了解进度与遗留。

## 1. 技术栈与运行形态

- Python **3.12**（`.python-version` 固定），依赖与虚拟环境由 **uv** 管理（`.venv` 在项目内，不污染系统环境）。
- Web 框架：**Flask 3**（应用工厂模式 `create_app()`，入口 `wsgi.py`）。
- ORM / 数据库：**Flask-SQLAlchemy + SQLite**（数据文件 `instance/petstore.db`，已 gitignore）。
- 启动：**gunicorn**，本地固定 `-w 1`（SQLite 单文件，多 worker 有写锁竞争问题）+ `--access-logfile -`（终端打印访问日志）。
- 服务对象：`pet-mini` 小程序端（已联调）；`pet-web` 管理端（命名空间已预留，未实现）。
- 金额统一以 **分（整数）** 存储与传输；时间戳统一为 **毫秒整数**（前端 `format.formatTime` 直接消费）。

## 2. 目录结构

```
pet-back/
  pyproject.toml / uv.lock        uv 项目定义与锁文件
  .python-version                 3.12
  .env.example / .env             环境变量模板 / 本地实际配置（.env 不入库）
  Makefile                        setup / dev / serve / seed / reset
  wsgi.py                         gunicorn/flask 入口：create_app()
  scripts/smoke_test.sh           全链路冒烟（56 项断言，需服务已启动）
  app/
    __init__.py                   应用工厂：配置、扩展、蓝图、错误处理、CLI、建表
    core/                         基础设施
      config.py                   读 env（.env 由 load_dotenv 启动时加载一次）
      response.py                 ok()/err()/ApiError + 全局错误处理器
      security.py                 Bearer Token 解析，@login_required
      constants.py                OrderStatus 状态机 / now_ms / gen_id / gen_token
    models/                       SQLAlchemy 模型（db 实例在 models/__init__.py）
      user.py                     User + ApiToken
      catalog.py                  Category / Product / Banner
      order.py                    Order + OrderItem（下单快照）
      cart.py                     CartLine + Favorite
      recharge.py                 RechargeTier + RechargeRecord
    api/v1/
      client/                     小程序端接口，前缀 /api/v1/client
        auth / home / catalog / cart / order / user / contact / address / payment
      admin/                      管理端 /api/v1/admin（pet-web 用）
        auth / order / aftersale / upload / product / category / user / admin_account
    services/                     业务逻辑层（client 与 admin 复用）
      wechat.py                   code2Session（Mock/真实双模式）
      order_service.py            订单状态机全部流转逻辑
      catalog_service.py          商品/分类/用户/管理员 CRUD（上下架/删除同步删图）
      payment_service.py          支付/退款联动 provider
      storage.py                  图片存储 Local/OSS 双实现（save_image/delete_image）
      serializers.py              模型 -> 响应 dict（client 对齐 pet-mini；admin_* 管理端）
    database/                     seed.py（幂等种子）+ cli.py（flask db seed|reset）
  instance/petstore.db            SQLite 数据文件（gitignore）
```

## 3. 分层与请求链路（核心约束）

```
gunicorn(wsgi:app)
  → api/v1/client|admin 接口层（参数解析、登录校验，不写业务规则）
    → services 业务层（状态机、微信调用；未来管理端复用同一层）
      → models 数据层（SQLAlchemy）
响应统一经 core/response（ok/err/ApiError → {code,data,message}）
```

- **接口层不写业务规则**：订单流转全部在 `services/order_service.py`；管理端未来直接调 service，不复制逻辑。
- **序列化集中在 `services/serializers.py`**：响应字段名与 pet-mini `mock/server.js` 逐一对齐（camelCase、`priceFen`、`hasMore`…），保证小程序从 Mock 切到真实后端**零改动**。
- **错误一律抛 `ApiError(code, message)`**，由全局错误处理器转统一响应；HTTP 状态码与 body code 保持一致（HTTPException/未捕获异常也被兜底成同结构）。

## 4. API 契约

- 命名空间：小程序端 `/api/v1/client/...`；管理端预留 `/api/v1/admin/...`。
- 响应体 `{code, data, message}`：`0` 成功；`400` 业务错误；`401` 未登录；`404` 不存在；`500` 服务异常。
- 认证：`Authorization: Bearer <token>`；受保护前缀 `/cart`、`/orders`、`/user` 及 `/auth/profile`，未登录 401。
- 完整接口清单见 [README.md](../README.md)（27 个，与 pet-mini services 层一一对应）。

## 5. 认证与登录态

- 微信一键登录，**无独立注册**：`POST /auth/wechat-login {code, phoneCode}` → `code2session` 换 openid + `getuserphonenumber` 换手机号 → 按 openid 找/建 User 并**绑定手机号** → 返回 `{token, user, isNewUser}`。
- **手机号强制**：`get_phone_number` 在真实模式下 `phoneCode` 缺失/无效 → **400，不允许登录**；手机号每次登录刷新（微信担保）。`phone` 存 `users.phone` 并建索引供后台搜索，但**不做全局唯一**（身份唯一靠 openid）。未接短信服务商，换绑 = 重新走 `getPhoneNumber`（`POST /user/phone/rebind`），不能改任意号。
- **access_token**：调手机号接口需小程序全局 access_token，`wechat.py` 用 appid/secret 拉取并**进程内缓存**（提前 5 分钟过期）；多实例部署应改共享缓存。
- **双模式**（`WECHAT_MOCK_LOGIN`，经 .env）：`true` 不调微信、固定 openid + Mock 手机号（`13800000000`）；`false` 真实 `jscode2session` + `getuserphonenumber`，需 `WECHAT_APPID/WECHAT_SECRET`。
- **Token 机制**：随机串存 `api_tokens` 表；每次登录**删旧发新（轮换）**，旧 token 立即失效（表现为 401，属正常）。无过期时间（本地阶段），生产前需加 TTL/清理。
- `public_user` 暴露 `phone` 供本人可见，不暴露 `openid/token`。

## 6. 订单状态机（与 pet-mini config.orderStatus 一致）

```
PENDING_PAY 待付款（下单即此态）
  ├─ 支付成功（回调调 mark_paid） → PAID_UNSHIPPED 待发货（累加销量）
  └─ 超时(TTL,默认30分,惰性判定)/用户取消 → CLOSED 已关闭（终态）
PAID_UNSHIPPED ─ 管理员发货 → SHIPPED 待收货
  （快递需物流公司+单号；**自提无需任何单号**，直接点发货）
SHIPPED ─ 用户确认收货 或 发货满 N 天自动确认 → COMPLETED 已完成（正向履约终态）
  自动确认走惰性判定（读取订单时 refresh_order_state 触发，不用定时任务）；
  有 PENDING 售后单时不自动完成（防悬空）；N = order_configs.auto_complete_days（后台可配，默认 7）。
售后退款（after_sales 表驱动，与履约状态解耦）：
  用户申请(整单全额) → AfterSale(PENDING)；退款窗口 can_user_refund：
    • PAID_UNSHIPPED 随时可退；SHIPPED 仅发货后 N 天内可退；COMPLETED 不可自助退；
    • 已被驳回过的订单永久不能再自助申请（_has_rejected_after_sale）。
    ├─ 管理员同意 → AfterSale(REFUNDING)；渠道到账后 finalize_refund → REFUNDED（全额则订单 REFUNDING→REFUNDED、回退销量）
    │     同步渠道（余额/mock/无支付单）发起后立即 finalize；微信为异步，等退款回调或查单补偿
    └─ 管理员驳回 → REJECTED（订单不变，但锁定自助再申请）
  管理员直接发起(金额自定义可部分, ADMIN_REFUNDABLE=PAID_UNSHIPPED/SHIPPED/COMPLETED) → AfterSale(REFUNDING)→到账 REFUNDED；
    全额则订单→REFUNDING→REFUNDED。**已完成订单用户不可自助退，但管理员仍可强制退（后门）**。
    注：全额直接发起会**合并关闭**该订单已有的用户 PENDING 申请单（置 REJECTED），防残留与二次退款。
  退款回调：POST /payments/refunds/notify（免登录）按 out_refund_no='R'+售后单id 反查，幂等 REFUNDING→REFUNDED。
  掉单补偿：admin POST /after-sales/:id/sync 主动查渠道退款单，SUCCESS 则 finalize。
  防累计超退：_committed_refund_fen(REFUNDING+REFUNDED 之和) + 本次退款 ≤ 订单总额，否则 400。
```

- 终态：`FINAL = (CLOSED, REFUNDED, COMPLETED)`。`SHIPPED` 不再是终态。
- 订单新增字段：`completed_at`、`complete_source`（USER 主动 / AUTO 自动 / '' 未完成）。
- 序列化 `order_payload` 下发 `canRefund/canConfirm/refundDeadlineAt/completedAt/completeSource`，前端只读布尔渲染，不重复实现窗口规则。

- 全部流转校验集中在 `services/order_service.py`；非法流转返回 400。`ship_order` 仅 `PAID_UNSHIPPED` 可发。
- **防二次退款**：`admin_approve_refund` 在订单已 `REFUNDED` 时拒绝同意（400）；`admin_initiate_refund` 会先合并关闭同订单的 PENDING 售后单。
- **无库存概念（下单现做）**：销量在**支付成功时**累加（非下单时）；全额退款回退销量；待付款关闭不涉销量。
- **配送方式 `DeliveryType`**：`EXPRESS`（快递，需完整地址）/ `SELF_PICKUP`（自提，仅需姓名+电话）；自提由管理端自定义提货单号。
- **列表 tab**：`''`全部 / `PENDING_PAY`未付款 / `PAID_UNSHIPPED`未发货 / `SHIPPED`已发货 / `AFTER_SALE`（有 PENDING 售后单的订单）。
- **运费规则（`shipping_service.calc_freight`）**：全站一套配置，下单时服务端算定并快照到订单（改配置不影响历史订单）。优先级：自提免运费 → 商品金额达 `free_threshold_fen` 免运费 → 否则收 `base_freight_fen`。**免邮判定只看商品金额合计**，不计运费本身；未配置（两值 0）= 全站包邮。
- **支付/发货/售后处理是商家侧/回调操作**，均在 `/api/v1/admin` 或支付回调；client 仅保留下单/支付/取消待付款/查/申请退款/撤回。
- **下单支付方式（`PayMethod`）**：`wechat`（默认）或 `balance`，**不可混用**；余额不足直接 400，不拆分支付。余额支付不弹收银台，服务端扣余额并建 `provider='balance'` 的已付支付单；对应的售后退款**退回余额**而非渠道（见 `payment_service.refund_after_sale` 按支付单 provider 分流）。
- **充值与订单共用一个支付回调地址**：`out_trade_no` 前缀 `RC` 路由到充值入账，其余为订单；两者均幂等且校验金额。

- **PENDING_PAY→PAID 由支付驱动**（阶段C）：provider 抽象在 `services/payment/`（mock/wechat）；mock 预下单即时成功（仅开发），wechat 走 `POST /orders/:id/pay` 预下单 + `POST /payments/notify` 回调（验签+幂等）调 `mark_paid`。退款：管理端同意/发起时 `payment_service.refund_after_sale` 联动 provider.refund 并回填 wx_refund_id。

## 7. 数据模型

| 表 | 关键字段 | 说明 |
|---|---|---|
| users | id(u+hex), openid(唯一), phone(索引,非唯一), nickname, avatar, balance_fen, created_at | 微信用户（avatar 不再持久化，总为空；phone 来自微信授权）。原 points/coupons 字段无业务逻辑，已全链路废弃并由 `_auto_migrate()` 删列 |
| api_tokens | user_id, token(唯一), created_at | 登录态，登录时轮换 |
| categories | id(字符串如 c_dried), name, sort | 种子 id（阶段F 起不再灌伪造种子，由管理端创建） |
| products | id(p001…), title, category_id, price_fen, sold, images(JSON), desc, sort, **on_sale**(bool,默认true) | **无 stock（下单现做）**；on_sale=false 为下架（client 端不可见/不可买，保留可恢复） |
| addresses | id(ad+hex), user_id, receiver_name, phone, province/city/district/detail, is_default | 收货地址簿（首个自动默认，一个用户仅一个默认） |
| admin_users | id(a+hex), username(唯一), password_hash, display_name, is_active, **is_super**(bool) | 管理员（werkzeug 密码哈希）；is_super 超管才能管理账号 |
| admin_tokens | admin_id, token(唯一), created_at | 管理员登录态，登录时轮换（与 api_tokens 隔离） |
| banners | id, image, title, sort, enabled(bool), product_id(可空) | 首页轮播/广告牌；enabled=False 小程序不展示；product_id 配了则点 banner 直达商品详情 |
| orders | id(o+hex), order_no(NO+毫秒+4位随机,唯一), user_id, total_fen, **goods_total_fen, freight_fen**, status, delivery_type, receiver_name/phone/address(快照), carrier, ship_no, created_at/paid_at/shipped_at/**completed_at/complete_source**/refund_requested_at/cancelled_at/refunded_at | status 取 PENDING_PAY/PAID_UNSHIPPED/SHIPPED/COMPLETED/CLOSED/REFUNDED；未发生时间戳为 0；`total_fen = goods_total_fen + freight_fen`（下单时快照）；complete_source=USER/AUTO 区分确认收货方式 |
| order_items | order_id, product_id, title, image, price_fen, qty | 下单快照 |
| after_sales | id(as+hex), order_id, user_id, source(USER/ADMIN), refund_fen, reason, status(PENDING/REJECTED/REFUNDING/REFUNDED), admin_id, admin_note, wx_refund_id, handled_at, created_at | 售后退款单，与订单履约状态解耦 |
| payments | id(pm+hex), order_id, payment_no(唯一=微信out_trade_no), transaction_id(唯一,可空), prepay_id, provider(**mock/wechat/balance**), amount_fen, status(CREATED/SUCCESS/CLOSED), payer_openid, raw_notify(JSON), paid_at, created_at | 支付单，一订单可多次预下单；由支付回调驱动订单转已付；provider=balance 为余额支付（不走渠道，退款也退回余额） |
| cart_lines | (user_id, product_id) 唯一, qty, checked | 渲染时实时 join 商品 |
| favorites | (user_id, product_id) 唯一 | 收藏 |
| recharge_tiers | id, threshold_fen, gift_fen, label, sub, sort | 充值活动档位：用户只能点选（不可自输金额）；后台可配多档，**必须至少保留一个** |
| recharge_records | user_id, amount_fen, gift_fen, created_at, payment_no(RC前缀,唯一), transaction_id, prepay_id, provider, status(PENDING/SUCCESS/CLOSED), payer_openid, tier_id, paid_at, **source(USER/ADMIN), admin_id, note** | 充值单/流水：走真实微信支付，**入账由支付回调驱动**；source=ADMIN 为后台手动调余额（测试用，可负，**无支付单、不计入充值预收**，也不出现在用户充值记录）；不提供退款入口 |
| shipping_configs | id(固定1), base_freight_fen, free_threshold_fen, updated_at | 运费规则（全局一套）；两值均为 0 即全站包邮（未配置时的默认） |
| order_configs | id(固定1), auto_complete_days(默认7), updated_at | 交易配置（全局一套）：发货后自动确认收货天数，同时是已发货订单的退款窗口；后台可配，无行时回退环境变量 ORDER_AUTO_COMPLETE_DAYS |
| admin_audit_logs | id, admin_id, username(快照), action, target, detail, ip, created_at | 管理端操作溯源；仅超管可查；username 快照防账号删除后失联 |

- ID 策略：分类/商品用**种子字符串 id**（与小程序数据兼容；阶段F 起新建用 `p+hex8`/`c+hex8`）；用户/订单用 `前缀+uuid hex`。
- **无迁移工具**：`create_all()` 只建新表、不会改已有表。字段变更走 `app/__init__.py:_auto_migrate()`：用 `PRAGMA table_info` 检查后幂等地 **补列（ADD）** 或 **删列（DROP，需 SQLite >= 3.35）**，保留其余数据；新增/删除模型字段时在此登记。
  已登记：补列 `products.on_sale`、`admin_users.is_super`（并把存量首个 admin 标为超管）；删列 `users.points`、`users.coupons`。

## 8. 配置与环境变量

| 变量 | 说明 |
|---|---|
| SECRET_KEY | Flask 签名密钥；当前认证不走 session，实际未使用，为管理端/CSRF 预留 |
| WECHAT_MOCK_LOGIN | true=Mock 登录（固定 openid）；false=真实 jscode2session |
| WECHAT_APPID / WECHAT_SECRET | 真实微信模式必填 |
| DATABASE_URL | 可覆盖，默认 `instance/petstore.db` |

- `.env` 由 `core/config.py` 的 `load_dotenv()` 在**进程启动时读取一次**；改完必须完全重启 gunicorn（`kill -HUP` 热重载不会重读环境变量）。
- `.env` 含密钥、已 gitignore；入库的是 `.env.example` 模板。

## 9. 种子数据

- `app/database/seed.py`：**阶段F 起仅创建初始超管管理员**（默认 admin/admin123）**与默认充值档位**（无档位时写入「充 1000 元、赠 100 元」）。分类/商品/Banner 等商品内容均不再灌伪造种子，全部改由管理后台（pet-web）真实创建；小程序端已支持这些内容为空时正常展示（空态）。
- **幂等**：仅当无任何管理员/无任何档位时才写入，不覆盖已有配置。
- Banner 管理界面属第二批（充值档位管理已上线）；补上之前 Banner 需直接改库或等第二批 UI。
- 命令：`flask db seed`（灌种子）/ `flask db reset`（drop_all + create_all + 灌种子，清空全部业务数据）。

## 10. 与 pet-mini 的对接

- 切换点仅 `pet-mini/config/index.js`：`useMock: false` + `baseURL: 'http://127.0.0.1:8000/api/v1/client'`；开发者工具勾选「不校验合法域名」。
- 契约对齐的权威参照是 `pet-mini/mock/server.js`：**改接口响应结构前先看 Mock 对应 handler**，两边字段必须一致。
- Flask 路由按注册顺序匹配：静态子路径需先于 `/xxx/<param>` 通配注册，否则被通配抢先匹配（如曾有 `/products/recommend` 先于 `/products/<product_id>`；推荐功能已移除）。

## 11. 管理端（pet-web / /api/v1/admin）

- **已实现**：`app/api/v1/admin/` 下按资源分子蓝图：`auth`（登录/登出/me/改密，含登录限流）、`order`（列表/详情/发货/发起退款）、`order_config`（交易配置：自动确认天数）、`aftersale`（待处理/同意/驳回/**同步退款状态**）、`upload`（图片上传）、`product`（商品 CRUD + 上下架）、`category`（分类 CRUD）、`user`（用户列表/详情/**余额调整**）、`admin_account`（管理员多账号 CRUD）、`recharge_tier`（充值档位 CRUD）、`shipping`（运费规则）、`banner`（Banner CRUD + 启停）、`dashboard`（经营概览聚合）、`export`（订单/商品/用户 CSV）、`audit`（操作溯源，仅超管）。
- **余额调整（测试用）**：`POST /users/:id/balance-adjust` 为**超管专属**（相当于凭空发行余额），记 `source=ADMIN/provider=admin` 流水；服务端禁止调成负数、禁止金额为 0、单次上限 100 万元。用户侧 `/user/recharge-records` 仅返回 `source=USER`，不暴露内部调账。
- **鉴权独立**：`AdminUser`（username 唯一 + werkzeug 密码哈希 + is_active + **is_super**）与 `AdminToken`（登录轮换）；`core/security.admin_required` 解析 Bearer，与小程序 `@login_required` 完全不互用。账号增删改为超管专属，走 `super_required`（非超管 403）。
- **业务分层**：目录/用户/账号规则集中在 `app/services/catalog_service.py`（商品上下架/删除同步删 OSS 图、分类删除校验引用、管理员自保护）；订单/售后复用 `order_service`。接口层不写业务规则。
- **初始账号**：`flask db seed/reset` 仅在无任何管理员时创建一个（默认 `admin` / `admin123`，**is_super=True**，可用 `SEED_ADMIN_USERNAME`/`SEED_ADMIN_PASSWORD` 覆盖）；**上线前必须改密**。
- **下架 vs 删除**：下架=`on_sale=false`（client 端列表过滤、详情 404、购物车隐藏、加购/下单 400；保留可重新上架）；删除=物理删库（先清 `cart_lines`/`favorites` 引用）+ 逐个 `storage.delete_image` 删 OSS/本地图（弱一致，失败仅记日志）。`order_items` 为下单快照（product_id 无外键），删商品不影响历史订单。
- 前端见 `pet-web/SPEC.md`（Vue3 + Element Plus，商品页左分类侧栏 + 右卡片网格镜像小程序结构）。

## 12. 上线前生产化待办（已识别、暂不处理）

> 本阶段为本地开发/小规模试运营，以下项故意未做，**正式对外上线前必须逐条处理**。

- **数据库：SQLite → PostgreSQL**
  - 现状：单文件 `instance/petstore.db` + gunicorn **固定 `-w 1`**（SQLite 写锁会阻塞多进程）。
  - 风险：并发写入串行化、文件锁互斥；流量上来后下单/回调会阻塞。
  - 要做：换 PostgreSQL → 才能开多 worker；同时引入 **Alembic** 替代理表式 `_auto_migrate()`（字段一多会失控）。
- **CORS 目前未收敛**
  - 什么是 CORS：**浏览器**的安全规则——网页 A 默认不能请求服务器 B 的接口，除非 B 明确允许。
  - 现状：`app/__init__.py` 里 `CORS(app)` = **允许任意源**调接口。
  - 为何当前风险低：① 小程序 `wx.request` 不受 CORS 约束，与此无关；② pet-web 开发走 Vite 代理、生产同源 Nginx反代，也是同源；③ 鉴权靠 `Authorization: Bearer` **请求头**传 token（不像 Cookie 会被浏览器自动携带），攻击者拿不到 token 就打不动。
  - 要做：pet-web 有独立域名后，把 `CORS(app)` 改为**显式 origin 白名单**（仅允许自己的管理后台域名），并配合 HTTPS。
- **Token 滑动过期（已实现）**：client 30 天 / admin 12 小时（`TOKEN_TTL_CLIENT_DAYS`/`TOKEN_TTL_ADMIN_HOURS`）；`security._slide` 在 age>TTL 判失效（401）、age>TTL/2 时续期 created_at（控制写放大）。
- **管理端登录限流（已实现）**：同一账号窗口（默认 15 分钟）内连续失败达上限（默认 10 次）返回 429 临时锁定；内存计数（单 worker），成功登录清零。
- **操作溯源（已实现）**：`admin_audit_logs` 记录关键写操作（login/改密/商品/分类/订单发货退款/售后同意驳回/调余额/账号/配置/banner），仅超管可查（`GET /audit-logs`）。
- **充值与余额**：充值单走真实微信支付且**不提供后台退入口**（按业务约定走客服线下处理）；余额可用于下单支付（不混用、无密码）。真实退款仍依赖回调驱动，上线前必验 `PAYMENT_PROVIDER=wechat` 与回调域名可达。

## 13. 编码约定

- 模块/文件 snake_case；接口层函数动词开头（`create_order`/`list_orders`）。
- 响应字段 camelCase（对齐前端）；模型属性 snake_case；两者转换只发生在 `serializers.py`。
- 业务错误 `raise ApiError(400, "...")`，资源不存在 `ApiError(404, "...")`，不要在接口层手工拼 err 响应。
- 新增接口后同步：README 接口清单、`scripts/smoke_test.sh` 冒烟断言。
