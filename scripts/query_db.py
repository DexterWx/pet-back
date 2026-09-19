#!/usr/bin/env python3
"""查库脚本：直接从本地 SQLite 读取数据，便于核对测试账号/业务数据是否入库。

用法（在 pet-back 目录下）：
    uv run python scripts/query_db.py                       # 默认查所有用户
    uv run python scripts/query_db.py --mode user           # 同上
    uv run python scripts/query_db.py --openid oXyZ         # 按 openid 模糊过滤
    uv run python scripts/query_db.py --limit 20            # 只看最近 20 条

约定：
- 复用 app.models（SQLAlchemy），字段随 ORM 演进，无需手写 SQL 列名；
- 金额以「分」存储，展示时换算为元；时间戳为毫秒，转本地可读时间；
- 只读，不做任何写操作（create_app 内的 create_all 幂等建表，不改动已有数据）。
"""
import argparse
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

# 将项目根目录（pet-back/）加入 sys.path，使脚本在任意 cwd 下均可执行
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import create_app  # noqa: E402
from app.models import ApiToken, User  # noqa: E402


def _display_width(s: str) -> int:
    """计算字符串显示宽度：中日韩全角字符按 2 计，其余按 1 计。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1 for ch in s)


def _pad(s: str, width: int) -> str:
    """按显示宽度右侧补空格，保证含中文的列对齐。"""
    return s + " " * max(0, width - _display_width(s))


def _ts(ms: int) -> str:
    """毫秒时间戳 -> 本地可读时间；0 视为未设置。"""
    if not ms:
        return "-"
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _yuan(fen: int) -> str:
    """分 -> 元（保留两位小数）。"""
    return f"{(fen or 0) / 100:.2f}"


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    """打印按显示宽度对齐的表格。"""
    widths = [_display_width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _display_width(cell))
    line = "  ".join(_pad(h, widths[i]) for i, h in enumerate(headers))
    print(line)
    print("-" * _display_width(line))
    for row in rows:
        print("  ".join(_pad(cell, widths[i]) for i, cell in enumerate(row)))


def query_users(openid_filter: str | None, limit: int | None) -> int:
    """查询用户信息（--mode user）。"""
    app = create_app()
    with app.app_context():
        q = User.query
        if openid_filter:
            q = q.filter(User.openid.like(f"%{openid_filter}%"))
        users = q.order_by(User.created_at.desc()).all()
        total = len(users)
        if limit is not None:
            users = users[:limit]

        # 预取每个用户当前有效（未轮换失效）的 token 数，用于判断是否已登录入库
        token_counts = {
            user.id: ApiToken.query.filter_by(user_id=user.id).count() for user in users
        }

    headers = ["#", "用户ID", "openid", "昵称", "余额(元)", "积分", "券", "有效token", "注册时间"]
    rows = [
        [
            str(i + 1),
            user.id,
            user.openid,
            user.nickname or "-",
            _yuan(user.balance_fen),
            str(user.points or 0),
            str(user.coupons or 0),
            str(token_counts.get(user.id, 0)),
            _ts(user.created_at),
        ]
        for i, user in enumerate(users)
    ]

    scope = f"（openid 含 '{openid_filter}'）" if openid_filter else ""
    print(f"共 {total} 个用户{scope}" + (f"，显示前 {len(rows)} 条" if limit is not None and total > len(rows) else ""))
    if rows:
        print()
        print_table(headers, rows)
    else:
        print("（无匹配记录，确认是否已登录建号或 .env 指向的库路径是否正确）")
    return 0


MODES = {
    "user": query_users,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="pet-back 查库脚本（只读）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--mode", default="user", choices=list(MODES), help="查询模式")
    parser.add_argument("--openid", default=None, help="按 openid 模糊过滤（user 模式）")
    parser.add_argument("--limit", type=int, default=None, help="最多显示条数，默认全部")
    args = parser.parse_args()

    kwargs = {}
    if args.mode == "user":
        kwargs = {"openid_filter": args.openid, "limit": args.limit}
    return MODES[args.mode](**kwargs)


if __name__ == "__main__":
    raise SystemExit(main())
