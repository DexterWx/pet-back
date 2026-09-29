#!/bin/zsh
# pet-back 冒烟测试（阶段F：管理端 CRUD + 客户端联动 + 订单/售后全链路）
# 自举测试数据：管理端建分类/商品 -> 跑客户端下单支付售后 -> 测上下架/删除/账号管理。
# 说明：分类/商品不再灌种子（改由管理端创建），故本脚本自建自清理，可重复运行。
# 前置：以 Mock 登录 + mock 支付启动服务：
#   WECHAT_MOCK_LOGIN=true PAYMENT_PROVIDER=mock uv run gunicorn -w 1 -b 127.0.0.1:8000 --access-logfile - wsgi:app
# 可选：SMOKE_HOST 覆盖目标地址（默认 127.0.0.1:8000），便于对隔离端口的临时库跑测试。
HOST="${SMOKE_HOST:-127.0.0.1:8000}"
CLIENT="http://$HOST/api/v1/client"
ADMIN="http://$HOST/api/v1/admin"
PASS=0; FAIL=0

check() {
  if echo "$3" | grep -q "$2"; then PASS=$((PASS+1)); echo "  ✓ $1"
  else FAIL=$((FAIL+1)); echo "  ✗ $1 | 期望含 [$2] 实际: $3"; fi
}
checkne() {  # 断言不包含
  if echo "$3" | grep -q "$2"; then FAIL=$((FAIL+1)); echo "  ✗ $1 | 不应含 [$2]"
  else PASS=$((PASS+1)); echo "  ✓ $1"; fi
}
jf() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }

echo "== 管理端登录 + 自举目录 =="
R=$(curl -s "$ADMIN/orders"); check "管理端未登录 -> 401" '"code":401' "$R"
R=$(curl -s -X POST "$ADMIN/auth/login" -H 'Content-Type: application/json' -d '{"username":"admin","password":"bad"}')
check "错误密码 -> 400" '"code":400' "$R"
R=$(curl -s -X POST "$ADMIN/auth/login" -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}')
check "管理员登录" '"code":0' "$R"
ATK=$(echo "$R" | jf 'd["data"]["token"]')
AAUTH="Authorization: Bearer $ATK"
R=$(curl -s "$ADMIN/auth/me" -H "$AAUTH"); check "GET /auth/me 含 isSuper" '"isSuper":true' "$R"
SELFID=$(echo "$R" | jf 'd["data"]["id"]')

R=$(curl -s -X POST "$ADMIN/categories" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"name":"冒烟测试分类","sort":1}')
check "创建分类" '"name":"冒烟测试分类"' "$R"
CID=$(echo "$R" | jf 'd["data"]["id"]')
R=$(curl -s -X POST "$ADMIN/products" -H "$AAUTH" -H 'Content-Type: application/json' \
  -d "{\"title\":\"冒烟测试商品A\",\"categoryId\":\"$CID\",\"priceFen\":3990,\"images\":[],\"desc\":\"冒烟用\",\"sort\":1,\"onSale\":true}")
check "创建商品" '"title":"冒烟测试商品A"' "$R"
PID=$(echo "$R" | jf 'd["data"]["id"]')
R=$(curl -s "$ADMIN/products?keyword=冒烟测试商品A" -H "$AAUTH"); check "管理端商品列表命中" "$PID" "$R"
R=$(curl -s "$ADMIN/categories" -H "$AAUTH"); check "分类列表含商品数" '"productCount":1' "$R"
R=$(curl -s -X POST "$ADMIN/products" -H "$AAUTH" -H 'Content-Type: application/json' -d "{\"title\":\"无分类\",\"categoryId\":\"c_none\",\"priceFen\":100}")
check "创建商品-分类不存在 -> 400" '"code":400' "$R"
R=$(curl -s -X DELETE "$ADMIN/categories/$CID" -H "$AAUTH")
check "删除有商品的分类 -> 400" '"code":400' "$R"

echo "== 客户端目录联动（上架可见）=="
R=$(curl -s "$CLIENT/categories"); check "客户端分类含新建" "$CID" "$R"
R=$(curl -s "$CLIENT/products/$PID"); check "客户端商品详情" '"categoryName":"冒烟测试分类"' "$R"
if echo "$R" | grep -q '"stock"'; then FAIL=$((FAIL+1)); echo "  ✗ 商品不应有 stock"; else PASS=$((PASS+1)); echo "  ✓ 商品无 stock"; fi
R=$(curl -s "$CLIENT/products/p999"); check "商品不存在 404" '"code":404' "$R"
R=$(curl -s "$CLIENT/products?keyword=冒烟测试商品A"); check "keyword 搜索命中" "$PID" "$R"

echo "== 上下架联动 =="
R=$(curl -s -X PATCH "$ADMIN/products/$PID/on-sale" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"onSale":false}')
check "下架 -> onSale false" '"onSale":false' "$R"
R=$(curl -s "$CLIENT/products/$PID"); check "下架后客户端详情 404" '"code":404' "$R"
R=$(curl -s "$CLIENT/products?keyword=冒烟测试商品A"); checkne "下架后客户端列表不含" "$PID" "$R"
R=$(curl -s "$ADMIN/products?onSale=false" -H "$AAUTH"); check "管理端可按下架筛选" "$PID" "$R"
R=$(curl -s -X PATCH "$ADMIN/products/$PID/on-sale" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"onSale":true}')
check "重新上架 -> onSale true" '"onSale":true' "$R"
R=$(curl -s "$CLIENT/products/$PID"); check "上架后客户端详情恢复" '"code":0' "$R"

echo "== 客户端认证/地址/购物车 =="
R=$(curl -s "$CLIENT/cart"); check "无 token /cart -> 401" '"code":401' "$R"
R=$(curl -s -X POST "$CLIENT/auth/wechat-login" -H 'Content-Type: application/json' -d '{"code":"test_code_1"}')
check "POST /auth/wechat-login" '"code":0' "$R"
TOKEN=$(echo "$R" | jf 'd["data"]["token"]')
AUTH="Authorization: Bearer $TOKEN"
R=$(curl -s "$CLIENT/auth/profile" -H "$AUTH"); check "GET /auth/profile" '"nickname"' "$R"
R=$(curl -s -X POST "$CLIENT/addresses/add" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"receiverName":"张三","phone":"13800000000","province":"广东省","city":"深圳市","district":"南山区","detail":"科技园1号"}')
check "新增地址(首个默认)" '"isDefault":true' "$R"
ADDR=$(echo "$R" | jf 'd["data"][0]["id"]')
R=$(curl -s -X POST "$CLIENT/cart/add" -H "$AUTH" -H 'Content-Type: application/json' -d "{\"productId\":\"$PID\",\"qty\":2}")
check "POST /cart/add" "\"productId\":\"$PID\"" "$R"
R=$(curl -s -X POST "$CLIENT/cart/add" -H "$AUTH" -H 'Content-Type: application/json' -d "{\"productId\":\"$PID\",\"qty\":999}")
check "超单笔上限 400" '"code":400' "$R"
R=$(curl -s "$CLIENT/cart" -H "$AUTH"); check "GET /cart join 价格" '"priceFen":3990' "$R"

echo "== 下单 -> 待付款 -> 取消 =="
R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":2}]}")
check "缺地址 -> 400" '"code":400' "$R"
SOLD0=$(curl -s "$CLIENT/products/$PID" | jf 'd["data"]["sold"]')
R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":2}],\"deliveryType\":\"EXPRESS\",\"addressId\":\"$ADDR\"}")
check "POST /orders/create -> PENDING_PAY" '"status":"PENDING_PAY"' "$R"
check "含收货人" '"receiverName":"张三"' "$R"
OID=$(echo "$R" | jf 'd["data"]["id"]')
check "待付款不增销量" "$SOLD0" "$(curl -s "$CLIENT/products/$PID" | jf 'd["data"]["sold"]')"
R=$(curl -s "$CLIENT/orders?status=PENDING_PAY" -H "$AUTH"); check "未付款 tab 命中" "$OID" "$R"
checkne "下单清空购物车对应商品" "\"productId\":\"$PID\"" "$(curl -s "$CLIENT/cart" -H "$AUTH")"
R=$(curl -s -X POST "$CLIENT/orders/$OID/cancel" -H "$AUTH"); check "取消 -> CLOSED" '"status":"CLOSED"' "$R"
R=$(curl -s -X POST "$CLIENT/orders/$OID/cancel" -H "$AUTH"); check "重复取消 -> 400" '"code":400' "$R"
R=$(curl -s -X POST "$CLIENT/orders/$OID/refund" -H "$AUTH" -H 'Content-Type: application/json' -d '{}')
check "CLOSED 申请退款 -> 400" '"code":400' "$R"

echo "== 支付与售后完整链路（mock provider）=="
R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":1}],\"deliveryType\":\"EXPRESS\",\"addressId\":\"$ADDR\"}")
OID2=$(echo "$R" | jf 'd["data"]["id"]')
check "下单得到待付款" '"status":"PENDING_PAY"' "$R"
R=$(curl -s -X POST "$CLIENT/orders/$OID2/pay" -H "$AUTH" -H 'Content-Type: application/json' -d '{}')
check "发起支付 -> 已付款(mock即时)" '"status":"PAID_UNSHIPPED"' "$R"
check "支付转已付后销量+1" "$((SOLD0+1))" "$(curl -s "$CLIENT/products/$PID" | jf 'd["data"]["sold"]')"
R=$(curl -s -X POST "$ADMIN/orders/$OID2/ship" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"carrier":"顺丰","shipNo":"SF88"}')
check "管理端发货 -> SHIPPED" '"status":"SHIPPED"' "$R"
R=$(curl -s -X POST "$CLIENT/orders/$OID2/refund" -H "$AUTH" -H 'Content-Type: application/json' -d '{"reason":"质量问题"}')
check "已发货用户申请退款 -> 售后 PENDING" '"status":"PENDING"' "$R"
ASID=$(echo "$R" | jf 'd["data"]["afterSale"]["id"]')
R=$(curl -s "$ADMIN/after-sales" -H "$AAUTH"); check "待处理售后列表命中" "$ASID" "$R"
R=$(curl -s "$ADMIN/orders?keyword=张三" -H "$AAUTH"); check "管理端订单搜索" "$OID2" "$R"
R=$(curl -s -X POST "$ADMIN/after-sales/$ASID/approve" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"note":"同意"}')
check "管理员同意 -> REFUNDED + 退款单号" "mockrefund_" "$R"
R=$(curl -s "$CLIENT/orders/$OID2" -H "$AUTH"); check "全额退后订单 REFUNDED" '"status":"REFUNDED"' "$R"
check "退款回退销量" "$SOLD0" "$(curl -s "$CLIENT/products/$PID" | jf 'd["data"]["sold"]')"

echo "== 订单页直接退款应合并关闭用户 PENDING 售后单（防残留/防二次退款）=="
R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":1}],\"deliveryType\":\"EXPRESS\",\"addressId\":\"$ADDR\"}")
OID3=$(echo "$R" | jf 'd["data"]["id"]')
TOTAL3=$(echo "$R" | jf 'd["data"]["totalFen"]')
curl -s -X POST "$CLIENT/orders/$OID3/pay" -H "$AUTH" -H 'Content-Type: application/json' -d '{}' >/dev/null
R=$(curl -s -X POST "$CLIENT/orders/$OID3/refund" -H "$AUTH" -H 'Content-Type: application/json' -d '{"reason":"不想要了"}')
ASID3=$(echo "$R" | jf 'd["data"]["afterSale"]["id"]')
R=$(curl -s "$ADMIN/after-sales" -H "$AAUTH"); check "用户申请后售后列表命中" "$ASID3" "$R"
R=$(curl -s -X POST "$ADMIN/orders/$OID3/refund" -H "$AAUTH" -H 'Content-Type: application/json' -d "{\"refundFen\":$TOTAL3,\"note\":\"订单页直接退\"}")
check "订单页直接退款 -> REFUNDED" '"status":"REFUNDED"' "$R"
R=$(curl -s "$ADMIN/after-sales" -H "$AAUTH"); checkne "直接退款后 PENDING 售后已清除" "$ASID3" "$R"
R=$(curl -s -X POST "$ADMIN/after-sales/$ASID3/approve" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"note":"重复同意"}')
check "重复同意已处理售后 -> 400（防二次退款）" '"code":400' "$R"
R=$(curl -s "$CLIENT/orders/$OID3" -H "$AUTH"); check "订单最终 REFUNDED" '"status":"REFUNDED"' "$R"

echo "== 管理端用户查询 =="
R=$(curl -s "$ADMIN/users?keyword=13800000000" -H "$AAUTH"); check "用户搜索(手机号)" '"phone":"13800000000"' "$R"
USERID=$(echo "$R" | jf 'd["data"]["list"][0]["id"]')
R=$(curl -s "$ADMIN/users/$USERID" -H "$AAUTH"); check "用户详情含订单数" '"orderCount"' "$R"
# 后台调整余额（测试用，仅超管）；用相对基线保证可重复跑
B0=$(curl -s "$ADMIN/users/$USERID" -H "$AAUTH" | jf 'd["data"]["balanceFen"]')
R=$(curl -s -X POST "$ADMIN/users/$USERID/balance-adjust" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"amountFen":50000,"note":"冒烟测试发放"}')
check "超管调整余额成功" '"code":0' "$R"
check "余额已增加" "$((B0 + 50000))" "$(curl -s "$ADMIN/users/$USERID" -H "$AAUTH" | jf 'd["data"]["balanceFen"]')"
R=$(curl -s -X POST "$ADMIN/users/$USERID/balance-adjust" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"amountFen":0}')
check "调整金额为 0 -> 400" '"code":400' "$R"
R=$(curl -s -X POST "$ADMIN/users/$USERID/balance-adjust" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"amountFen":-99999999}')
check "扣成负数 -> 400" '"code":400' "$R"
R=$(curl -s -X POST "$ADMIN/users/u_nope/balance-adjust" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"amountFen":100}')
check "用户不存在 -> 404" '"code":404' "$R"
R=$(curl -s "$CLIENT/user/recharge-records" -H "$AUTH")
checkne "用户充值记录不暴露后台调整" '"provider":"admin"' "$R"

echo "== 用户资料/余额/收藏 =="
R=$(curl -s -X POST "$CLIENT/user/profile" -H "$AUTH" -H 'Content-Type: application/json' -d '{"nickname":" 旺财 "}')
check "更新昵称 trim" '"nickname":"旺财"' "$R"
R=$(curl -s "$CLIENT/user/balance" -H "$AUTH"); check "GET /user/balance" '"balanceFen"' "$R"
R=$(curl -s -X POST "$CLIENT/user/favorites/toggle" -H "$AUTH" -H 'Content-Type: application/json' -d "{\"productId\":\"$PID\"}")
check "收藏 toggle" '"favorited":true' "$R"

echo "== 管理端多账号 + 改密 + 越权保护 =="
R=$(curl -s "$ADMIN/admins" -H "$AAUTH"); check "管理员列表含 admin" '"username":"admin"' "$R"
R=$(curl -s -X POST "$ADMIN/admins" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"username":"pwtest","password":"pw123456","displayName":"改密测试"}')
check "创建管理员" '"username":"pwtest"' "$R"
PWID=$(echo "$R" | jf 'd["data"]["id"]')
R=$(curl -s -X POST "$ADMIN/auth/login" -H 'Content-Type: application/json' -d '{"username":"pwtest","password":"pw123456"}')
check "新管理员登录" '"code":0' "$R"
PTK=$(echo "$R" | jf 'd["data"]["token"]')
PAUTH="Authorization: Bearer $PTK"
R=$(curl -s "$ADMIN/admins" -H "$PAUTH"); check "普通管理员可看列表" '"code":0' "$R"
R=$(curl -s -X POST "$ADMIN/admins" -H "$PAUTH" -H 'Content-Type: application/json' -d '{"username":"x","password":"x123456"}')
check "普通管理员建号 -> 403" '"code":403' "$R"
R=$(curl -s -X POST "$ADMIN/users/$USERID/balance-adjust" -H "$PAUTH" -H 'Content-Type: application/json' -d '{"amountFen":100}')
check "普通管理员调余额 -> 403" '"code":403' "$R"
R=$(curl -s -X POST "$ADMIN/auth/change-password" -H "$PAUTH" -H 'Content-Type: application/json' -d '{"oldPassword":"wrong","newPassword":"pw654321"}')
check "改密-原密码错误 -> 400" '"code":400' "$R"
R=$(curl -s -X POST "$ADMIN/auth/change-password" -H "$PAUTH" -H 'Content-Type: application/json' -d '{"oldPassword":"pw123456","newPassword":"pw654321"}')
check "改密成功" '"code":0' "$R"
R=$(curl -s "$ADMIN/auth/me" -H "$PAUTH"); check "改密后旧 token 失效 -> 401" '"code":401' "$R"
R=$(curl -s -X POST "$ADMIN/auth/login" -H 'Content-Type: application/json' -d '{"username":"pwtest","password":"pw654321"}')
check "新密码登录" '"code":0' "$R"
R=$(curl -s -X POST "$ADMIN/auth/login" -H 'Content-Type: application/json' -d '{"username":"pwtest","password":"pw123456"}')
check "旧密码登录失败 -> 400" '"code":400' "$R"
R=$(curl -s -X PUT "$ADMIN/admins/$SELFID" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"isActive":false}')
check "不能禁用自己 -> 400" '"code":400' "$R"
R=$(curl -s -X DELETE "$ADMIN/admins/$SELFID" -H "$AAUTH")
check "不能删除自己 -> 400" '"code":400' "$R"
R=$(curl -s -X DELETE "$ADMIN/admins/$PWID" -H "$AAUTH"); check "删除管理员" '"code":0' "$R"

echo "== 充值与余额支付（批次③）=="
R=$(curl -s "$CLIENT/user/recharge-tiers" -H "$AUTH"); check "档位列表含默认档" '"thresholdFen":100000' "$R"
TIER0=$(echo "$R" | jf 'd["data"][0]["id"]')
BAL0=$(curl -s "$CLIENT/user/balance" -H "$AUTH" | jf 'd["data"]["balanceFen"]')
R=$(curl -s -X POST "$CLIENT/user/recharge/prepay" -H "$AUTH" -H 'Content-Type: application/json' -d "{\"tierId\":$TIER0}")
check "充值预下单(mock 即时到账)" '"settled":true' "$R"
check "充值单号带 RC 前缀" '"paymentNo":"RC' "$R"
RCNO=$(echo "$R" | jf 'd["data"]["paymentNo"]')
check "返回 payParams 与金额" '"amountFen":100000' "$R"
BALA=$(curl -s "$CLIENT/user/balance" -H "$AUTH" | jf 'd["data"]["balanceFen"]')
# 用相对基线断言，保证脚本可重复跑（余额会累积）
check "充值已含赠送入账" "$((BAL0 + 100000 + 10000))" "$BALA"
R=$(curl -s -X POST "$CLIENT/user/recharge" -H "$AUTH" -H 'Content-Type: application/json' -d '{"amountFen":5000}')
check "旧的直接入账接口已下线 -> 404" '"code":404' "$R"
R=$(curl -s "$CLIENT/user/recharge/record?paymentNo=$RCNO" -H "$AUTH"); check "充值单可查已到账" '"status":"SUCCESS"' "$R"
R=$(curl -s "$CLIENT/user/recharge-records" -H "$AUTH"); check "充值记录列表" '"total"' "$R"
R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":1}],\"deliveryType\":\"EXPRESS\",\"addressId\":\"$ADDR\"}")
OIDB=$(echo "$R" | jf 'd["data"]["id"]'); TOTALB=$(echo "$R" | jf 'd["data"]["totalFen"]')
R=$(curl -s -X POST "$CLIENT/orders/$OIDB/pay" -H "$AUTH" -H 'Content-Type: application/json' -d '{"method":"balance"}')
check "余额支付直接已付" '"status":"PAID_UNSHIPPED"' "$R"
check "余额已正确扣减" "$((BALA - TOTALB))" "$(curl -s "$CLIENT/user/balance" -H "$AUTH" | jf 'd["data"]["balanceFen"]')"
# 不混用：余额不足必须整单拒结。可构造的最大单笔为 99 件，仅当它超过当前余额时才断言，
# 否则（多次重跑余额已积高）计为跳过，避免假失败与连带干扰后面的取消断言。
PRICE=$(curl -s "$CLIENT/products/$PID" | jf 'd["data"]["priceFen"]')
if [ $(( 99 * PRICE )) -gt $BALA ]; then
  QTY_X=$(( BALA / PRICE + 1 ))
  R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":$QTY_X}],\"deliveryType\":\"EXPRESS\",\"addressId\":\"$ADDR\"}")
  OIDC=$(echo "$R" | jf 'd["data"]["id"]')
  R=$(curl -s -X POST "$CLIENT/orders/$OIDC/pay" -H "$AUTH" -H 'Content-Type: application/json' -d '{"method":"balance"}')
  check "余额不足拒结(不混用) -> 400" '"code":400' "$R"
  R=$(curl -s -X POST "$CLIENT/orders/$OIDC/cancel" -H "$AUTH"); check "未付单可取消" '"status":"CLOSED"' "$R"
else
  PASS=$((PASS+1)); echo "  ✓ 余额不足用例跳过（当前余额已超出单笔上限，请用全新库跑以覆盖）"
fi
# 参数校验与余额无关，恒定执行
R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":1}],\"deliveryType\":\"EXPRESS\",\"addressId\":\"$ADDR\"}")
OIDM=$(echo "$R" | jf 'd["data"]["id"]')
R=$(curl -s -X POST "$CLIENT/orders/$OIDM/pay" -H "$AUTH" -H 'Content-Type: application/json' -d '{"method":"alipay"}')
check "非法支付方式 -> 400" '"code":400' "$R"
R=$(curl -s -X POST "$CLIENT/orders/$OIDM/cancel" -H "$AUTH"); check "待付款单可取消" '"status":"CLOSED"' "$R"
R=$(curl -s "$ADMIN/recharge-tiers" -H "$AAUTH"); check "后台档位列表" "\"id\":$TIER0" "$R"
R=$(curl -s -X DELETE "$ADMIN/recharge-tiers/$TIER0" -H "$AAUTH")
check "删到空被拒 -> 400" '"code":400' "$R"
R=$(curl -s -X POST "$ADMIN/recharge-tiers" -H "$AAUTH" -H 'Content-Type: application/json' \
  -d '{"thresholdFen":20000,"giftFen":2000,"label":"充200元","sub":"送20元","sort":2}')
check "新增档位" '"id"' "$R"
TIER2=$(echo "$R" | jf 'd["data"]["id"]')
R=$(curl -s -X PUT "$ADMIN/recharge-tiers/$TIER2" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"giftFen":3000}')
check "更新档位赠送额" '"giftFen":3000' "$R"
R=$(curl -s -X POST "$ADMIN/recharge-tiers" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"thresholdFen":0}')
check "门槛为 0 -> 400" '"code":400' "$R"
R=$(curl -s -X DELETE "$ADMIN/recharge-tiers/$TIER2" -H "$AAUTH"); check "非最后一个档位可删" '"code":0' "$R"

echo "== 运费规则（批次④）=="
R=$(curl -s "$CLIENT/shipping/config"); check "客户端可读运费规则" '"baseFreightFen"' "$R"
R=$(curl -s -X PUT "$ADMIN/shipping-config" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"baseFreightFen":-1}')
check "基础运费为负 -> 400" '"code":400' "$R"
R=$(curl -s -X PUT "$ADMIN/shipping-config" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"baseFreightFen":800,"freeThresholdFen":9900}')
check "配置运费生效" '"baseFreightFen":800' "$R"
# 快递且商品金额 3990 < 门槛 9900 -> 运费 800，总额 4790
R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":1}],\"deliveryType\":\"EXPRESS\",\"addressId\":\"$ADDR\"}")
check "未达门槛拆分商品金额" '"goodsTotalFen":3990' "$R"
check "运费计入总额" '"totalFen":4790' "$R"
OIDF=$(echo "$R" | jf 'd["data"]["id"]')
R=$(curl -s "$CLIENT/orders/$OIDF" -H "$AUTH"); check "订单详情含运费快照" '"freightFen":800' "$R"
# 自提一律免运费
R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":1}],\"deliveryType\":\"SELF_PICKUP\",\"addressId\":\"$ADDR\"}")
check "自提免运费" '"freightFen":0' "$R"
# 商品金额 3x3990=11970 >= 9900 -> 免运费
R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":3}],\"deliveryType\":\"EXPRESS\",\"addressId\":\"$ADDR\"}")
check "达包邮门槛免运费" '"freightFen":0' "$R"
R=$(curl -s -X PUT "$ADMIN/shipping-config" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"baseFreightFen":0,"freeThresholdFen":0}')
check "复位为全站包邮" '"baseFreightFen":0' "$R"

echo "== 确认收货与退款窗口（批次⑤）=="
# 确认收货 -> COMPLETED -> 不可自助退；但管理员可强制退（后门）
R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":1}],\"deliveryType\":\"EXPRESS\",\"addressId\":\"$ADDR\"}")
OCA=$(echo "$R" | jf 'd["data"]["id"]'); TOTALA=$(echo "$R" | jf 'd["data"]["totalFen"]')
curl -s -X POST "$CLIENT/orders/$OCA/pay" -H "$AUTH" -H 'Content-Type: application/json' -d '{}' >/dev/null
curl -s -X POST "$ADMIN/orders/$OCA/ship" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"carrier":"顺丰","shipNo":"SF9"}' >/dev/null
R=$(curl -s "$CLIENT/orders/$OCA" -H "$AUTH"); check "待收货可确认" '"canConfirm":true' "$R"
check "窗口内可自助退" '"canRefund":true' "$R"
R=$(curl -s -X POST "$CLIENT/orders/$OCA/confirm" -H "$AUTH"); check "确认收货 -> COMPLETED" '"status":"COMPLETED"' "$R"
check "已完成不可自助退" '"canRefund":false' "$R"
R=$(curl -s -X POST "$CLIENT/orders/$OCA/refund" -H "$AUTH" -H 'Content-Type: application/json' -d '{}')
check "已完成申请退款 -> 400" '"code":400' "$R"
R=$(curl -s -X POST "$ADMIN/orders/$OCA/refund" -H "$AAUTH" -H 'Content-Type: application/json' -d "{\"refundFen\":$TOTALA,\"note\":\"完成后强制退\"}")
check "管理员可对已完成强制退 -> REFUNDED" '"status":"REFUNDED"' "$R"

# 驳回锁定：申请 -> 驳回 -> 再申请被拒
R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":1}],\"deliveryType\":\"EXPRESS\",\"addressId\":\"$ADDR\"}")
OCB=$(echo "$R" | jf 'd["data"]["id"]')
curl -s -X POST "$CLIENT/orders/$OCB/pay" -H "$AUTH" -H 'Content-Type: application/json' -d '{}' >/dev/null
curl -s -X POST "$ADMIN/orders/$OCB/ship" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"carrier":"顺丰","shipNo":"SF10"}' >/dev/null
R=$(curl -s -X POST "$CLIENT/orders/$OCB/refund" -H "$AUTH" -H 'Content-Type: application/json' -d '{"reason":"x"}')
ASB=$(echo "$R" | jf 'd["data"]["afterSale"]["id"]')
R=$(curl -s -X POST "$ADMIN/after-sales/$ASB/reject" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"note":"超期"}')
check "管理员驳回 -> REJECTED" '"status":"REJECTED"' "$R"
R=$(curl -s -X POST "$CLIENT/orders/$OCB/refund" -H "$AUTH" -H 'Content-Type: application/json' -d '{}')
check "驳回后再申请 -> 400（锁定）" '"code":400' "$R"
R=$(curl -s "$CLIENT/orders/$OCB" -H "$AUTH"); check "驳回后 canRefund=false" '"canRefund":false' "$R"

# 自提发货无需单号
R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":1}],\"deliveryType\":\"SELF_PICKUP\",\"addressId\":\"$ADDR\"}")
OCC=$(echo "$R" | jf 'd["data"]["id"]')
curl -s -X POST "$CLIENT/orders/$OCC/pay" -H "$AUTH" -H 'Content-Type: application/json' -d '{}' >/dev/null
R=$(curl -s -X POST "$ADMIN/orders/$OCC/ship" -H "$AAUTH" -H 'Content-Type: application/json' -d '{}')
check "自提无单号直接发货 -> SHIPPED" '"status":"SHIPPED"' "$R"

# 交易配置（自动确认天数）
R=$(curl -s "$ADMIN/order-config" -H "$AAUTH"); check "读交易配置默认7天" '"autoCompleteDays":7' "$R"
R=$(curl -s -X PUT "$ADMIN/order-config" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"autoCompleteDays":0}')
check "天数 0 -> 400" '"code":400' "$R"
R=$(curl -s -X PUT "$ADMIN/order-config" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"autoCompleteDays":3}')
check "配置 3 天生效" '"autoCompleteDays":3' "$R"
R=$(curl -s -X PUT "$ADMIN/order-config" -H "$AAUTH" -H 'Content-Type: application/json' -d '{"autoCompleteDays":7}')
check "复位 7 天" '"autoCompleteDays":7' "$R"

# 防累计超退（HTTP）：部分退后再发起超额退应 400
R=$(curl -s -X POST "$CLIENT/orders/create" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"items\":[{\"productId\":\"$PID\",\"qty\":1}],\"deliveryType\":\"EXPRESS\",\"addressId\":\"$ADDR\"}")
OCD=$(echo "$R" | jf 'd["data"]["id"]'); TOTALD=$(echo "$R" | jf 'd["data"]["totalFen"]')
curl -s -X POST "$CLIENT/orders/$OCD/pay" -H "$AUTH" -H 'Content-Type: application/json' -d '{}' >/dev/null
R=$(curl -s -X POST "$ADMIN/orders/$OCD/refund" -H "$AAUTH" -H 'Content-Type: application/json' -d "{\"refundFen\":$((TOTALD / 2)),\"note\":\"部分退\"}")
ASD=$(echo "$R" | jf 'd["data"]["id"]'); check "部分退受理" '"refundFen"' "$R"
R=$(curl -s -X POST "$ADMIN/orders/$OCD/refund" -H "$AAUTH" -H 'Content-Type: application/json' -d "{\"refundFen\":$TOTALD}")
check "累计超退 -> 400" '"code":400' "$R"
R=$(curl -s -X POST "$ADMIN/after-sales/$ASD/sync" -H "$AAUTH"); check "同步退款状态接口可用" '"code":0' "$R"

echo "== 商品删除（清库 + 图片尽力删）=="
R=$(curl -s -X DELETE "$ADMIN/products/$PID" -H "$AAUTH"); check "删除商品" '"code":0' "$R"
R=$(curl -s "$CLIENT/products/$PID"); check "删除后客户端详情 404" '"code":404' "$R"
R=$(curl -s "$ADMIN/products/$PID" -H "$AAUTH"); check "删除后管理端详情 404" '"code":404' "$R"
R=$(curl -s -X DELETE "$ADMIN/categories/$CID" -H "$AAUTH"); check "无商品后删除分类" '"code":0' "$R"

echo "== 其他 =="
R=$(curl -s "$CLIENT/not-exist"); check "未知路径 -> 404" '"code":404' "$R"

echo ""
echo "结果: 通过 $PASS, 失败 $FAIL"
[ $FAIL -eq 0 ] && exit 0 || exit 1
