# pet-back 现状交接（Current Status）

> 接手前请先阅读 [architecture.md](./architecture.md)。本文描述"当前做到哪、怎么跑、哪些是假设/遗留"。
> 最近更新：后端从零搭建完成并已通过小程序真实联调（`useMock=false`）；微信登录已由 Mock 模式切换为真实 `jscode2session`（.env 配置了正式 appid/secret）。

## 1. 一句话现状

后端已完整实现 pet-mini Mock Server 的全部 27 个接口（`/api/v1/client` 命名空间），响应结构与 Mock 逐字段对齐，小程序零改动切换成功；56 项全链路冒烟全部通过；管理端 `/api/v1/admin` 仅占位。

## 2. 如何运行

```bash
cd pet-back
make setup          # 首次：uv sync 安装依赖（.venv 在项目内）
make reset          # 建表 + 灌种子（11 分类/14 商品/3 banner/2 充值档位）
make serve          # gunicorn http://127.0.0.1:8000（带访问日志）
# 或 make dev       # Flask 调试模式（reload）
```

冒烟验证（服务需已启动）：`./scripts/smoke_test.sh`，期望输出 `通过 56, 失败 0`。
注意：冒烟会写入测试用户/订单/充值数据，跑完可 `make reset` 恢复干净种子。

小程序联调：`pet-mini/config/index.js` 已置 `useMock: false` + `baseURL: http://127.0.0.1:8000/api/v1/client`；开发者工具勾选「不校验合法域名」。

## 3. 已完成功能清单

- 基础设施：应用工厂、统一响应 `{code,data,message}`（HTTP 状态码与 body code 一致）、全局错误兜底（ApiError/HTTPException/未捕获异常）、CORS。
- 认证：微信登录（code2Session 双模式）、按 openid 找/建用户、Token 入库 + 登录轮换、`@login_required` Bearer 解析、401 语义与前端 request 层约定一致。
- 目录：分类列表、商品列表（分类筛选/关键词/销量价格排序/分页 hasMore）、推荐（前 6）、详情（含 categoryName）。
- 首页：banner（查表）、entries（静态配置）。
- 购物车：增/改（qty<=0 即删）/删/查，库存校验，行数据实时 join 商品价格库存。
- 订单：创建（扣库存/加销量/快照/清购物车）、列表（未发货 tab 分组）、详情、模拟发货、退款申请/撤回、取消（回补库存回退销量），状态机集中在 order_service。
- 用户：资料更新（昵称 trim≤20 校验）、余额、充值档位、充值入账（**赠送额服务端按档位计算，不信任前端**，记流水）、收藏 toggle/列表。
- 数据：11 张表；种子数据幂等（`flask db seed` / `flask db reset`）；种子内容与 `pet-mini/mock/db.js` 同源。
- 文档：README（接口清单/命令/联调步骤）+ 本 docs 目录。

## 4. 已做验证

- `uv sync`、`flask db reset/seed`、gunicorn 启动均正常；全部 `.py` 过 `compileall`。
- `scripts/smoke_test.sh` **56 项断言全部通过**，覆盖：登录/isNewUser/token 轮换旧 token 401、401 拦截、商品筛选排序分页搜索、404 商品、购物车全操作与库存校验、下单扣库存清购物车、退款申请↔撤回↔取消回补库存、发货后拒绝退款取消、空订单 400、资料更新与空昵称 400、充值满赠、收藏 toggle、未知路径 404。
- 小程序端真实联调走通：切换 `useMock=false` 后首页/分类等页面请求真实后端（期间确认了旧 Mock token 401 属预期、gunicorn 访问日志需 `--access-logfile -`）。
- 未做：真实微信 `jscode2session` 全链路（.env 已配正式 appid/secret，但未见真机登录成功记录）；并发/性能测试；单元测试（当前只有 shell 冒烟）。

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

- **手机号 + 一键授权（已设计未实施）**：User 加 phone 字段、`POST /user/profile/authorize`（头像+昵称+getPhoneNumber code 一次提交）、微信 `getuserphonenumber` 接口（需企业认证主体、按次收费）、编辑资料页只读展示、`scripts/query_db.py` 查库脚本（`--mode user --phone`）。方案见对话记录，落地时注意：无迁移工具，加列需手工 `ALTER TABLE users ADD COLUMN phone VARCHAR(20) NOT NULL DEFAULT ''` 或 `make reset`。
- 头像上传：前端 `chooseAvatar` 是临时路径，后端需补上传接口（存本地/OSS）换正式 URL，否则头像跨设备失效。
- 管理端 `/api/v1/admin`：管理员认证、商品/订单管理（复用 services 层）。
- 数据库迁移：引入 Alembic（或轻量补列脚本），摆脱「加字段=清库」。
- 真实微信支付：下单流程改为 预下单→支付回调→建单；启用 `REFUNDING/REFUNDED` 退款资金流。
- Token 过期与清理策略；操作审计（管理端需要）。
- 单元测试：pytest + 内存 SQLite，把 smoke_test.sh 的断言沉淀为可重复测试。
- 部署：换 PostgreSQL、gunicorn 多 worker、HTTPS 域名（小程序正式环境要求 request 合法域名）。
- 新订单通知：企业微信群机器人 webhook 推送（见 pet-mini docs 遗留项，由后端实现）。

## 7. 接手易踩坑（Gotchas）

- **改 .env 必须完全重启 gunicorn**：`load_dotenv` 只在进程启动时读一次，`kill -HUP` 热重载无效。
- **包名 `app/database` 而非 `app/db`**：`app.db` 会与 `models` 导出的 `db` 实例属性冲突（`AttributeError: module 'app.db' has no attribute 'create_all'`），新建子包注意类似命名遮蔽。
- **路由注册顺序**：`/products/recommend` 必须先于 `/products/<product_id>` 注册（catalog.py 已处理），新增静态子路径同理。
- **Token 轮换**：重新登录后旧 token 立即 401，属正常；前端 request 层会自动清态跳登录。
- **HTTP 状态码=业务码**：err 响应 HTTP 也是 400/401/404/500，curl 调试时 `-w %{http_code}` 与 body code 应一致；前端按 `statusCode===200?0:statusCode` 归一化。
- **model 加字段不会自动建列**：`create_all()` 只建缺失的表；忘了这点会报 `no such column`。
- **冒烟脚本有副作用**：跑完数据库里有测试用户/订单，演示前记得 `make reset`。
- **`WECHAT_MOCK_LOGIN=false` 时**：开发者工具的 wx.login code 也能换 openid（appid 需与工具里的一致）；appid/secret 不匹配会返回 400「微信登录失败: errcode=40029」等明确错误。
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
| 启动/运维命令 | `Makefile`、`README.md` |
