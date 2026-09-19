# pet-back 宠物商城后端

Flask + SQLAlchemy(SQLite) + gunicorn，为 `pet-mini` 小程序端提供 API；管理端（`pet-web`）命名空间已预留。

详细文档：[docs/architecture.md](docs/architecture.md)（架构与约定）、[docs/current.md](docs/current.md)（进度交接与遗留）。

## 环境要求

- Python 3.12（`.python-version` 已固定，由 uv 自动匹配）
- [uv](https://docs.astral.sh/uv/)（已用 brew 安装；虚拟环境建在 `pet-back/.venv`，不污染系统环境）

## 快速开始

```bash
cd pet-back
make setup    # uv sync 安装依赖（首次）
cp .env.example .env   # 可选，默认配置即可本地联调
make reset    # 建表 + 灌种子数据（分类/商品/Banner/充值档位）
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

- 命名空间：小程序端 `/api/v1/client/...`；管理端预留 `/api/v1/admin/...`（本期未实现）。
- 统一响应体 `{code, data, message}`：`0` 成功；`400` 业务错误；`401` 未登录；`404` 不存在；`500` 服务异常。HTTP 状态码与 body code 一致。
- 认证：`Authorization: Bearer <token>`；受保护路径 `/cart`、`/orders`、`/user`、`/auth/profile`。
- 金额一律「分」（整数）；时间戳一律毫秒整数。

### 接口清单（对齐 pet-mini mock/server.js）

| 方法 | 路径 | 说明 | 登录 |
|---|---|---|---|
| POST | /auth/wechat-login | 微信登录（code 换 openid，找/建用户，轮换 token） | - |
| GET | /auth/profile | 当前用户快照 | 是 |
| GET | /home/banner | 首页轮播 | - |
| GET | /home/entries | 首页功能入口 | - |
| GET | /categories | 分类列表 | - |
| GET | /products | 商品列表（categoryId/keyword/sort/order/page/pageSize） | - |
| GET | /products/recommend | 推荐商品（前 6） | - |
| GET | /products/:id | 商品详情（含 categoryName） | - |
| GET | /cart | 购物车（join 商品实时价格/库存） | 是 |
| POST | /cart/add | 加购（校验库存） | 是 |
| POST | /cart/update | 改数量/勾选（qty<=0 即删除） | 是 |
| POST | /cart/remove | 删除行 | 是 |
| GET | /orders | 订单列表（status=PAID_UNSHIPPED 为“未发货”tab 分组） | 是 |
| POST | /orders/create | 支付成功后建单（扣库存/加销量/清购物车） | 是 |
| GET | /orders/:id | 订单详情 | 是 |
| POST | /orders/:id/ship | 模拟发货（Demo） | 是 |
| POST | /orders/:id/refund | 申请退款 | 是 |
| POST | /orders/:id/refund/revoke | 撤回退款申请 | 是 |
| POST | /orders/:id/cancel | 商家同意退款/取消（回补库存，未来由管理端调用） | 是 |
| GET | /user/balance | 余额/积分/券 | 是 |
| POST | /user/profile | 更新头像昵称 | 是 |
| GET | /user/recharge-tiers | 充值档位 | 是 |
| POST | /user/recharge | 充值入账（赠送额以服务端档位为准） | 是 |
| GET | /user/favorites | 收藏列表 | 是 |
| POST | /user/favorites/toggle | 收藏/取消收藏 | 是 |
| GET | /contact/info | 联系方式（占位） | - |

## 目录结构

```
pet-back/
  wsgi.py               gunicorn/flask 入口
  Makefile              setup / dev / serve / seed / reset
  app/
    __init__.py         create_app 应用工厂
    core/               config / response(统一响应+错误处理) / security(Bearer Token) / constants(订单状态机)
    models/             user(+ApiToken) / catalog(Category,Product,Banner) / order(+OrderItem) / cart(+Favorite) / recharge
    api/v1/
      client/           小程序端接口（auth/home/catalog/cart/order/user/contact）
      admin/            管理端预留命名空间（本期占位）
    services/           wechat(code2Session) / order_service(订单状态机) / serializers(字段对齐 Mock)
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
