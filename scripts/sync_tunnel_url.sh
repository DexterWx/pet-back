#!/usr/bin/env bash
# 把 cpolar 隧道的当前域名同步进 .env 的支付回调地址。
#
# 背景：free 版隧道每次重启分配的域名都会变，而 WXPAY_NOTIFY_URL 写死在 .env 里，
#       变了不改就是「钱扣了回调打不进」——所以交给 cron 每 5 分钟对一次。
# 用法：bash scripts/sync_tunnel_url.sh        （无变化时什么都不做）
# 动作：改 .env 的 WXPAY_NOTIFY_URL（先备份 .env.bak）→ systemctl restart pet-back
#       退款回调地址由 config.py 从它派生，不用单独写。
set -uo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=.env

RE='https://[a-z0-9.-]*cpolar[a-z0-9.-]*'

# 取当前隧道域名：先问 cpolar 本地状态页，拿不到再从 journald 末尾找最近一次
url="$(curl -s --max-time 5 http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -oE "$RE" | head -1)"
[ -n "$url" ] || url="$(journalctl -u cpolar-tunnel -n 3000 --no-pager 2>/dev/null | grep -oE "$RE" | tail -1)"
if [ -z "$url" ]; then echo "[$(date '+%F %T')] 取不到隧道域名（cpolar 没在跑？），跳过"; exit 1; fi

old="$(grep '^WXPAY_NOTIFY_URL=' "$ENV_FILE" | cut -d= -f2- | grep -oE "$RE" | head -1)"
if [ "$old" = "$url" ]; then echo "[$(date '+%F %T')] 域名未变（$url），无需处理"; exit 0; fi

new_path="$(grep '^WXPAY_NOTIFY_URL=' "$ENV_FILE" | cut -d= -f2- | sed "s|$old|$url|")"
cp "$ENV_FILE" "$ENV_FILE.bak"
python3 - "$ENV_FILE" "$new_path" <<'PY'
import sys
path, value = sys.argv[1], sys.argv[2]
lines = open(path, encoding="utf-8").read().splitlines(keepends=True)
with open(path, "w", encoding="utf-8") as f:
    for line in lines:
        f.write(f"WXPAY_NOTIFY_URL={value}\n" if line.startswith("WXPAY_NOTIFY_URL=") else line)
PY

systemctl restart pet-back
echo "[$(date '+%F %T')] 已同步 $old -> $url，并重启 pet-back"
