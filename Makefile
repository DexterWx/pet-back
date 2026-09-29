# pet-back 常用命令（本地开发，SQLite 单文件库）
export FLASK_APP := wsgi.py

.PHONY: setup dev serve seed reset lan-url

## 安装依赖（uv 在 pet-back/.venv 内建虚拟环境，不污染系统）
setup:
	uv sync

## 调试启动（Flask 自带服务器，带 reload）
## 绑 0.0.0.0 而非 127.0.0.1：否则小程序真机（局域网另一台设备）连不上，
## 表现为开发者工具正常但真机“加载失败，请重试”。仅限开发机使用，同网段设备可访问。
dev:
	uv run flask run --debug --host 0.0.0.0 --port 8000

## gunicorn 启动（SQLite 本地调试固定单 worker，避免多进程写锁竞争；--access-logfile - 打印访问日志）
## 监听 0.0.0.0 以支持手机真机联调；只在本机调试可用 -b 127.0.0.1:8000 收紧
serve:
	uv run gunicorn -w 1 -b 0.0.0.0:8000 --access-logfile - wsgi:app

## 打印当前局域网访问地址（小程序真机联调用；配合 pet-mini/scripts/set-dev-host.sh 自动回写 baseURL）
lan-url:
	@IP=$$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null); \
	if [ -z "$$IP" ]; then echo "未探测到局域网 IP（检查是否连了 WiFi）"; exit 1; fi; \
	echo "本机局域网地址: http://$$IP:8000"; \
	echo "小程序自检地址: http://$$IP:8000/api/v1/client/categories"; \
	echo "回写 baseURL:  sh ../pet-mini/scripts/set-dev-host.sh"

## 灌种子数据（幂等：已存在则跳过）
seed:
	uv run flask db seed

## 删表重建 + 灌种子
reset:
	uv run flask db reset
