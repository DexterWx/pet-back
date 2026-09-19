# pet-back 常用命令（本地开发，SQLite 单文件库）
export FLASK_APP := wsgi.py

.PHONY: setup dev serve seed reset

## 安装依赖（uv 在 pet-back/.venv 内建虚拟环境，不污染系统）
setup:
	uv sync

## 调试启动（Flask 自带服务器，带 reload）
dev:
	uv run flask run --debug --host 127.0.0.1 --port 8000

## gunicorn 启动（SQLite 本地调试固定单 worker，避免多进程写锁竞争；--access-logfile - 打印访问日志）
serve:
	uv run gunicorn -w 1 -b 127.0.0.1:8000 --access-logfile - wsgi:app

## 灌种子数据（幂等：已存在则跳过）
seed:
	uv run flask db seed

## 删表重建 + 灌种子
reset:
	uv run flask db reset
