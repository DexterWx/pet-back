# pet-back 现状交接（Current Status）

> 接手前请先阅读 [architecture.md](./architecture.md)。本文描述"当前做到哪、怎么跑、哪些是假设/遗留"。
> 最近更新：功能全部完成（A–G + F + 补齐批次①→⑦），冒烟 128/0；当前只剩**部署上线 + 等 ICP 备案**（见仓库根 `DEPLOY.md`）。临时用 cpolar 公网域名访问管理后台给人测试。

## 1. 一句话现状

订单系统已重构为**专业状态机**（阶段B）：`PENDING_PAY 待付款 → PAID_UNSHIPPED 待发货 → SHIPPED 已发货`，待付款超时/取消→`CLOSED`；退款走独立 `after_sales` 表（用户申请全额 / 管理员发起自定义额，管理员同意/驳回）。无库存（下单现做，销量在支付成功时累加）。管理端 `/api/v1/admin`（账号密码登录 + 独立 token）提供发货/发起退款/售后处理。头像不再持久化（阶段A 回退）。

> 阶段状态：**A–G + F（管理后台）+ 补齐批次①→⑦ 全部完成并验证**（微信支付/手机号/OSS 均真实联调；冒烟 128/0）。订单状态机含 `COMPLETED` 终态与退款窗口/驳回锁定；退款已异步化（REFUNDING + 回调/查单补偿 + 防超退）。**剩下的不是开发而是部署：上线步骤与 `.env` 生产切换见仓库根 `DEPLOY.md`，当前在等 ICP 备案。**

## 2. 如何运行

```bash
cd pet-back
make setup          # 首次：uv sync 安装依赖（.venv 在项目内）
make reset          # 建表 + 灌种子（阶段F 起仅创建 1 超管 admin + 默认充值档位，不灌商品/分类/Banner）
make serve          # gunicorn http://0.0.0.0:8000（带访问日志；绑 0.0.0.0 以支持小程序真机联调）
make lan-url        # 打印当前局域网地址与自检 URL（真机联调用）
# 或 make dev       # Flask 调试模式（reload）
```

> 开发服务监听 `0.0.0.0` 意味着**同一局域网内其他设备（含手机）可直连本后端**，仅适合开发机；
> 若只想本机访问，改回 `-b 127.0.0.1:8000`（代价是真机无法联调）。公网暴露必须走 cpolar/反向代理 + 上线前收紧。

管理后台：`cd pet-web && npm install && npm run dev`（Vite :5173，`/api`+`/uploads` 代理到 :8000；`VITE_BACKEND` 可覆盖后端地址），登录 `admin/admin123`。

冒烟验证（服务需已启动）：`./scripts/smoke_test.sh`，期望输出 `通过 128, 失败 0`（同一库反复跑时“余额不足”用例会因余额已积高而计为跳过 → 127）。脚本已重写为**自举式**（管理端建分类/商品再跑客户端下单支付售后全链路，最后测上下架/删除/账号管理/改密/充值与余额支付/运费规则/后台调余额），可重复运行；需 `WECHAT_MOCK_LOGIN=true PAYMENT_PROVIDER=mock WECOM_NOTIFY_ENABLED=false` 起服务（后者避免往真实企业微信群刷测试消息），可用 `SMOKE_HOST=host:port` 指向隔离端口。

小程序联调：`pet-mini/config/index.js` 已置 `useMock: false`，`baseURL` 由顶部 `DEV_HOST`（电脑局域网 IP）+ `DEV_PORT` 拼装，**模拟器与真机共用**；换网络后跑 `sh pet-mini/scripts/set-dev-host.sh` 自动回写（真机用 127.0.0.1 必定“加载失败”）。开发者工具需勾选「不校验合法域名」。

## 3. 已完成功能清单

- 基础设施：应用工厂、统一响应 `{code,data,message}`（HTTP 状态码与 body code 一致）、全局错误兜底（ApiError/HTTPException/未捕获异常）、CORS。
- 认证：微信登录（code2Session 双模式）、按 openid 找/建用户、Token 入库 + 登录轮换、`@login_required` Bearer 解析、401 语义与前端 request 层约定一致。
- 目录：分类列表、商品列表（分类筛选/关键词/销量价格排序/分页 hasMore）、详情（含 categoryName）。（阶段F 后取消了“为您推荐”功能，/products/recommend 已移除。）
- 首页：banner（查表）、entries（静态配置）。
- 购物车：增/改（qty<=0 即删）/删/查，库存校验，行数据实时 join 商品价格库存。
- 订单：创建（扣库存/加销量/快照/清购物车）、列表（未发货 tab 分组）、详情、模拟发货、退款申请/撤回、取消（回补库存回退销量），状态机集中在 order_service。
- 用户：资料更新（昵称 trim≤20 校验）、余额、充值档位、充值入账（**赠送额服务端按档位计算，不信任前端**，记流水）、收藏 toggle/列表。
- 数据：11 张表；种子数据幂等（`flask db seed` / `flask db reset`）；**阶段F 起种子仅创建初始超管，分类/商品/Banner/充值档位均不再灌伪造数据**（改由管理端创建）。
- **管理端（阶段F 第一批）**：商品 CRUD + 上下架（`on_sale`）+ 物理删除（同步删 OSS/本地图，弱一致）、分类 CRUD（删除校验商品引用）、用户列表/详情（含订单数/累计消费）、管理员多账号 CRUD（`is_super` 超管，`super_required` 403 拦非超管）+ 改密；业务集中 `catalog_service.py`。client 端已过滤下架商品（列表/详情/购物车/下单）。轻量补列迁移 `_auto_migrate()`（幂等 ALTER，保数据）。
- 文档：README（接口清单/命令/联调步骤）+ 本 docs 目录 + `pet-web/SPEC.md`（管理后台）。
- **企业微信通知（批次②）**：`services/notify.py` 群机器人推送「新订单已支付」（`payment_service._settle_payment` 内，仅本次真的转已付时）与「用户退款申请」（`order_service.apply_refund`）。**尽力而为**：均在 commit 后调用、异常只记 warning 绝不抛出；`WECOM_WEBHOOK_URL` 为空或 `WECOM_NOTIFY_ENABLED=false` 则静默跳过（跑冒烟/本地开发必关，否则刷真实群）。
- **充值真实化与余额支付（批次③）**：
  - 充值不再直接入账！`recharge_records` 扩展支付字段（payment_no/`RC`前缀、transaction_id、prepay_id、provider、status、payer_openid、tier_id、paid_at），由 `_auto_migrate()` 幂等补列；`POST /user/recharge/prepay {tierId}` 预下单，**入账发生在支付回调到账后**（`handle_payment_notify` 按 `RC` 前缀路由到 `_settle_recharge`）。
  - **旧的 `POST /user/recharge`（无支付直接加余额）已下线**，这是一开始最大的资金安全隐患。
  - 档位只能点选：`/user/recharge-tiers` 返回含 id 的多档位；后台 `GET/POST/PUT/DELETE /admin/recharge-tiers`，**至少保留一个档位**（仅剩一条时删除返回 400），seed 会写入默认档「充1000送100」。
  - 下单支付方式 `PayMethod`：`wechat`（默认）/ `balance`，**不可混用**、余额支付**不设密码**；余额不足 400。余额支付建 `provider='balance'` 已付支付单，其售后退款**退回余额**（`refund_after_sale` 按支付单 provider 分流，避免误调微信退款）。
- **运费体系（批次④）**：新增 `shipping_configs`（单行，全局一套：`base_freight_fen` + `free_threshold_fen`）与 `shipping_service.py`；`orders` 新增 `goods_total_fen`/`freight_fen` 并在下单时快照（`_auto_migrate()` 补列 + 历史订单 `goods_total_fen` 回填为原 `total_fen`）。规则：自提免运费 → 商品金额达门槛免运费 → 否则收基础运费；**免邮只看商品金额**；未配置=全站包邮（不影响存量行为）。接口：client `GET /shipping/config`（免登录，供前端展示包邮标识）、admin `GET/PUT /shipping-config`。
- **订单完成态与退款窗口（批次⑤）**：新增 `COMPLETED` 终态（不再以 SHIPPED 为履约终态）+ `orders.completed_at/complete_source`；`confirm_receive`（SHIPPED→COMPLETED）与 `auto_complete_if_due`（发货满 N 天惰性自动确认，有 PENDING 售后单则跳过）。退款窗口 `can_user_refund`：未发货随时、已发货仅 N 天内、已完成不可自助退；**被驳回过的订单永久锁定自助申请**；`ADMIN_REFUNDABLE` 含 COMPLETED（管理员强制退后门）。`ship_order` 自提不再要求任何单号。N 从环境变量升级为后台可配：新增 `order_configs`（单行，`auto_complete_days` 默认 7）+ admin `GET/PUT /order-config`；`get_auto_complete_days` 优先读库、回退 env、再回退 7（请求级缓存于 g）。序列化下发 `canRefund/canConfirm/refundDeadlineAt`。
- **退款链路异步化（批次⑤剩余）**：同意/直接发起退款先进 `REFUNDING`（全额退订单同步 REFUNDING），渠道到账后 `finalize_refund`（幂等）才转 REFUNDED + 回退销量。同步渠道（余额/mock/无支付单）发起后立即 finalize；微信异步，等 `POST /payments/refunds/notify`（免登录，按 out_refund_no='R'+售后单id 反查）或 admin `POST /after-sales/:id/sync`（`provider.query_refund` 主动查单补偿）。**防累计超退**：`_committed_refund_fen`(REFUNDING+REFUNDED 之和)+本次 ≤ 订单总额，否则 400。provider 抽象新增 `parse_refund_notify`/`query_refund`（wechat 实现，mock 返回 None/SUCCESS）。
- **后台余额调整（测试用）**：`POST /admin/users/:id/balance-adjust`（**仅超管**，`{amountFen,note}`，可负），记 `source=ADMIN/provider=admin` 流水，与用户真实充值严格区分（仪表盘不得将其计入“充值预收”）；服务端禁止负余额/金额为 0/单次超 100 万元。用户侧 `/user/recharge-records` 仅返回 `source=USER`。
- **Banner 管理（批次⑥）**：`banners` 加 `enabled` 列（`_auto_migrate` 补列，存量默认启用）；admin `GET/POST/PUT/DELETE /banners`（CRUD + 启停，删除时尽力删图）；client `/home/banner` 仅返回启用项。
- **仪表盘/导出/安全（批次⑦）**：admin `GET /dashboard`（轻聚合；销售额=已支付未整单退 total_fen；充值预收仅 source=USER；后台调余额/赠送/余额消费分列不混算）；`GET /export/{orders,products,users}`（CSV utf-8-sig）；token 滑动过期（client 30d/admin 12h，`security._slide` 过半续期）；admin 登录限流（10 次/15 分钟 → 429，内存计数）；`admin_audit_logs` + `GET /audit-logs`（仅超管）+ 关键写操作埋点（`services/audit.py`）。

## 4. 已做验证

- `uv sync`、`flask db reset/seed`、gunicorn 启动均正常；全部 `.py` 过 `compileall`。
- `scripts/smoke_test.sh` **56 项断言全部通过**，覆盖：登录/isNewUser/token 轮换旧 token 401、401 拦截、商品筛选排序分页搜索、404 商品、购物车全操作与库存校验、下单扣库存清购物车、退款申请↔撤回↔取消回补库存、发货后拒绝退款取消、空订单 400、资料更新与空昵称 400、充值满赠、收藏 toggle、未知路径 404。
- 小程序端真实联调走通：切换 `useMock=false` 后首页/分类等页面请求真实后端（期间确认了旧 Mock token 401 属预期、gunicorn 访问日志需 `--access-logfile -`）。
- 真实微信 `jscode2session` 全链路已验证（2026-09-19）：开发者工具 `wx.login` → 后端换得真实 openid 入库（users 表出现非 `mock_openid_dev` 的 openid 且带有效 token）。鉴别方法：Mock 模式入库的 openid 恒等于常量 `mock_openid_dev`，其余即微信下发真值。
- 数据核对：`scripts/query_db.py`（只读查库）已投入使用，`uv run python scripts/query_db.py --mode user` 查全部用户（金额换算元、毫秒时间戳转可读、显示含中文对齐的表格），支持 `--openid` 模糊过滤与 `--limit`；后续扩展订单等查询在 `MODES` 注册新 mode。
- 未做：并发/性能测试；单元测试（当前只有 shell 冒烟 + 查库脚本人工核对）。

## 5. 关键假设与决策（接手勿随意推翻）

- **接口契约以 `pet-mini/mock/server.js` 为权威**：字段名 camelCase、金额分、毫秒时间戳（未发生为 0）、错误文案都对齐 Mock，改任何一边必须同步另一边。
- URL 带 `/api/v1/client` 命名空间是为 **pet-web 管理端**预留（admin 蓝图已占位）；小程序 baseURL 含该前缀，不是遗漏。
- gunicorn 固定 **单 worker**：SQLite 写锁限制，本地阶段够用；上生产换 PostgreSQL 前不要加 worker。
- Token 是**数据库随机串**（非 JWT），登录即轮换、无过期；简单可控，管理端不要复用这套鉴权。
- 订单取消/发货接口暂挂 client 端（小程序 Demo 按钮需要），语义上是商家操作，管理端上线时应迁移。
- 充值无真实资金流：支付成功即入账（与小程序 Mock 支付一致）；接入微信支付后需补支付回调与对账。
- 种子商品/分类 id 为字符串（p001/c_dried），前端有引用，**不要改成自增整数**。
- `.env` 当前为真实微信模式（`WECHAT_MOCK_LOGIN=false` + 正式 appid/secret）；需要无凭证联调时改回 `true`（固定 openid `mock_openid_dev`，全员同一账号）。

## 6. 遗留 / 待办（Next）

- **（最优先）pet-mini 适配新后端**：新增 `address.service.js` 与地址管理页；确认订单页选地址+配送方式并传 `deliveryType`+`addressId`；商品详情去掉库存；订单详情展示物流单号/收货人并移除 Demo 发货/取消按钮；config 补 REFUNDING/REFUNDED 文案与 deliveryType。**`/orders/create` 现在强制要求 `addressId`，不改会直接下单失败。**
- ~~契约权威~~ 已失效：`pet-mini/mock/` 已于阶段 A 整体删除，真实后端为唯一契约。
- ~~微信支付建模~~ **已完成（C）**：`payments` 表 + provider 抽象（mock/wechat）+ 预下单/回调幂等/退款联动；真实微信支付已联调到账。待补：掉单主动查单补偿、退款回调驱动 REFUNDING→REFUNDED（当前退款为同步记账态）。
- ~~手机号 + 一键授权~~ **已完成（D）**：`/auth/wechat-login` 需 `{code, phoneCode}`（code2session + getuserphonenumber，openid+手机号一起入库）；未授权不能登录。`users.phone` 索引、非全局唯一；换绑 `/user/phone/rebind`（重走 getPhoneNumber，不接短信不能改任意号）。
- 头像**不再持久化**（阶段 A 回退了上一轮的 `POST /user/avatar`）：`/user/profile` 只处理昵称，服务端不接收 avatar；小程序 chooseAvatar 仅本地展示。`storage.py` 与 `/uploads/<path>` 静态路由**保留**，供阶段 E 商品图床复用。
- 上传能力（阶段E 已完成）：`services/storage.py` 提供 `LocalStorage`/`OSSStorage` 双实现，`IMAGE_PROVIDER=local|oss` 切换；管理端 `POST /api/v1/admin/upload/image` 返回 URL（供 F 商品管理用）。OSS 需 Bucket 公共读 + AccessKey；未配置时 local 落 `instance/uploads`。
- ~~管理端扩展：商品管理、用户管理、管理员多账号 CRUD~~ **已完成（F 第一批）**：`catalog_service.py` + admin 子蓝图 product/category/user/admin_account，client 端同步过滤下架商品；前端 pet-web 已浏览器走通。
- 数据库迁移：引入 Alembic；单元测试：pytest + 内存 SQLite（本轮改动已用临时 test_client 脚本验证，未沉淀）。
- Token 过期与清理策略；操作审计（管理端需要）。
- 部署与生产化（**已集中记录到 [architecture.md 第 12 节](./architecture.md)，上线前逐条处理**）：换 PostgreSQL + 多 worker、CORS 收敛为域名白名单、HTTPS 域名、引入 Alembic。
- ~~order_no 并发撞号~~ **已修**：`core.constants.gen_order_no()` → `NO+毫秒+4 位随机`（长度 19）。
- ~~积分/优惠券~~ **已全链路删除**：`users.points/coupons` 无业务逻辑（永远为 0），已从模型/序列化/`/user/balance`/小程序「我的」/pet-web 用户页移除，并由 `_auto_migrate()` 安全删列（无索引依赖，已验证用户数据保留）。
- **F 第二批（pet-web 待做）**：`/dashboard` 仪表盘、Banner 管理（当前 Banner 已清空、无管理界面）。~~充值档位管理~~ **已完成（批次③，菜单「充值活动」）**。

## 7. 接手易踩坑（Gotchas）

- **改 .env 必须完全重启 gunicorn**：`load_dotenv` 只在进程启动时读一次，`kill -HUP` 热重载无效。
- **小程序真机“加载失败，请重试”**：第一优先查 `pet-mini/config/index.js` 的 `DEV_HOST` 是否为电脑局域网 IP（手机上的 127.0.0.1 是手机自己），第二优先查后端是否绑了 `0.0.0.0`（只绑 127.0.0.1 时即使 IP 正确也连不上）。两者都已处理，换网络后跑 `sh pet-mini/scripts/set-dev-host.sh` 即可；工具的「局域网模式」不能代替修复。
- **包名 `app/database` 而非 `app/db`**：`app.db` 会与 `models` 导出的 `db` 实例属性冲突（`AttributeError: module 'app.db' has no attribute 'create_all'`），新建子包注意类似命名遮蔽。
- **路由注册顺序**：静态子路径必须先于 `/xxx/<param>` 通配注册，否则被通配抢先匹配（Flask 按注册顺序）；新增静态子路径同理。
- **Token 轮换**：重新登录后旧 token 立即 401，属正常；前端 request 层会自动清态跳登录。
- **HTTP 状态码=业务码**：err 响应 HTTP 也是 400/401/404/500，curl 调试时 `-w %{http_code}` 与 body code 应一致；前端按 `statusCode===200?0:statusCode` 归一化。
- **model 加字段不会自动建列**：`create_all()` 只建缺失的表；忘了这点会报 `no such column`。
- **冒烟脚本有副作用**：跑完数据库里有测试用户/订单，演示前记得 `make reset`。
- **`WECHAT_MOCK_LOGIN=false` 时**：开发者工具的 wx.login code 也能换 openid（appid 需与工具里的一致）；appid/secret 不匹配会返回 400「微信登录失败: errcode=40029」等明确错误。注意库里可能残留 Mock 期建的 `mock_openid_dev` 用户，用 `query_db.py` 查用户时注意区分，演示/交付前 `make reset` 清掉。
- 日志：访问日志靠 `--access-logfile -`（Makefile serve 已带）；应用内 `app.logger` 异常栈也在同一终端。

## 8. 关键文件速查

| 关注点 | 文件 |
|---|---|
| 应用工厂/建表 | `app/__init__.py` |
| 统一响应/错误处理 | `app/core/response.py` |
| Token 认证 | `app/core/security.py`、`app/models/user.py`（ApiToken） |
| 订单状态机 | `app/services/order_service.py`、`app/core/constants.py` |
| 微信登录（双模式） | `app/services/wechat.py`、`.env` |
| 字段对齐（改响应先看这） | `app/services/serializers.py`、`pet-mini/mock/server.js` |
| 接口路由 | `app/api/v1/client/*.py`（按资源分文件） |
| 种子数据 | `app/database/seed.py`（对照 `pet-mini/mock/db.js`） |
| 冒烟测试 | `scripts/smoke_test.sh` |
| 查库核对（只读） | `scripts/query_db.py`（`--mode user [--openid xxx] [--limit N]`） |
| 启动/运维命令 | `Makefile`、`README.md` |
