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
        auth / home / catalog / cart / order / user / contact
      admin/                      管理端预留命名空间 /api/v1/admin（占位，无接口）
    services/                     业务逻辑层（client 与未来 admin 复用）
      wechat.py                   code2Session（Mock/真实双模式）
      order_service.py            订单状态机全部流转逻辑
      serializers.py              模型 -> 响应 dict（字段名对齐 pet-mini Mock）
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

- 微信一键登录，**无独立注册**：`POST /auth/wechat-login {code}` → `services/wechat.code2session` 换 openid → 按 openid 找/建 User → 返回 `{token, user(publicUser), isNewUser}`。
- **双模式**（`WECHAT_MOCK_LOGIN`，经 .env 配置）：
  - `true`：不调微信接口，任何 code 映射到固定 openid `mock_openid_dev`（单一身份，本地演示）；
  - `false`：真实调用 `jscode2session`，需 `WECHAT_APPID/WECHAT_SECRET`。
- **Token 机制**：随机串存 `api_tokens` 表；每次登录**删旧发新（轮换）**，旧 token 立即失效（表现为 401，属正常）。无过期时间（本地阶段），生产前需加 TTL/清理。
- `publicUser` 序列化不暴露 `openid/token`。

## 6. 订单状态机（与 pet-mini config.orderStatus 一致）

```
PAID_UNSHIPPED（已付款未发货，订单仅此态创建，无“待付款”）
  ├─ 用户申请退款 → REFUND_REQUESTED ─ 用户撤回 → PAID_UNSHIPPED
  ├─ 商家同意退款/直接取消 → CANCELLED（终态；回补库存、回退销量）
  └─ 发货 → SHIPPED（不可取消/退款；Demo 由小程序“模拟发货”触发）
预留：CANCELLED → REFUNDING → REFUNDED（接入真实支付后启用，常量已定义）
```

- 全部流转校验集中在 `services/order_service.py`；非法流转返回 400。
- 下单副作用：扣库存、加销量、写订单行快照（标题/图/单价锁定）、清购物车对应行。
- 列表 `status=PAID_UNSHIPPED` 为「未发货」tab 分组过滤（含 `REFUND_REQUESTED`）。
- `POST /orders/:id/cancel` 语义是**商家侧**操作，当前挂在 client 端供小程序 Demo 按钮使用，未来应迁到 `/api/v1/admin` 并换管理员鉴权（service 层无需改动）。

## 7. 数据模型

| 表 | 关键字段 | 说明 |
|---|---|---|
| users | id(u+hex), openid(唯一), nickname, avatar, balance_fen, points, coupons | 微信用户 |
| api_tokens | user_id, token(唯一), created_at | 登录态，登录时轮换 |
| categories | id(字符串如 c_dried), name, sort | 种子 id 与 Mock 兼容 |
| products | id(p001…), title, category_id, price_fen, stock, sold, images(JSON), desc, sort | desc 列属性名为 description（避开 Python 关键字语义） |
| banners | id, image, title, sort | 首页轮播 |
| orders | id(o+hex), order_no(NO+毫秒), user_id, total_fen, status, 四个毫秒时间戳 | 未发生的时间戳为 0（与 Mock 一致） |
| order_items | order_id, product_id, title, image, price_fen, qty | 下单快照 |
| cart_lines | (user_id, product_id) 唯一, qty, checked | 渲染时实时 join 商品 |
| favorites | (user_id, product_id) 唯一 | 收藏 |
| recharge_tiers | threshold_fen, gift_fen, label, sub | 充值满赠档位（赠送额服务端计算，不信任前端） |
| recharge_records | user_id, amount_fen, gift_fen, created_at | 充值流水 |

- ID 策略：分类/商品用**种子字符串 id**（与小程序数据兼容）；用户/订单用 `前缀+uuid hex`。
- **无迁移工具**：`create_all()` 只建新表、不会给已有表加列。模型加字段后要么 `make reset`（清空业务数据），要么手工 `ALTER TABLE`（后续可引入 Alembic 或轻量补列逻辑）。

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

- `app/database/seed.py`：11 分类、14 商品、3 banner、2 充值档位，内容照搬 `pet-mini/mock/db.js`（id/价格/库存/图片/文案一致），保证前后端数据同源。
- **幂等**：按主键存在即跳过，不覆盖运行期产生的库存/销量变化。
- 命令：`flask db seed`（灌种子）/ `flask db reset`（drop_all + create_all + 灌种子，清空全部业务数据）。

## 10. 与 pet-mini 的对接

- 切换点仅 `pet-mini/config/index.js`：`useMock: false` + `baseURL: 'http://127.0.0.1:8000/api/v1/client'`；开发者工具勾选「不校验合法域名」。
- 契约对齐的权威参照是 `pet-mini/mock/server.js`：**改接口响应结构前先看 Mock 对应 handler**，两边字段必须一致。
- Mock 路由的「静态路径先于 `:param`」约定在 Flask 中体现为：`/products/recommend` 的注册先于 `/products/<product_id>`（catalog.py 内有注释）。

## 11. 管理端（pet-web）扩展约定

- 新接口一律放 `app/api/v1/admin/`，按资源建子蓝图（参照 client 目录组织）。
- 鉴权独立实现（管理员账号体系），**不复用** client 的 `@login_required`。
- 业务逻辑优先复用 `app/services`（订单取消/发货、商品管理等）；service 不足时在 service 层补，不在接口层写规则。

## 12. 编码约定

- 模块/文件 snake_case；接口层函数动词开头（`create_order`/`list_orders`）。
- 响应字段 camelCase（对齐前端）；模型属性 snake_case；两者转换只发生在 `serializers.py`。
- 业务错误 `raise ApiError(400, "...")`，资源不存在 `ApiError(404, "...")`，不要在接口层手工拼 err 响应。
- 新增接口后同步：README 接口清单、`scripts/smoke_test.sh` 冒烟断言。
