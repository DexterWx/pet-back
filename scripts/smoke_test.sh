#!/bin/zsh
# pet-back 冒烟测试：覆盖 pet-mini mock/server.js 全部接口链路
BASE="http://127.0.0.1:8000/api/v1/client"
PASS=0; FAIL=0

# check <描述> <期望片段> <实际输出>
check() {
  if echo "$3" | grep -q "$2"; then
    PASS=$((PASS+1)); echo "  ✓ $1"
  else
    FAIL=$((FAIL+1)); echo "  ✗ $1 | 期望含 [$2] 实际: $3"
  fi
}

echo "== 公共接口 =="
R=$(curl -s "$BASE/categories"); check "GET /categories" '"code":0' "$R"; check "分类数量=11" '"id":"c_notice"' "$R"
R=$(curl -s "$BASE/products/recommend"); check "GET /products/recommend" '"id":"p001"' "$R"
R=$(curl -s "$BASE/products/p001"); check "GET /products/p001" '"categoryName":"奖励零食"' "$R"
R=$(curl -s "$BASE/products/p999"); check "商品不存在 404" '"code":404' "$R"
R=$(curl -s "$BASE/products?categoryId=c_dried&sort=price&order=asc&page=1&pageSize=5")
check "GET /products 筛选排序" '"id":"p008"' "$R"; check "分页字段" '"hasMore"' "$R"
R=$(curl -s "$BASE/products?keyword=鸡肉"); check "keyword 搜索" '"total"' "$R"
R=$(curl -s "$BASE/home/banner"); check "GET /home/banner" '"id":"b1"' "$R"
R=$(curl -s "$BASE/home/entries"); check "GET /home/entries" '"key":"buy"' "$R"
R=$(curl -s "$BASE/contact/info"); check "GET /contact/info" '"phone"' "$R"

echo "== 认证 =="
R=$(curl -s "$BASE/cart"); check "无 token 访问 /cart -> 401" '"code":401' "$R"
R=$(curl -s -X POST "$BASE/auth/wechat-login" -H 'Content-Type: application/json' -d '{"code":"test_code_1"}')
check "POST /auth/wechat-login" '"code":0' "$R"
TOKEN=$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
NEW1=$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["isNewUser"])')
AUTH="Authorization: Bearer $TOKEN"
R=$(curl -s -X POST "$BASE/auth/wechat-login" -H 'Content-Type: application/json' -d '{"code":"test_code_2"}')
TOKEN2=$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
NEW2=$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["isNewUser"])')
check "首次登录 isNewUser=True" 'True' "$NEW1"
check "二次登录 isNewUser=False(同一 openid)" 'False' "$NEW2"
R=$(curl -s "$BASE/auth/profile" -H "Authorization: Bearer $TOKEN"); check "旧 token 轮换后失效 -> 401" '"code":401' "$R"
TOKEN=$TOKEN2; AUTH="Authorization: Bearer $TOKEN"
R=$(curl -s "$BASE/auth/profile" -H "$AUTH"); check "GET /auth/profile" '"nickname"' "$R"

echo "== 购物车 =="
R=$(curl -s -X POST "$BASE/cart/add" -H "$AUTH" -H 'Content-Type: application/json' -d '{"productId":"p009","qty":2}')
check "POST /cart/add" '"productId":"p009"' "$R"; check "加购后 checked=true" '"checked":true' "$R"
curl -s -X POST "$BASE/cart/add" -H "$AUTH" -H 'Content-Type: application/json' -d '{"productId":"p010","qty":1}' > /dev/null
R=$(curl -s -X POST "$BASE/cart/add" -H "$AUTH" -H 'Content-Type: application/json' -d '{"productId":"p014","qty":999}'); check "超库存加购 -> 400 库存不足" '库存不足' "$R"
R=$(curl -s -X POST "$BASE/cart/update" -H "$AUTH" -H 'Content-Type: application/json' -d '{"productId":"p009","qty":3}')
check "POST /cart/update qty" '"qty":3' "$R"
R=$(curl -s -X POST "$BASE/cart/update" -H "$AUTH" -H 'Content-Type: application/json' -d '{"productId":"p009","checked":false}')
check "POST /cart/update checked" '"checked":false' "$R"
R=$(curl -s -X POST "$BASE/cart/update" -H "$AUTH" -H 'Content-Type: application/json' -d '{"productId":"p010","qty":0}')
check "qty<=0 即删除行" '"code":0' "$R"
if echo "$R" | grep -q '"productId":"p010"'; then FAIL=$((FAIL+1)); echo "  ✗ p010 应已被删除"; else PASS=$((PASS+1)); echo "  ✓ p010 已删除"; fi
R=$(curl -s "$BASE/cart" -H "$AUTH"); check "GET /cart 实时 join 商品" '"priceFen":3990' "$R"

echo "== 订单链路 =="
STOCK0=$(curl -s "$BASE/products/p009" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["stock"])')
R=$(curl -s -X POST "$BASE/orders/create" -H "$AUTH" -H 'Content-Type: application/json' -d '{"items":[{"productId":"p009","qty":2}]}')
check "POST /orders/create" '"status":"PAID_UNSHIPPED"' "$R"
check "订单含 orderNo" '"orderNo":"NO' "$R"
OID=$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["id"])')
TOTAL=$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["totalFen"])')
check "totalFen=3990*2" '7980' "$TOTAL"
STOCK1=$(curl -s "$BASE/products/p009" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["stock"])')
check "下单扣库存 -2" "$((STOCK0-2))" "$STOCK1"
R=$(curl -s "$BASE/cart" -H "$AUTH")
if echo "$R" | grep -q '"productId":"p009"'; then FAIL=$((FAIL+1)); echo "  ✗ 下单后购物车应清空 p009"; else PASS=$((PASS+1)); echo "  ✓ 下单后购物车清空对应商品"; fi
R=$(curl -s "$BASE/orders/$OID" -H "$AUTH"); check "GET /orders/:id" "\"id\":\"$OID\"" "$R"
R=$(curl -s "$BASE/orders?status=PAID_UNSHIPPED" -H "$AUTH"); check "GET /orders 未发货 tab" '"status":"PAID_UNSHIPPED"' "$R"
R=$(curl -s -X POST "$BASE/orders/$OID/refund" -H "$AUTH"); check "申请退款 -> REFUND_REQUESTED" '"status":"REFUND_REQUESTED"' "$R"
R=$(curl -s -X POST "$BASE/orders/$OID/refund" -H "$AUTH"); check "重复申请退款 -> 400" '"code":400' "$R"
R=$(curl -s "$BASE/orders?status=PAID_UNSHIPPED" -H "$AUTH"); check "退款申请中仍在未发货 tab" '"status":"REFUND_REQUESTED"' "$R"
R=$(curl -s -X POST "$BASE/orders/$OID/refund/revoke" -H "$AUTH"); check "撤回退款 -> PAID_UNSHIPPED" '"status":"PAID_UNSHIPPED"' "$R"
R=$(curl -s -X POST "$BASE/orders/$OID/cancel" -H "$AUTH"); check "取消 -> CANCELLED" '"status":"CANCELLED"' "$R"
STOCK2=$(curl -s "$BASE/products/p009" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["stock"])')
check "取消回补库存" "$STOCK0" "$STOCK2"
R=$(curl -s -X POST "$BASE/orders/$OID/cancel" -H "$AUTH"); check "CANCELLED 再取消 -> 400" '"code":400' "$R"
R=$(curl -s "$BASE/orders?status=SHIPPED" -H "$AUTH"); check "已发货 tab 不含取消单" '"code":0' "$R"
if echo "$R" | grep -q "$OID"; then FAIL=$((FAIL+1)); echo "  ✗ SHIPPED tab 不应含该单"; else PASS=$((PASS+1)); echo "  ✓ SHIPPED tab 不含该单"; fi
# 第二单：发货流程
R=$(curl -s -X POST "$BASE/orders/create" -H "$AUTH" -H 'Content-Type: application/json' -d '{"items":[{"productId":"p010","qty":1}]}')
OID2=$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["id"])')
R=$(curl -s -X POST "$BASE/orders/$OID2/ship" -H "$AUTH"); check "模拟发货 -> SHIPPED" '"status":"SHIPPED"' "$R"
R=$(curl -s -X POST "$BASE/orders/$OID2/refund" -H "$AUTH"); check "已发货不可申请退款 -> 400" '"code":400' "$R"
R=$(curl -s -X POST "$BASE/orders/$OID2/cancel" -H "$AUTH"); check "已发货不可取消 -> 400" '"code":400' "$R"
R=$(curl -s -X POST "$BASE/orders/create" -H "$AUTH" -H 'Content-Type: application/json' -d '{"items":[]}'); check "空订单 -> 400" '"code":400' "$R"

echo "== 用户 =="
R=$(curl -s -X POST "$BASE/user/profile" -H "$AUTH" -H 'Content-Type: application/json' -d '{"nickname":" 旺财 ","avatar":"https://example.com/a.png"}')
check "更新资料(nickname trim)" '"nickname":"旺财"' "$R"
R=$(curl -s -X POST "$BASE/user/profile" -H "$AUTH" -H 'Content-Type: application/json' -d '{"nickname":"   "}'); check "空昵称 -> 400" '"code":400' "$R"
R=$(curl -s "$BASE/user/balance" -H "$AUTH"); check "GET /user/balance" '"balanceFen"' "$R"
R=$(curl -s "$BASE/user/recharge-tiers" -H "$AUTH"); check "GET /user/recharge-tiers" '"thresholdFen":50000' "$R"
R=$(curl -s -X POST "$BASE/user/recharge" -H "$AUTH" -H 'Content-Type: application/json' -d '{"amountFen":50000,"giftFen":3000}')
check "充值 500 元(服务端赠送 30 元)" '"balanceFen":53000' "$R"
R=$(curl -s -X POST "$BASE/user/recharge" -H "$AUTH" -H 'Content-Type: application/json' -d '{"amountFen":0}'); check "充值 0 -> 400" '"code":400' "$R"
R=$(curl -s -X POST "$BASE/user/favorites/toggle" -H "$AUTH" -H 'Content-Type: application/json' -d '{"productId":"p001"}')
check "收藏 toggle -> favorited=true" '"favorited":true' "$R"
R=$(curl -s "$BASE/user/favorites" -H "$AUTH"); check "GET /user/favorites" '"id":"p001"' "$R"
R=$(curl -s -X POST "$BASE/user/favorites/toggle" -H "$AUTH" -H 'Content-Type: application/json' -d '{"productId":"p001"}')
check "再 toggle -> favorited=false" '"favorited":false' "$R"
R=$(curl -s -X POST "$BASE/user/favorites/toggle" -H "$AUTH" -H 'Content-Type: application/json' -d '{"productId":"p999"}'); check "收藏不存在商品 -> 404" '"code":404' "$R"

echo "== 其他 =="
R=$(curl -s "$BASE/not-exist"); check "未知路径 -> 404 统一结构" '"code":404' "$R"

echo ""
echo "结果: 通过 $PASS, 失败 $FAIL"
[ $FAIL -eq 0 ] && exit 0 || exit 1
