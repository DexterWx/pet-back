# pet-back 常用命令（Linux 服务器上开发/测试/线上同一台机器，SQLite 单文件库）
export FLASK_APP := wsgi.py

.PHONY: setup dev serve seed reset

## 安装依赖（uv 在 pet-back/.venv 内建虚拟环境，不污染系统）
setup:
	uv sync

## 调试启动（Flask 自带服务器，带 reload）
## 绑 0.0.0.0：手机真机（公网另一台设备）要能直连本后端。
dev:
	uv run flask run --debug --host 0.0.0.0 --port 8000

## gunicorn 启动（SQLite 固定单 worker，多进程会抢写锁；--access-logfile - 打印访问日志）
## 现阶段公网 IP 直连，故监听 0.0.0.0；Nginx 反代到位后改 -b 127.0.0.1:8000 收紧
serve:
	uv run gunicorn -w 1 -b 0.0.0.0:8000 --access-logfile - wsgi:app

## 灌种子数据（幂等：已存在则跳过）
seed:
	uv run flask db seed

## 删表重建 + 灌种子
reset:
	uv run flask db reset
